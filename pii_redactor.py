# ─────────────────────────────────────────────────────────────────────────────
# pii_redactor.py
# Scrubs sensitive supplier document data before sending to the Anthropic API.
# Enterprise-grade DaaS products must never send raw PII to third-party LLMs.
#
# Patterns covered:
#   • Bank account & IFSC codes (India)
#   • PAN, GSTIN, CIN (India company identifiers)
#   • Credit/debit card numbers
#   • Email addresses
#   • Phone numbers (India & international)
#   • Aadhaar numbers
#   • Passport numbers
#   • Swift/BIC codes
#   • IBAN numbers
# ─────────────────────────────────────────────────────────────────────────────

import re
from dataclasses import dataclass, field

@dataclass
class RedactionResult:
    redacted_text: str
    redaction_log: list[dict] = field(default_factory=list)

    @property
    def total_redactions(self) -> int:
        return len(self.redaction_log)


# Each entry: (label, compiled_pattern, replacement_token)
_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    (
        "Bank account (IN)",
        re.compile(r"\b\d{9,18}\b(?=\s*(A/?C|account|acc\.?|bank))", re.IGNORECASE),
        "[BANK_ACCOUNT]",
    ),
    (
        "IFSC code",
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        "[IFSC_CODE]",
    ),
    (
        "GSTIN",
        re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b"),
        "[GSTIN]",
    ),
    (
        "PAN",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        "[PAN]",
    ),
    (
        "CIN",
        re.compile(r"\b[LUu]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}\b"),
        "[CIN]",
    ),
    (
        "Aadhaar",
        re.compile(r"\b\d{4}[\s\-]?\d{4}[\s\-]?\d{4}\b"),
        "[AADHAAR]",
    ),
    (
        "Credit/debit card",
        re.compile(r"\b(?:\d{4}[\s\-]?){3}\d{4}\b"),
        "[CARD_NUMBER]",
    ),
    (
        "IBAN",
        re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b"),
        "[IBAN]",
    ),
    (
        "SWIFT/BIC",
        re.compile(r"\b[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?\b"),
        "[SWIFT_BIC]",
    ),
    (
        "Email address",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[EMAIL]",
    ),
    (
        "Phone (IN)",
        re.compile(r"(?<!\d)(?:\+91[\s\-]?)?[6-9]\d{9}(?!\d)"),
        "[PHONE]",
    ),
    (
        "Phone (international)",
        re.compile(r"\+\d{1,3}[\s\-]?\(?\d{1,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}"),
        "[PHONE]",
    ),
    (
        "Passport",
        re.compile(r"\b[A-Z]{1,2}\d{6,9}\b"),
        "[PASSPORT]",
    ),
]


def redact(text: str) -> RedactionResult:
    """
    Apply all PII patterns to text, replacing matches with labelled tokens.
    Returns a RedactionResult with the cleaned text and an audit log.
    """
    log: list[dict] = []
    result = text

    for label, pattern, token in _PATTERNS:
        matches = list(pattern.finditer(result))
        if matches:
            for m in matches:
                log.append({
                    "type":     label,
                    "original": m.group()[:6] + "***",  # partial for audit, not full value
                    "position": m.start(),
                    "token":    token,
                })
            result = pattern.sub(token, result)

    return RedactionResult(redacted_text=result, redaction_log=log)


def redact_bytes(file_bytes: bytes, mime_type: str) -> tuple[bytes, RedactionResult]:
    """
    For text-based files (CSV, TXT), redact PII in the raw bytes.
    For binary files (PDF, images), return unchanged — Claude handles those natively
    and binary scrubbing requires a dedicated PDF/OCR pipeline (out of scope for v0.1).
    """
    if mime_type in ("text/csv", "text/plain"):
        text = file_bytes.decode("utf-8", errors="replace")
        result = redact(text)
        return result.redacted_text.encode("utf-8"), result

    # Binary formats — return as-is with an informational log entry
    return file_bytes, RedactionResult(
        redacted_text="[binary — redaction not applied]",
        redaction_log=[{
            "type":     "Binary file",
            "original": mime_type,
            "position": 0,
            "token":    "No redaction applied to binary. Consider an on-prem deployment for sensitive PDFs.",
        }],
    )


if __name__ == "__main__":
    # Quick smoke test
    test = """
    Invoice from Rahul Sharma <rahul.sharma@acmecorp.in>
    GSTIN: 27AAPFU0939F1ZV
    PAN: AAPFU0939F
    Bank A/C: 123456789012
    IFSC: HDFC0001234
    Phone: +91 9876543210
    Amount due: INR 485,000
    Steel sheets: 1200 kg @ INR 85/kg
    """
    r = redact(test)
    print(r.redacted_text)
    print(f"\n{r.total_redactions} PII items redacted:")
    for entry in r.redaction_log:
        print(f"  [{entry['type']}] {entry['original']} → {entry['token']}")
