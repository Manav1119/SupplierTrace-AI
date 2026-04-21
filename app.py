# ─────────────────────────────────────────────────────────────────────────────
# app.py  —  SupplierTrace AI  v0.2
# Refinements: HITL verification, review queue, carbon/spend ratio,
#              data quality dashboard, supplier session history,
#              PII redaction audit, mock Kyoto™ sync
# ─────────────────────────────────────────────────────────────────────────────

import streamlit as st
import pandas as pd
import plotly.express as px
import io, json, time
from datetime import datetime
from pathlib import Path

from emission_factors import (
    EMISSION_FACTORS,
    SCOPE3_LABELS,
    calculate_co2e,
    get_factor,
)
from extractor import extract_from_document, get_mime_type, SAMPLE_EXTRACTION
from pii_redactor import RedactionResult

# ── Constants ─────────────────────────────────────────────────────────────────

CONF_THRESHOLD   = 0.70
GOLD_FILE        = Path("gold_standard.json")
MATERIAL_OPTIONS = list(EMISSION_FACTORS.keys())

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="SupplierTrace AI",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
[data-testid="stAppViewContainer"] { background:#f8faf8; }
[data-testid="stSidebar"]          { background:#fff; border-right:1px solid #e0ebe0; }

.metric-card  { background:#fff; border:1px solid #d4e8d4; border-radius:12px; padding:1.1rem 1.25rem; text-align:center; }
.metric-label { font-size:12px; color:#6b8f6b; font-weight:500; text-transform:uppercase; letter-spacing:.05em; margin-bottom:4px; }
.metric-value { font-size:28px; font-weight:600; color:#1a3a1a; line-height:1.1; }
.metric-sub   { font-size:12px; color:#8aab8a; margin-top:2px; }

.badge-high   { background:#d4f0d4; color:#1a6b1a; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }
.badge-medium { background:#fff3cd; color:#7a5c00; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }
.badge-low    { background:#ffe0e0; color:#8b1a1a; padding:2px 8px; border-radius:20px; font-size:11px; font-weight:500; }

.info-box  { background:#eaf4ea; border-left:3px solid #2e7d32; border-radius:0 8px 8px 0; padding:.75rem 1rem; font-size:13px; color:#1a4a1a; margin-bottom:1rem; }
.warn-box  { background:#fff8e1; border-left:3px solid #f9a825; border-radius:0 8px 8px 0; padding:.75rem 1rem; font-size:13px; color:#5a4000; margin-bottom:1rem; }
.error-box { background:#fce4ec; border-left:3px solid #c62828; border-radius:0 8px 8px 0; padding:.75rem 1rem; font-size:13px; color:#5a0000; margin-bottom:1rem; }

.sidebar-section { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.07em; color:#6b8f6b; margin:1rem 0 .4rem; }
.supplier-row { display:flex; justify-content:space-between; padding:5px 0; border-bottom:1px solid #e8f0e8; font-size:13px; }

[data-testid="stFileUploader"] { border:2px dashed #b5d4b5 !important; border-radius:12px !important; background:#f0f8f0 !important; }
.stButton > button { background:#2e7d32 !important; color:white !important; border:none !important; border-radius:8px !important; font-weight:500 !important; }
.stButton > button:hover { background:#1b5e20 !important; }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────

for k, v in {
    "result":           None,
    "redaction":        None,
    "verifications":    {},
    "gold_log":         [],
    "supplier_history": {},
}.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── Helpers ───────────────────────────────────────────────────────────────────

def confidence_badge(val: float) -> str:
    if val >= 0.85:
        return f"<span class='badge-high'>High {val:.0%}</span>"
    elif val >= CONF_THRESHOLD:
        return f"<span class='badge-medium'>Medium {val:.0%}</span>"
    return f"<span class='badge-low'>Low {val:.0%}</span>"


def enrich(data: dict, verifications: dict) -> pd.DataFrame:
    rows = []
    for idx, item in enumerate(data.get("line_items", [])):
        v   = verifications.get(idx, {})
        mk  = v.get("material_key") or item.get("material_key", "unknown")
        qty = float(v.get("quantity") or item.get("quantity") or 0)
        conf = float(item.get("confidence", 0.5))
        ef   = get_factor(mk)
        co2e = calculate_co2e(mk, qty)
        rows.append({
            "_idx":             idx,
            "Description":      item.get("description", "—"),
            "Quantity":         qty,
            "Unit":             item.get("unit", ef["unit"]),
            "Material":         ef["label"],
            "Scope 3 category": SCOPE3_LABELS.get(item.get("scope3_category","other"),
                                                   item.get("scope3_category","other")),
            "EF (kgCO₂e/unit)": ef["factor"],
            "EF source":        ef["source"],
            "tCO₂e":            round(co2e / 1000, 5),
            "Confidence":       conf,
            "_flag":            item.get("flag"),
            "_material_key":    mk,
            "_needs_review":    conf < CONF_THRESHOLD,
            "_reviewed":        v.get("reviewed", False),
            "_corrected":       bool(v),
        })
    return pd.DataFrame(rows)


def save_gold(item: dict, correction: dict):
    entry = {
        "timestamp":     datetime.utcnow().isoformat(),
        "original_desc": item.get("description"),
        "original_mk":   item.get("material_key"),
        "original_qty":  item.get("quantity"),
        "original_conf": item.get("confidence"),
        "corrected_mk":  correction.get("material_key"),
        "corrected_qty": correction.get("quantity"),
        "reviewer":      "human",
    }
    st.session_state.gold_log.append(entry)
    existing = []
    if GOLD_FILE.exists():
        try:
            existing = json.loads(GOLD_FILE.read_text())
        except Exception:
            pass
    GOLD_FILE.write_text(json.dumps(existing + [entry], indent=2))


def update_history(data: dict, df: pd.DataFrame):
    name   = data.get("supplier_name") or "Unknown supplier"
    inv_no = data.get("invoice_number", "—")
    total  = round(df["tCO₂e"].sum(), 5)
    hist   = st.session_state.supplier_history
    if name not in hist:
        hist[name] = {"total_tco2e": 0.0, "invoices": []}
    if inv_no not in [i["invoice"] for i in hist[name]["invoices"]]:
        hist[name]["total_tco2e"] = round(hist[name]["total_tco2e"] + total, 5)
        hist[name]["invoices"].append({"invoice": inv_no, "date": data.get("invoice_date","—"), "tco2e": total})


def all_reviewed(df: pd.DataFrame) -> bool:
    return len(df[df["_needs_review"] & ~df["_reviewed"]]) == 0


def kpi_card(col, label, value, sub, color="#1a3a1a"):
    col.markdown(
        f"<div class='metric-card'><div class='metric-label'>{label}</div>"
        f"<div class='metric-value' style='color:{color};'>{value}</div>"
        f"<div class='metric-sub'>{sub}</div></div>",
        unsafe_allow_html=True,
    )


# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🌿 SupplierTrace AI")
    st.markdown("<p style='font-size:13px;color:#6b8f6b;'>v0.2 · AI-powered Scope 3 extraction</p>", unsafe_allow_html=True)
    st.divider()

    st.markdown("<div class='sidebar-section'>Configuration</div>", unsafe_allow_html=True)
    api_key = st.text_input("Anthropic API key", type="password", placeholder="sk-ant-…")
    region  = st.selectbox("Region / EF priority",
                           ["India (CEA 2023)", "United Kingdom (DEFRA 2023)",
                            "United States (EPA 2022)", "Global average"], index=0)
    st.divider()

    # Supplier history
    st.markdown("<div class='sidebar-section'>Session — Supplier history</div>", unsafe_allow_html=True)
    if st.session_state.supplier_history:
        for supplier, hist in st.session_state.supplier_history.items():
            st.markdown(
                f"<div class='supplier-row'>"
                f"<span style='color:#1a3a1a;font-weight:500;'>{supplier[:20]}</span>"
                f"<span style='color:#2e7d32;font-weight:600;'>{hist['total_tco2e']:.3f} t</span>"
                f"</div>", unsafe_allow_html=True)
            for inv in hist["invoices"]:
                st.markdown(f"<p style='font-size:11px;color:#8aab8a;margin:2px 0 0 8px;'>↳ {inv['invoice']} · {inv['tco2e']:.4f} t</p>", unsafe_allow_html=True)
        total_sess = sum(h["total_tco2e"] for h in st.session_state.supplier_history.values())
        st.markdown(f"<p style='font-size:12px;font-weight:600;color:#2e7d32;margin-top:8px;'>Session total: {total_sess:.3f} tCO₂e</p>", unsafe_allow_html=True)
    else:
        st.caption("No invoices analysed yet.")

    # HITL gold log
    if st.session_state.gold_log:
        st.divider()
        st.markdown("<div class='sidebar-section'>HITL — Gold standard</div>", unsafe_allow_html=True)
        st.markdown(f"<p style='font-size:12px;color:#6b8f6b;'>{len(st.session_state.gold_log)} correction(s) saved</p>", unsafe_allow_html=True)
        st.download_button("⬇ Download gold_standard.json",
                           data=json.dumps(st.session_state.gold_log, indent=2),
                           file_name="gold_standard.json", mime="application/json",
                           use_container_width=True)
        st.caption("Use to fine-tune Claude Haiku as a cheaper extraction model.")

    st.divider()
    st.markdown("<p style='font-size:11px;color:#aaa;'>Prototype v0.2 · Manav · 2024</p>", unsafe_allow_html=True)


# ── Header ────────────────────────────────────────────────────────────────────

st.markdown("""
<div style='margin-bottom:1.5rem;'>
  <h1 style='font-size:2rem;font-weight:600;color:#1a3a1a;margin-bottom:4px;'>🌿 SupplierTrace AI</h1>
  <p style='font-size:15px;color:#5a7a5a;margin:0;'>
    Audit-ready Scope 3 extraction with human verification, PII redaction, and Kyoto™ sync.
  </p>
</div>
""", unsafe_allow_html=True)

col_up, col_act = st.columns([3, 1], gap="large")
with col_up:
    uploaded_file = st.file_uploader("drop", type=["pdf","png","jpg","jpeg","csv"],
                                     label_visibility="collapsed")
    if uploaded_file:
        st.markdown(f"<div class='info-box'>📎 <strong>{uploaded_file.name}</strong> — {uploaded_file.size/1024:.1f} KB · ready</div>", unsafe_allow_html=True)

with col_act:
    st.markdown("<br>", unsafe_allow_html=True)
    run_demo = st.button("▶  Load demo invoice",  use_container_width=True)
    run_real = st.button("🔍  Analyse document",   use_container_width=True, disabled=(uploaded_file is None))

st.divider()


# ── Main render ───────────────────────────────────────────────────────────────

def render_results(data: dict, redaction: RedactionResult | None = None):
    df = enrich(data, st.session_state.verifications)
    if df.empty:
        st.warning("No line items extracted."); return

    update_history(data, df)

    total_tco2e   = df["tCO₂e"].sum()
    avg_conf      = df["Confidence"].mean()
    needs_review  = df[df["_needs_review"]]
    pending_count = int(len(df[df["_needs_review"] & ~df["_reviewed"]]))
    reviewed_ok   = all_reviewed(df)
    top_cat       = df.groupby("Scope 3 category")["tCO₂e"].sum().idxmax()
    total_value   = data.get("total_value")
    carbon_int    = round((total_tco2e * 1000) / total_value, 4) if total_value else None

    # ── Banners ─────────────────────────────────────────────────────────────
    if pending_count > 0:
        st.markdown(f"<div class='warn-box'>⚠️ <strong>{pending_count} item(s) require human verification</strong> (confidence &lt; {CONF_THRESHOLD:.0%}). Review below before export is unlocked.</div>", unsafe_allow_html=True)
    if redaction and redaction.total_redactions > 0:
        st.markdown(f"<div class='info-box'>🔒 <strong>{redaction.total_redactions} PII item(s) scrubbed</strong> before sending to Claude API (bank details, tax IDs, contacts).</div>", unsafe_allow_html=True)

    # ── KPI row ──────────────────────────────────────────────────────────────
    st.markdown("### Summary")
    k1, k2, k3, k4, k5 = st.columns(5, gap="small")
    kpi_card(k1, "Total Scope 3",    f"{total_tco2e:.3f}", "tCO₂e")
    kpi_card(k2, "Line items",       f"{len(df)}",          "extracted")
    kpi_card(k3, "Avg confidence",   f"{avg_conf:.0%}",     "data quality",
             color="#1a6b1a" if avg_conf >= 0.85 else ("#7a5c00" if avg_conf >= CONF_THRESHOLD else "#8b1a1a"))
    kpi_card(k4, "Needs review",     f"{len(needs_review)}", "flagged items",
             color="#8b1a1a" if len(needs_review) > 0 else "#1a6b1a")
    if carbon_int:
        kpi_card(k5, "Carbon intensity", f"{carbon_int:.2f}",
                 f"kgCO₂e / {data.get('currency','unit')}", color="#1565c0")
    else:
        k5.markdown("<div class='metric-card'><div class='metric-label'>Carbon intensity</div><div class='metric-value' style='font-size:14px;padding-top:6px;color:#aaa;'>—</div><div class='metric-sub'>no invoice value</div></div>", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Supplier header
    if data.get("supplier_name"):
        inf = st.columns(4)
        for col, (lbl, val) in zip(inf, [
            ("Supplier",      data.get("supplier_name","—")),
            ("Invoice #",     data.get("invoice_number","—")),
            ("Date",          data.get("invoice_date","—")),
            ("Invoice value", f"{data.get('currency','') or ''} {data.get('total_value','—')}"),
        ]):
            col.markdown(f"<p style='font-size:11px;color:#6b8f6b;font-weight:600;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px;'>{lbl}</p>"
                         f"<p style='font-size:14px;color:#1a3a1a;font-weight:500;margin:0;'>{val}</p>", unsafe_allow_html=True)

    st.divider()

    # ── Charts ───────────────────────────────────────────────────────────────
    st.markdown("### Emission breakdown")
    c1, c2, c3 = st.columns(3, gap="large")

    with c1:
        cat_df = df.groupby("Scope 3 category")["tCO₂e"].sum().reset_index().sort_values("tCO₂e", ascending=False)
        fig = px.bar(cat_df, x="tCO₂e", y="Scope 3 category", orientation="h",
                     color="tCO₂e", color_continuous_scale=["#a8d5a2","#2e7d32"], title="By GHG category")
        fig.update_layout(plot_bgcolor="white", paper_bgcolor="white", coloraxis_showscale=False,
                          margin=dict(l=0,r=10,t=40,b=0), height=260, title_font_size=13, font_family="sans-serif")
        fig.update_xaxes(showgrid=True, gridcolor="#e8f0e8", zeroline=False)
        fig.update_yaxes(showgrid=False)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        # Data quality dashboard — confidence distribution
        bins = pd.cut(df["Confidence"],
                      bins=[0, 0.5, CONF_THRESHOLD, 0.85, 1.0],
                      labels=["<50% low", "50–70% borderline", "70–85% medium", ">85% high"],
                      include_lowest=True)
        conf_df = bins.value_counts().reset_index()
        conf_df.columns = ["Band", "Items"]
        conf_df = conf_df.sort_values("Band")
        fig2 = px.bar(conf_df, x="Band", y="Items", color="Band",
                      color_discrete_map={"<50% low":"#e53935","50–70% borderline":"#fb8c00",
                                          "70–85% medium":"#fdd835",">85% high":"#43a047"},
                      title="Data quality — confidence spread")
        fig2.update_layout(showlegend=False, plot_bgcolor="white", paper_bgcolor="white",
                           margin=dict(l=0,r=0,t=40,b=0), height=260, title_font_size=13, font_family="sans-serif")
        fig2.update_xaxes(showgrid=False)
        fig2.update_yaxes(showgrid=True, gridcolor="#e8f0e8", zeroline=False)
        st.plotly_chart(fig2, use_container_width=True)

    with c3:
        mat_df = df.groupby("Material")["tCO₂e"].sum().reset_index().sort_values("tCO₂e", ascending=False)
        fig3 = px.pie(mat_df, values="tCO₂e", names="Material",
                      color_discrete_sequence=px.colors.sequential.Greens[2:][::-1],
                      title="By material", hole=0.45)
        fig3.update_traces(textposition="outside", textinfo="percent+label")
        fig3.update_layout(showlegend=False, margin=dict(l=0,r=0,t=40,b=0),
                           height=260, title_font_size=13, font_family="sans-serif", paper_bgcolor="white")
        st.plotly_chart(fig3, use_container_width=True)

    # Carbon intensity callout
    if carbon_int:
        top_mat = df.sort_values("tCO₂e", ascending=False).iloc[0]
        st.markdown(
            f"<div class='info-box'>📊 <strong>Carbon intensity: {carbon_int:.2f} kgCO₂e per {data.get('currency','unit')} spent</strong> — "
            f"largest source: <strong>{top_mat['Material']}</strong> "
            f"({top_mat['tCO₂e']:.4f} tCO₂e · {top_mat['tCO₂e']/total_tco2e:.0%} of total). "
            f"Flag for procurement review.</div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # ── HITL Verification table ───────────────────────────────────────────────
    st.markdown("### Line items — Human verification")
    st.caption(f"Items with confidence < {CONF_THRESHOLD:.0%} are flagged 🔴 and must be checked off before export.")

    for _, row in df.iterrows():
        idx          = int(row["_idx"])
        needs_rev    = bool(row["_needs_review"])
        is_reviewed  = bool(row["_reviewed"])
        is_corrected = bool(row["_corrected"])

        if needs_rev and not is_reviewed:
            card_style = "border:1.5px solid #e53935; border-radius:10px; padding:12px 14px; margin-bottom:10px; background:#fff8f8;"
        elif is_reviewed or is_corrected:
            card_style = "border:1.5px solid #43a047; border-radius:10px; padding:12px 14px; margin-bottom:10px; background:#f5fff5;"
        else:
            card_style = "border:1px solid #d4e8d4; border-radius:10px; padding:12px 14px; margin-bottom:10px; background:#fff;"

        st.markdown(f"<div style='{card_style}'>", unsafe_allow_html=True)
        top = st.columns([3, 1, 1, 1, 1])
        with top[0]:
            flag_md = f"  \n`⚠ {row['_flag']}`" if row["_flag"] else ""
            st.markdown(f"**{str(row['Description'])[:80]}**{flag_md}")
        with top[1]:
            st.markdown(f"<span style='font-size:11px;color:#6b8f6b;'>Material</span><br><span style='font-size:13px;font-weight:500;'>{row['Material']}</span>", unsafe_allow_html=True)
        with top[2]:
            st.markdown(f"<span style='font-size:11px;color:#6b8f6b;'>Quantity</span><br><span style='font-size:13px;font-weight:500;'>{row['Quantity']:g} {row['Unit']}</span>", unsafe_allow_html=True)
        with top[3]:
            st.markdown(f"<span style='font-size:11px;color:#6b8f6b;'>tCO₂e</span><br><span style='font-size:13px;font-weight:600;color:#1b5e20;'>{row['tCO₂e']:.4f}</span>", unsafe_allow_html=True)
        with top[4]:
            st.markdown(f"<span style='font-size:11px;color:#6b8f6b;'>Confidence</span><br>{confidence_badge(row['Confidence'])}", unsafe_allow_html=True)

        # Verify expander
        exp_label = ("✅ Corrected" if is_corrected else
                     ("🔴 Needs review — verify here" if needs_rev else "✏️ Edit / verify"))
        with st.expander(exp_label, expanded=(needs_rev and not is_reviewed)):
            vc = st.columns([2, 1, 1])
            with vc[0]:
                cur_mk = row["_material_key"] if row["_material_key"] in MATERIAL_OPTIONS else MATERIAL_OPTIONS[0]
                new_mk = st.selectbox("Material key", options=MATERIAL_OPTIONS,
                                      index=MATERIAL_OPTIONS.index(cur_mk), key=f"mk_{idx}")
            with vc[1]:
                new_qty = st.number_input("Quantity", value=float(row["Quantity"]),
                                          min_value=0.0, key=f"qty_{idx}")
            with vc[2]:
                checked = st.checkbox("Mark as reviewed ✓", value=is_reviewed, key=f"rev_{idx}") if needs_rev else True

            sc1, sc2 = st.columns([1, 3])
            with sc1:
                if st.button("💾 Save correction", key=f"save_{idx}"):
                    original = data["line_items"][idx]
                    corr = {"material_key": new_mk, "quantity": new_qty, "reviewed": True}
                    st.session_state.verifications[idx] = corr
                    save_gold(original, corr)
                    st.success("Saved to gold standard ✓")
                    st.rerun()
            with sc2:
                if needs_rev and not is_reviewed:
                    if st.button("✓ Accept AI output as-is", key=f"accept_{idx}"):
                        mk_val = row["_material_key"]
                        corr = {"material_key": mk_val, "quantity": float(row["Quantity"]), "reviewed": True}
                        st.session_state.verifications[idx] = corr
                        st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    if data.get("extraction_notes"):
        st.markdown(f"<div class='info-box'>📋 <strong>Extraction notes:</strong> {data['extraction_notes']}</div>", unsafe_allow_html=True)

    st.divider()

    # ── Export ────────────────────────────────────────────────────────────────
    st.markdown("### Export & sync to Kyoto™")

    if not reviewed_ok:
        st.markdown(
            f"<div class='error-box'>🔒 <strong>Export locked</strong> — {pending_count} item(s) still need review. "
            f"This ensures every exported row is audit-ready and traceable to a human decision.</div>",
            unsafe_allow_html=True,
        )

    df_final = enrich(data, st.session_state.verifications)

    export_df = df_final[[
        "Description","Quantity","Unit","Material","Scope 3 category",
        "EF (kgCO₂e/unit)","EF source","tCO₂e","Confidence",
    ]].copy()
    export_df["Human verified"] = df_final["_corrected"]
    export_df["Supplier"]       = data.get("supplier_name","")
    export_df["Invoice number"] = data.get("invoice_number","")
    export_df["Invoice date"]   = data.get("invoice_date","")

    csv_buf = io.StringIO()
    export_df.to_csv(csv_buf, index=False)

    kyoto_payload = {
        "schema_version":     "kyoto_v1",
        "source":             "SupplierTrace AI v0.2",
        "exported_at":        datetime.utcnow().isoformat(),
        "supplier_name":      data.get("supplier_name"),
        "invoice_number":     data.get("invoice_number"),
        "invoice_date":       data.get("invoice_date"),
        "region":             region,
        "total_tco2e":        round(df_final["tCO₂e"].sum(), 5),
        "carbon_intensity":   carbon_int,
        "currency":           data.get("currency"),
        "total_value":        data.get("total_value"),
        "ghg_protocol_scope": 3,
        "pii_redactions":     redaction.total_redactions if redaction else 0,
        "line_items": [
            {
                "description":    r["Description"],
                "quantity":       r["Quantity"],
                "unit":           r["Unit"],
                "material":       r["Material"],
                "scope3_category":r["Scope 3 category"],
                "ef_kgco2e_unit": r["EF (kgCO₂e/unit)"],
                "ef_source":      r["EF source"],
                "tco2e":          r["tCO₂e"],
                "confidence":     r["Confidence"],
                "human_verified": bool(r["_corrected"]),
            }
            for _, r in df_final.iterrows()
        ],
    }
    kyoto_json = json.dumps(kyoto_payload, indent=2)

    e1, e2, e3 = st.columns(3)
    with e1:
        st.download_button("⬇  Download CSV", data=csv_buf.getvalue(),
                           file_name=f"scope3_{(data.get('supplier_name') or 'export').replace(' ','_').lower()}_{datetime.today().strftime('%Y%m%d')}.csv",
                           mime="text/csv", use_container_width=True, disabled=not reviewed_ok)
    with e2:
        st.download_button("⬇  Kyoto™ JSON", data=kyoto_json,
                           file_name=f"kyoto_{(data.get('invoice_number') or 'export').replace(' ','_').lower()}.json",
                           mime="application/json", use_container_width=True, disabled=not reviewed_ok)
    with e3:
        if st.button("🔗  Sync to Kyoto™", use_container_width=True, disabled=not reviewed_ok):
            with st.spinner("Posting to Kyoto™ ingestion API…"):
                time.sleep(1.8)
            st.success(
                f"✅ Synced {len(kyoto_payload['line_items'])} items · "
                f"{kyoto_payload['total_tco2e']} tCO₂e · "
                f"Supplier: {data.get('supplier_name','—')}"
            )
            st.caption("Production: POST https://kyoto.fitsol.green/api/v1/ingestion with OAuth2 bearer token.")


# ── Entry point ───────────────────────────────────────────────────────────────

if run_demo:
    st.session_state.result        = SAMPLE_EXTRACTION
    st.session_state.redaction     = None
    st.session_state.verifications = {}

if run_real:
    if not api_key:
        st.error("Enter your Anthropic API key in the sidebar first.")
    elif uploaded_file is None:
        st.error("Upload a document first.")
    else:
        mime = get_mime_type(uploaded_file.name)
        if mime == "application/octet-stream":
            st.error("Unsupported file type.")
        else:
            with st.spinner(f"Redacting PII and analysing {uploaded_file.name}…"):
                try:
                    result, redaction = extract_from_document(uploaded_file.read(), mime, api_key)
                    st.session_state.result        = result
                    st.session_state.redaction     = redaction
                    st.session_state.verifications = {}
                except json.JSONDecodeError as e:
                    st.error(f"Claude returned unexpected output — try again. Detail: {e}")
                except Exception as e:
                    st.error(f"Error: {e}")

if st.session_state.result:
    render_results(st.session_state.result, st.session_state.redaction)
else:
    st.markdown("""
<div style='text-align:center;padding:3rem 2rem;color:#5a7a5a;'>
    <div style='font-size:3rem;margin-bottom:1rem;'>📄</div>
    <p style='font-size:16px;font-weight:500;color:#2e4a2e;'>Upload a supplier document to get started</p>
    <p style='font-size:14px;color:#7a9a7a;'>PDF invoices · PNG/JPG scans · CSV exports<br>Or click <strong>Load demo invoice</strong></p>
    <br>
    <div style='display:flex;justify-content:center;gap:1.5rem;flex-wrap:wrap;font-size:13px;'>
        <span>✅ HITL verification + review queue</span>
        <span>✅ PII redaction before API call</span>
        <span>✅ Carbon intensity / spend ratio</span>
        <span>✅ Confidence quality dashboard</span>
        <span>✅ Supplier session history</span>
        <span>✅ Kyoto™ schema export + sync</span>
    </div>
</div>
""", unsafe_allow_html=True)
