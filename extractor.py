# ─────────────────────────────────────────────────────────────────────────────
# extractor.py
# Handles all Claude API calls for document parsing and emission extraction
# ─────────────────────────────────────────────────────────────────────────────

import anthropic
import base64
import json
from pathlib import Path
from emission_factors import get_all_material_keys, SCOPE3_LABELS
from pii_redactor import redact_bytes, RedactionResult

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert sustainability analyst specialised in GHG Protocol Scope 3 emissions accounting.
Your job is to extract emission-relevant data from supplier documents such as invoices, purchase orders, delivery notes, or bills of lading.

You MUST return ONLY a valid JSON object — no markdown fences, no explanation, no preamble. Just raw JSON.

The JSON must follow this exact schema:
{
  "supplier_name": "string or null",
  "invoice_number": "string or null",
  "invoice_date": "string or null",
  "currency": "string or null",
  "total_value": number or null,
  "line_items": [
    {
      "description": "verbatim item description from the document",
      "quantity": number (must be a positive number, estimate if not explicit),
      "unit": "kg / g / tonne / pieces / litre / kWh / tonne-km / etc.",
      "material_key": "EXACTLY one key from the allowed_keys list",
      "scope3_category": "EXACTLY one of: purchased_goods / capital_goods / energy_related / upstream_transport / waste / business_travel / other",
      "confidence": number between 0.0 and 1.0,
      "flag": "null or a short data-quality note (e.g., 'unit assumed kg', 'material inferred from context', 'quantity estimated')"
    }
  ],
  "extraction_notes": "brief summary of any assumptions, missing data, or overall data quality"
}

Rules:
1. material_key must be EXACTLY one of the allowed keys — choose the closest match.
2. For transport line items (freight, shipping, logistics), use a transport material_key and set scope3_category to 'upstream_transport'. Set unit to 'tonne-km'.
3. For electricity or energy, use an electricity material_key and set scope3_category to 'energy_related'.
4. If quantity is missing, estimate it from context (e.g., from total weight, number of units). Set flag to 'quantity estimated'.
5. confidence = 1.0 means the material is explicit in the document. confidence < 0.5 means you guessed.
6. Always extract something — never return an empty line_items array.
7. If the document contains no supplier info, set those fields to null but still extract line items.
"""

def build_user_message(file_bytes: bytes, mime_type: str, material_keys: list[str]) -> list[dict]:
    """Build the user message payload for Claude, with the document and instructions."""

    allowed_keys_str = "\n".join(f"  - {k}" for k in material_keys)
    text_block = {
        "type": "text",
        "text": (
            f"Please extract all emission-relevant line items from this supplier document.\n\n"
            f"Allowed material_key values:\n{allowed_keys_str}"
        ),
    }

    if mime_type == "application/pdf":
        doc_block = {
            "type": "document",
            "source": {
                "type": "base64",
                "media_type": "application/pdf",
                "data": base64.standard_b64encode(file_bytes).decode("utf-8"),
            },
        }
    elif mime_type in ("text/csv", "text/plain"):
        # For CSV/text, embed as plain text
        doc_block = {
            "type": "text",
            "text": f"Document content:\n\n{file_bytes.decode('utf-8', errors='replace')}",
        }
    else:
        # Image (PNG, JPG, WEBP)
        doc_block = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64.standard_b64encode(file_bytes).decode("utf-8"),
            },
        }

    return [doc_block, text_block]


def extract_from_document(
    file_bytes: bytes,
    mime_type: str,
    api_key: str,
) -> tuple[dict, RedactionResult]:
    """
    Send a supplier document to Claude and return structured emission data.

    Applies PII redaction before sending to the API.

    Returns:
        (extraction_dict, redaction_result)
        extraction_dict keys: supplier_name, invoice_number, invoice_date,
            currency, total_value, line_items, extraction_notes
    """
    # ── Step 1: scrub PII before touching the API ─────────────────────────
    clean_bytes, redaction = redact_bytes(file_bytes, mime_type)

    client = anthropic.Anthropic(api_key=api_key)
    material_keys = get_all_material_keys()

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": build_user_message(clean_bytes, mime_type, material_keys),
            }
        ],
    )

    raw = response.content[0].text.strip()

    # Strip accidental markdown fences if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        if raw.endswith("```"):
            raw = raw[: raw.rfind("```")]

    return json.loads(raw), redaction


def get_mime_type(filename: str) -> str:
    """Infer MIME type from file extension."""
    ext = Path(filename).suffix.lower()
    return {
        ".pdf":  "application/pdf",
        ".png":  "image/png",
        ".jpg":  "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".csv":  "text/csv",
        ".txt":  "text/plain",
    }.get(ext, "application/octet-stream")


# ── Demo / sample data (no API key needed) ────────────────────────────────────

SAMPLE_EXTRACTION = {
    "supplier_name": "Precision Metals India Pvt. Ltd.",
    "invoice_number": "INV-2024-08731",
    "invoice_date": "2024-03-15",
    "currency": "INR",
    "total_value": 485000,
    "line_items": [
        {
            "description": "Cold Rolled Steel Sheets (CRCA) — 2mm thickness",
            "quantity": 1200,
            "unit": "kg",
            "material_key": "steel",
            "scope3_category": "purchased_goods",
            "confidence": 0.97,
            "flag": None,
        },
        {
            "description": "Aluminium Extrusion Profiles — 6063 alloy",
            "quantity": 340,
            "unit": "kg",
            "material_key": "aluminium",
            "scope3_category": "purchased_goods",
            "confidence": 0.95,
            "flag": None,
        },
        {
            "description": "Copper Wire Rod — 8mm",
            "quantity": 85,
            "unit": "kg",
            "material_key": "copper",
            "scope3_category": "purchased_goods",
            "confidence": 0.98,
            "flag": None,
        },
        {
            "description": "HDPE Packaging Film — 100 micron",
            "quantity": 60,
            "unit": "kg",
            "material_key": "plastic_hdpe",
            "scope3_category": "purchased_goods",
            "confidence": 0.88,
            "flag": "material type inferred from 'HDPE' in description",
        },
        {
            "description": "Road freight — Pune to Gurugram (1,400 km)",
            "quantity": 1685,
            "unit": "tonne-km",
            "material_key": "road_diesel",
            "scope3_category": "upstream_transport",
            "confidence": 0.82,
            "flag": "tonne-km estimated from total shipment weight × distance",
        },
    ],
    "extraction_notes": "All line items extracted with high confidence. Transport quantity estimated from shipment weight (1.205 tonne) × distance (1,400 km). HDPE classification inferred from product code.",
}
