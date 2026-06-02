"""Smart Substitution Engine — demo UI (Streamlit).

Talks directly to the AI service (default http://localhost:8000) so it is fully
self-contained — no database or .NET backend needed for the demo.

Run locally:
    cd ui
    pip install -r requirements.txt
    streamlit run app.py
"""

from __future__ import annotations

import os

import pandas as pd
import requests
import streamlit as st

AI_URL_DEFAULT = os.environ.get("AI_SERVICE_URL", "http://localhost:8000").rstrip("/")
# Browser-reachable AI URL for the chat widget (the user's browser calls it
# directly, so it must NOT be the in-cluster hostname like "ai-service").
AI_PUBLIC_URL = os.environ.get("AI_PUBLIC_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 90  # explanations can take a few seconds

LABEL_COLORS = {
    "Excellent": "#15803d",
    "Strong": "#2563eb",
    "Good": "#0891b2",
    "Fair": "#d97706",
    "Weak": "#dc2626",
}
DIMENSIONS = [
    ("category_similarity", "Category", 30),
    ("contract_match", "Contract", 25),
    ("price_similarity", "Price", 20),
    ("stock_availability", "Stock", 10),
    ("unit_pack_similarity", "Unit / pack", 8),
]

# --------------------------------------------------------------------------- #
# Demo data
# --------------------------------------------------------------------------- #
PRESETS: dict[str, dict] = {
    "Chicken Breast — out of stock": {
        "requested": {
            "id": "product_001", "name": "Chicken Breast 2kg", "category_id": "chicken",
            "brand": "Brand A", "unit": "kg", "pack_size": 2.0, "base_price": 10.0,
            "dietary_tags": "halal",
        },
        "quantity": 20,
        "candidates": [
            {"id": "product_2033", "name": "Chicken Breast Premium 2kg", "category_id": "chicken",
             "brand": "Brand B", "unit": "kg", "pack_size": 2.0, "base_price": 10.5,
             "stock_quantity": 150, "contract_price": 9.5, "is_preferred": True, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_2099", "name": "Organic Chicken Breast 2kg", "category_id": "chicken",
             "brand": "Brand C", "unit": "kg", "pack_size": 2.0, "base_price": 11.0,
             "stock_quantity": 40, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": "halal,organic"},
            {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg", "category_id": "poultry",
             "brand": "Brand D", "unit": "kg", "pack_size": 2.0, "base_price": 9.8,
             "stock_quantity": 80, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_5001", "name": "Pork Loin 2kg", "category_id": "pork",
             "brand": "Brand X", "unit": "kg", "pack_size": 2.0, "base_price": 9.0,
             "stock_quantity": 120, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": ""},
        ],
    },
    "Halal request — allergen filter blocks pork": {
        "requested": {
            "id": "product_010", "name": "Beef Mince 1kg", "category_id": "beef",
            "brand": "Brand A", "unit": "kg", "pack_size": 1.0, "base_price": 12.0,
            "dietary_tags": "halal",
        },
        "quantity": 10,
        "candidates": [
            {"id": "product_4001", "name": "Beef Sirloin 2kg", "category_id": "beef",
             "brand": "Brand B", "unit": "kg", "pack_size": 2.0, "base_price": 13.0,
             "stock_quantity": 60, "contract_price": 12.5, "is_preferred": True, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_5002", "name": "Pork Sausages 1kg", "category_id": "pork",
             "brand": "Brand X", "unit": "kg", "pack_size": 1.0, "base_price": 8.0,
             "stock_quantity": 200, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": ""},
        ],
    },
}

SAMPLE_CATALOG = [
    {"id": "product_001", "name": "Chicken Breast 2kg", "category_id": "chicken", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_2033", "name": "Chicken Breast Premium 2kg", "category_id": "chicken", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_2099", "name": "Organic Chicken Breast 2kg", "category_id": "chicken", "is_active": True, "dietary_tags": ["halal", "organic"]},
    {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg", "category_id": "poultry", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_3003", "name": "Turkey Breast 2kg", "category_id": "poultry", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_4001", "name": "Beef Sirloin 2kg", "category_id": "beef", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_5001", "name": "Pork Loin 2kg", "category_id": "pork", "is_active": True, "dietary_tags": []},
    {"id": "product_6001", "name": "Atlantic Salmon Fillet 1kg", "category_id": "fish", "is_active": True, "dietary_tags": ["pescatarian"]},
    {"id": "product_7001", "name": "Tofu Firm 500g", "category_id": "plant_protein", "is_active": True, "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_7002", "name": "Plant-Based Chicken Strips 500g", "category_id": "plant_protein", "is_active": True, "dietary_tags": ["vegan"]},
    {"id": "product_8001", "name": "Fresh Carrots 5kg", "category_id": "vegetables", "is_active": True, "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_9002", "name": "Discontinued Chicken Nuggets 1kg", "category_id": "chicken", "is_active": False, "dietary_tags": ["halal"]},
]

CANDIDATE_COLUMNS = [
    "id", "name", "category_id", "brand", "unit", "pack_size", "base_price",
    "stock_quantity", "contract_price", "is_preferred", "is_active", "dietary_tags",
]


# --------------------------------------------------------------------------- #
# API helpers
# --------------------------------------------------------------------------- #
def _base_url() -> str:
    return st.session_state.get("ai_url", AI_URL_DEFAULT).rstrip("/")


def api_get(path: str):
    try:
        r = requests.get(_base_url() + path, timeout=10)
        return r.ok, (r.json() if r.content else {}), None
    except Exception as exc:
        return False, None, str(exc)


def api_post(path: str, payload: dict):
    try:
        r = requests.post(_base_url() + path, json=payload, timeout=TIMEOUT)
        data = r.json() if r.content else {}
        if not r.ok:
            return False, None, f"HTTP {r.status_code}: {data.get('detail', data)}"
        return True, data, None
    except Exception as exc:
        return False, None, str(exc)


def _split_tags(value) -> list[str]:
    if isinstance(value, list):
        return [t for t in value if t]
    return [t.strip() for t in str(value or "").split(",") if t.strip()]


# --------------------------------------------------------------------------- #
# Styling
# --------------------------------------------------------------------------- #
def build_css(dark: bool) -> str:
    """Return the full <style> block for the chosen theme.

    Every colour is driven by a CSS variable, so flipping ``dark`` re-themes the
    whole app in one shot — the custom cards AND the native Streamlit shell
    (sidebar, inputs, selects, tabs, expanders, secondary buttons).
    """
    if dark:
        v = {
            "bg": "#0b1220", "surface": "#141d2e", "border": "#25324a", "inputbg": "#0f1828",
            "text": "#e9eef7", "muted": "#9fb0c9", "faint": "#6f8099", "body": "#c7d2e0",
            "track": "#1f2a3e", "rankbg": "#1e2a47", "ranktext": "#a5b4fc", "expl": "#111c30",
            "chipbg": "#1f2a3e", "chiptext": "#cbd5e1", "empty": "#141d2e", "eborder": "#2c3a54",
            "shadow": "0 1px 3px rgba(0,0,0,.35)", "rule_end": "#25324a", "dot_off": "#475569",
        }
    else:
        v = {
            "bg": "#f6f7f9", "surface": "#ffffff", "border": "#e8ebf0", "inputbg": "#ffffff",
            "text": "#0f172a", "muted": "#64748b", "faint": "#94a3b8", "body": "#334155",
            "track": "#eef1f5", "rankbg": "#eef2ff", "ranktext": "#4338ca", "expl": "#f8fafc",
            "chipbg": "#f1f5f9", "chiptext": "#475569", "empty": "#ffffff", "eborder": "#d8dee7",
            "shadow": "0 1px 3px rgba(15,23,42,.04)", "rule_end": "#e2e8f0", "dot_off": "#cbd5e1",
        }
    return f"""
<style>
  :root {{
    --bg:{v['bg']}; --surface:{v['surface']}; --border:{v['border']}; --inputbg:{v['inputbg']};
    --text:{v['text']}; --muted:{v['muted']}; --faint:{v['faint']}; --body:{v['body']};
    --track:{v['track']}; --rankbg:{v['rankbg']}; --ranktext:{v['ranktext']}; --expl:{v['expl']};
    --chipbg:{v['chipbg']}; --chiptext:{v['chiptext']}; --empty:{v['empty']}; --eborder:{v['eborder']};
    --shadow:{v['shadow']}; --rule-end:{v['rule_end']}; --dot-off:{v['dot_off']};
  }}

  /* hide developer chrome */
  /* Hide developer chrome. IMPORTANT: do NOT hide the whole stToolbar — the
     collapsed-sidebar expand ( » ) button lives inside it, so hiding the toolbar
     leaves no way to reopen the sidebar once collapsed. Hide only the deploy /
     status / decoration bits and keep the toolbar itself. */
  [data-testid="stDecoration"], [data-testid="stStatusWidget"] {{ display:none !important; }}
  [data-testid="stAppDeployButton"], [data-testid="stToolbarActions"] {{ display:none !important; }}
  /* Header + toolbar follow the theme (no white bar in dark mode). */
  [data-testid="stHeader"], [data-testid="stToolbar"] {{ background:transparent !important; }}
  #MainMenu, footer {{ visibility:hidden; }}

  /* app shell + native surfaces follow the theme */
  .stApp {{ background:var(--bg); color:var(--text);
            --background-color:var(--bg); --secondary-background-color:var(--surface); --text-color:var(--text); }}
  .block-container {{ padding-top:1.4rem; padding-bottom:4rem; max-width:1180px; }}
  [data-testid="stSidebar"] {{ background:var(--surface); border-right:1px solid var(--border); }}
  [data-testid="stSidebar"] *, .stApp p, .stApp label, .stApp li,
  [data-testid="stWidgetLabel"] p, [data-baseweb="tab"] {{ color:var(--text); }}
  .stApp [data-testid="stCaptionContainer"] {{ color:var(--muted) !important; }}

  /* inputs / selects / number steppers */
  .stApp [data-baseweb="input"], .stApp [data-baseweb="textarea"],
  .stApp [data-baseweb="select"] > div, .stApp [data-baseweb="base-input"] {{
      background:var(--inputbg) !important; border-color:var(--border) !important; }}
  .stApp input, .stApp textarea, .stApp [data-baseweb="select"] div {{ color:var(--text) !important; }}
  .stApp [data-testid="stNumberInput"] button {{ background:var(--inputbg) !important; border-color:var(--border) !important; color:var(--text) !important; }}

  /* secondary buttons (the primary "Find/Search" button keeps its blue accent) */
  .stApp button[kind="secondary"], .stApp [data-testid="baseButton-secondary"],
  .stApp [data-testid="stBaseButton-secondary"] {{
      background:var(--inputbg) !important; color:var(--text) !important; border-color:var(--border) !important; }}

  /* tabs + expander + dataframe container */
  .stApp [data-baseweb="tab-list"] {{ border-bottom:1px solid var(--border); background:transparent; }}
  .stApp [data-baseweb="tab"][aria-selected="true"] {{ color:var(--text); }}
  .stApp [data-testid="stExpander"] {{ background:var(--surface); border:1px solid var(--border); border-radius:12px; }}
  .stApp [data-testid="stExpander"] summary {{ color:var(--text); }}
  .stApp [data-testid="stDataFrame"], .stApp [data-testid="stDataEditor"] {{ border:1px solid var(--border); border-radius:10px; }}

  /* brand header */
  .brand {{ display:flex; align-items:center; gap:14px; margin-bottom:2px; }}
  .brand .logo {{ width:46px; height:46px; border-radius:12px; background:linear-gradient(135deg,#4f46e5,#2563eb);
                 display:flex; align-items:center; justify-content:center; font-size:24px; box-shadow:0 4px 12px rgba(37,99,235,.25); }}
  .brand h1 {{ font-size:1.55rem; font-weight:800; letter-spacing:-.02em; margin:0; color:var(--text); }}
  .brand .tag {{ color:var(--muted); font-size:.9rem; margin-top:1px; }}
  .rule {{ height:1px; background:linear-gradient(90deg,var(--rule-end),transparent); margin:14px 0 4px; }}

  /* section labels */
  .sec {{ text-transform:uppercase; letter-spacing:.07em; font-size:.72rem; font-weight:700; color:var(--faint); margin:6px 0 2px; }}

  /* generic card */
  .card {{ background:var(--surface); border:1px solid var(--border); border-radius:14px; padding:16px 18px;
          box-shadow:var(--shadow); margin-bottom:14px; }}

  /* result card */
  .rep-head {{ display:flex; align-items:flex-start; gap:14px; }}
  .rank {{ flex:0 0 auto; width:30px; height:30px; border-radius:9px; background:var(--rankbg); color:var(--ranktext);
          font-weight:800; font-size:.95rem; display:flex; align-items:center; justify-content:center; margin-top:2px; }}
  .rep-main {{ flex:1; min-width:0; }}
  .rep-name {{ font-weight:700; font-size:1.06rem; color:var(--text); }}
  .rep-sub {{ color:var(--muted); font-size:.82rem; margin:2px 0 7px; }}
  .rep-right {{ text-align:right; flex:0 0 auto; min-width:118px; }}
  .conf {{ font-size:1.6rem; font-weight:800; line-height:1; }}
  .conf-label {{ font-size:.74rem; font-weight:700; margin-top:1px; }}
  .fit {{ font-size:.72rem; color:var(--faint); margin-top:3px; }}

  .chip {{ display:inline-block; padding:2px 10px; border-radius:999px; font-size:.7rem; font-weight:700;
          background:var(--chipbg); color:var(--chiptext); margin-right:6px; }}
  .chip.pref {{ background:#4338ca; color:#fff; }}
  .chip.contract {{ background:#3730a3; color:#e0e7ff; }}
  .chip.cat {{ background:var(--chipbg); color:var(--chiptext); font-weight:600; }}

  .bars {{ margin-top:12px; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:5px 0; font-size:.78rem; }}
  .bar-label {{ flex:0 0 78px; color:var(--muted); }}
  .bar-track {{ flex:1; height:7px; background:var(--track); border-radius:5px; overflow:hidden; }}
  .bar-fill {{ height:100%; background:linear-gradient(90deg,#6366f1,#2563eb); border-radius:5px; }}
  .bar-val {{ flex:0 0 46px; text-align:right; color:var(--body); font-variant-numeric:tabular-nums; }}

  .expl {{ margin-top:13px; background:var(--expl); border-left:3px solid #2563eb; border-radius:8px;
          padding:10px 14px; color:var(--body); font-size:.9rem; line-height:1.5; }}
  .expl .ai {{ color:var(--faint); font-size:.72rem; font-weight:600; margin-left:6px; }}

  /* similar-products rows */
  .hit {{ display:flex; align-items:center; gap:14px; padding:10px 2px; border-bottom:1px solid var(--border); }}
  .hit-main {{ flex:1; min-width:0; }}
  .hit-name {{ font-weight:600; color:var(--text); }}
  .hit-track {{ flex:0 0 150px; height:7px; background:var(--track); border-radius:5px; overflow:hidden; }}
  .hit-fill {{ height:100%; background:linear-gradient(90deg,#6366f1,#2563eb); border-radius:5px; }}
  .hit-score {{ flex:0 0 44px; text-align:right; font-weight:700; color:var(--body); font-variant-numeric:tabular-nums; }}

  /* empty state */
  .empty {{ text-align:center; color:var(--faint); padding:46px 20px; border:1px dashed var(--eborder);
           border-radius:14px; background:var(--empty); }}
  .empty .big {{ font-size:30px; margin-bottom:8px; }}

  /* sidebar status dots */
  .stat {{ font-size:.9rem; margin:3px 0; color:var(--text); }}
  .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px; }}
  .dot.on {{ background:#16a34a; }} .dot.off {{ background:var(--dot-off); }}
</style>
"""


def chip(text: str, cls: str = "") -> str:
    return f'<span class="chip {cls}">{text}</span>'


def render_replacement(rep: dict, rank: int) -> str:
    color = LABEL_COLORS.get(rep.get("confidence_label", ""), "#64748b")
    price = rep.get("effective_price")
    unit = rep.get("unit") or "unit"
    sub = " · ".join(
        p for p in [
            rep.get("brand"),
            f"{price:.2f}/{unit}" if isinstance(price, (int, float)) else None,
            f"{int(rep['stock_quantity'])} in stock" if rep.get("stock_quantity") is not None else None,
        ] if p
    )
    chips = chip(rep.get("category_id", ""), "cat") if rep.get("category_id") else ""
    if rep.get("is_preferred"):
        chips += chip("★ Preferred supplier", "pref")
    elif rep.get("is_under_contract"):
        chips += chip("Under contract", "contract")

    b = rep["score_breakdown"]
    bars = "".join(
        f'<div class="bar-row"><span class="bar-label">{label}</span>'
        f'<span class="bar-track"><span class="bar-fill" style="width:{round(b[key] / mx * 100)}%"></span></span>'
        f'<span class="bar-val">{b[key]}/{mx}</span></div>'
        for key, label, mx in DIMENSIONS
    )
    ai = '<span class="ai">✨ AI-generated</span>' if rep.get("explanation_source") == "ollama" else ""
    return (
        f'<div class="card">'
        f'<div class="rep-head">'
        f'<div class="rank">{rank}</div>'
        f'<div class="rep-main"><div class="rep-name">{rep["name"]}</div>'
        f'<div class="rep-sub">{sub}</div><div>{chips}</div></div>'
        f'<div class="rep-right"><div class="conf" style="color:{color}">{rep["confidence_pct"]}%</div>'
        f'<div class="conf-label" style="color:{color}">{rep.get("confidence_label", "")} match</div>'
        f'<div class="fit">Fit score {rep["final_score"]}/93</div></div>'
        f'</div>'
        f'<div class="bars">{bars}</div>'
        f'<div class="expl">{rep["explanation"]}{ai}</div>'
        f'</div>'
    )


def render_hit(hit: dict) -> str:
    pct = round(max(0.0, min(1.0, hit.get("score", 0))) * 100)
    return (
        f'<div class="hit">'
        f'<div class="hit-main"><span class="hit-name">{hit["name"]}</span> {chip(hit.get("category_id", ""), "cat")}</div>'
        f'<span class="hit-track"><span class="hit-fill" style="width:{pct}%"></span></span>'
        f'<span class="hit-score">{hit.get("score", 0):.2f}</span>'
        f'</div>'
    )


# --------------------------------------------------------------------------- #
# Page
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Smart Substitution Engine", page_icon="🔁", layout="wide")
# Theme is driven by the sidebar toggle (read here so the whole app re-themes on flip).
st.markdown(build_css(st.session_state.get("dark_mode", False)), unsafe_allow_html=True)

if "preset" not in st.session_state:
    st.session_state.preset = next(iter(PRESETS))

st.markdown(
    '<div class="brand"><div class="logo">🔁</div>'
    '<div><h1>Smart Substitution Engine</h1>'
    '<div class="tag">AI-powered replacements for out-of-stock products</div></div></div>'
    '<div class="rule"></div>',
    unsafe_allow_html=True,
)

# ---- Sidebar ----
with st.sidebar:
    st.toggle("🌙 Dark mode", key="dark_mode", help="Switch between light and dark themes.")
    st.markdown("### Status")
    ok, health, err = api_get("/health") if "_health" not in st.session_state else st.session_state._health
    st.session_state._health = (ok, health, err)

    if not ok:
        st.markdown('<div class="stat"><span class="dot off"></span>Service offline</div>', unsafe_allow_html=True)
    else:
        emb = health.get("embeddings", {})
        vs = health.get("vector_store", {})
        ai_ready = health.get("ollama", {}).get("reachable")
        idx = vs.get("indexed_products", 0) if vs.get("available") else "—"
        rows = [
            ("on", "Service online"),
            ("on" if ai_ready else "off", "AI explanations" + ("" if ai_ready else " · standard")),
            ("on" if emb.get("available") else "off", "Semantic matching" + ("" if emb.get("available") else " · basic")),
            ("on" if vs.get("available") else "off", f"Search index · {idx} products"),
        ]
        st.markdown(
            "".join(f'<div class="stat"><span class="dot {d}"></span>{t}</div>' for d, t in rows),
            unsafe_allow_html=True,
        )

    if st.button("Refresh", use_container_width=True):
        st.session_state.pop("_health", None)
        st.rerun()

    with st.expander("Advanced"):
        st.session_state.ai_url = st.text_input("Service URL", value=_base_url())

    st.markdown('<div style="color:#94a3b8;font-size:.78rem;margin-top:18px;">Smart Substitution Engine</div>',
                unsafe_allow_html=True)

tab_reco, tab_search = st.tabs(["Replacements", "Similar products"])

# =========================================================================== #
# Tab 1 — Replacements
# =========================================================================== #
with tab_reco:
    preset_name = st.selectbox("Scenario", list(PRESETS), key="preset")
    preset = PRESETS[preset_name]

    st.markdown('<div class="sec">Out-of-stock item</div>', unsafe_allow_html=True)
    rp = preset["requested"]
    c1, c2, c3, c4 = st.columns(4)
    name = c1.text_input("Product", rp["name"], key=f"name_{preset_name}")
    category_id = c2.text_input("Category", rp["category_id"], key=f"cat_{preset_name}")
    base_price = c3.number_input("Price", value=float(rp["base_price"]), min_value=0.0, step=0.5, key=f"bp_{preset_name}")
    quantity = c4.number_input("Quantity needed", value=int(preset["quantity"]), min_value=1, step=1, key=f"qty_{preset_name}")
    c5, c6, c7 = st.columns(3)
    unit = c5.text_input("Unit", rp.get("unit") or "", key=f"unit_{preset_name}")
    pack_size = c6.number_input("Pack size", value=float(rp.get("pack_size") or 0), min_value=0.0, step=0.5, key=f"pack_{preset_name}")
    dietary = c7.text_input("Dietary tags", rp.get("dietary_tags", ""), key=f"diet_{preset_name}",
                            help="A replacement must carry ALL of these (allergen safety).")

    st.markdown('<div class="sec">Available products</div>', unsafe_allow_html=True)
    cand_df = pd.DataFrame(preset["candidates"], columns=CANDIDATE_COLUMNS)
    edited = st.data_editor(
        cand_df, num_rows="dynamic", use_container_width=True, hide_index=True, key=f"cand_{preset_name}",
        column_config={
            "id": st.column_config.TextColumn("ID", width="small"),
            "name": st.column_config.TextColumn("Product", width="medium"),
            "category_id": st.column_config.TextColumn("Category", width="small"),
            "brand": st.column_config.TextColumn("Brand", width="small"),
            "unit": st.column_config.TextColumn("Unit", width="small"),
            "pack_size": st.column_config.NumberColumn("Pack", format="%.1f", width="small"),
            "base_price": st.column_config.NumberColumn("Price", format="%.2f", width="small"),
            "stock_quantity": st.column_config.NumberColumn("Stock", format="%d", width="small"),
            "contract_price": st.column_config.NumberColumn("Contract", format="%.2f", width="small"),
            "is_preferred": st.column_config.CheckboxColumn("Preferred", width="small"),
            "is_active": st.column_config.CheckboxColumn("Active", width="small"),
            "dietary_tags": st.column_config.TextColumn("Dietary", width="small"),
        },
    )

    o1, o2, o3 = st.columns([1.2, 1.2, 1.6])
    max_results = o1.slider("Max results", 1, 10, 3)
    use_ai = o2.toggle("AI explanations", value=True, help="Off = instant rule-based explanations.")
    o3.write("")
    go = o3.button("Find replacements", type="primary", use_container_width=True)

    if go:
        candidates, contract_items = [], []
        for _, row in edited.iterrows():
            if not str(row.get("id") or "").strip():
                continue
            cand = {
                "id": row["id"], "name": row["name"], "category_id": row["category_id"],
                "brand": row.get("brand") or None, "unit": row.get("unit") or None,
                "pack_size": float(row["pack_size"]) if pd.notna(row.get("pack_size")) else None,
                "base_price": float(row["base_price"]) if pd.notna(row.get("base_price")) else 0.0,
                "stock_quantity": float(row["stock_quantity"]) if pd.notna(row.get("stock_quantity")) else 0.0,
                "contract_price": float(row["contract_price"]) if pd.notna(row.get("contract_price")) else None,
                "is_active": bool(row.get("is_active", True)),
                "dietary_tags": _split_tags(row.get("dietary_tags")),
            }
            candidates.append(cand)
            if cand["contract_price"] is not None or bool(row.get("is_preferred")):
                contract_items.append({
                    "product_id": cand["id"],
                    "contract_price": cand["contract_price"],
                    "is_preferred": bool(row.get("is_preferred")),
                })

        payload = {
            "company": {"id": "company_001", "name": "Demo Co"},
            "requested_product": {
                "id": rp["id"], "name": name, "category_id": category_id,
                "brand": rp.get("brand"), "unit": unit or None,
                "pack_size": pack_size or None, "base_price": base_price,
                "dietary_tags": _split_tags(dietary),
            },
            "requested_quantity": quantity,
            "contract_items": contract_items,
            "candidate_products": candidates,
            "max_results": max_results,
            "use_ai_explanation": use_ai,
        }
        with st.spinner("Finding the best alternatives…"):
            ok, data, err = api_post("/recommendations/replacements", payload)
        st.session_state.reco = {"ok": ok, "data": data, "err": err}

    st.markdown('<div class="sec">Recommended replacements</div>', unsafe_allow_html=True)
    reco = st.session_state.get("reco")
    if not reco:
        st.markdown('<div class="empty"><div class="big">🛒</div>Choose a scenario and select '
                    '<b>Find replacements</b> to see ranked alternatives.</div>', unsafe_allow_html=True)
    elif not reco["ok"]:
        st.error(f"Could not get recommendations. {reco['err'] or ''}")
    else:
        data = reco["data"]
        reps = data.get("replacements", [])
        if not reps:
            st.markdown(f'<div class="empty"><div class="big">🔍</div>'
                        f'{data.get("no_candidates_reason") or "No suitable replacement found."}</div>',
                        unsafe_allow_html=True)
        for i, rep in enumerate(reps, 1):
            st.markdown(render_replacement(rep, i), unsafe_allow_html=True)

        rejected = data.get("rejected_candidates", [])
        if rejected:
            with st.expander(f"Not recommended ({len(rejected)})"):
                for rc in rejected:
                    st.markdown(
                        f'**{rc["name"]}** — <span style="color:#b91c1c">{rc["rejection_reason"]}</span>',
                        unsafe_allow_html=True,
                    )

# =========================================================================== #
# Tab 2 — Similar products
# =========================================================================== #
with tab_search:
    st.markdown('<div class="sec">Find similar products</div>', unsafe_allow_html=True)
    st.caption("Search the catalog by meaning, not just keywords — great for discovering substitutes.")

    if st.button("📥 Load sample catalog", use_container_width=True):
        with st.spinner("Loading catalog…"):
            ok, data, err = api_post("/index/products", {"products": SAMPLE_CATALOG})
        if ok:
            st.session_state.pop("_health", None)
            st.success(f"Loaded {data['indexed']} products into the search index.")
        else:
            st.error("Couldn't load the catalog — the search service is unavailable.")

    q1, q2, q3 = st.columns([3, 2, 1])
    query = q1.text_input("Search for", "Chicken Breast 2kg")
    query_cat = q2.text_input("Category (optional)", "")
    top_k = q3.number_input("Results", value=5, min_value=1, max_value=20)
    active_only = st.toggle("In-stock products only", value=True)

    if st.button("Search", type="primary", use_container_width=True):
        payload = {"name": query, "top_k": int(top_k), "active_only": active_only}
        if query_cat.strip():
            payload["category_id"] = query_cat.strip()
        with st.spinner("Searching…"):
            ok, data, err = api_post("/search/similar", payload)
        st.session_state.search = {"ok": ok, "data": data, "err": err}

    search = st.session_state.get("search")
    if not search:
        st.markdown('<div class="empty"><div class="big">🔎</div>Load the sample catalog, then search '
                    'for a product to see the closest matches.</div>', unsafe_allow_html=True)
    elif not search["ok"]:
        st.error("Search is unavailable — load the sample catalog first.")
    else:
        hits = search["data"].get("results", [])
        if not hits:
            st.markdown('<div class="empty"><div class="big">🤷</div>No matches found — '
                        'load the sample catalog first.</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="card">' + "".join(render_hit(h) for h in hits) + '</div>',
                        unsafe_allow_html=True)

# =========================================================================== #
# Floating chat assistant
# Inject the self-contained widget (served by the AI service) into the parent
# document so the launcher floats over the whole app, bottom-right. It calls the
# AI service directly from the browser, so it uses the public URL + CORS.
# =========================================================================== #
st.components.v1.html(
    f"""
    <script>
    (function() {{
      var doc;
      try {{ doc = window.parent.document; }} catch (e) {{ return; }}  // cross-origin guard
      var API = '{AI_PUBLIC_URL}', SRC = API + '/chat/static/widget.js?v=6';
      function inject() {{
        var s = doc.createElement('script');
        s.id = 'sse-chat-loader';
        s.src = SRC;
        s.setAttribute('data-api', API);
        doc.body.appendChild(s);
      }}
      if (doc.getElementById('sse-chat-widget')) return;          // already mounted
      if (!doc.getElementById('sse-chat-loader')) inject();        // first load (let it finish)
      // ONE delayed retry only if the widget never appeared (e.g. AI service was
      // still warming up). No tight loop — so a slow load is never interrupted.
      setTimeout(function () {{
        if (doc.getElementById('sse-chat-widget')) return;
        var old = doc.getElementById('sse-chat-loader'); if (old) old.remove();
        try {{ window.parent.__sseChat = null; }} catch (e) {{}}
        inject();
      }}, 3000);
    }})();
    </script>
    """,
    height=0,
)
