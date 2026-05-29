"""Streamlit demo UI for the Smart Substitution Engine AI service.

Talks directly to the Python AI service (default http://localhost:8000) so it is
fully self-contained — no MongoDB / .NET backend needed for the demo.

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
TIMEOUT = 90  # LLM explanations can take a few seconds

LABEL_COLORS = {
    "Excellent": "#16a34a",
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
    ("unit_pack_similarity", "Unit/Pack", 8),
]

# --------------------------------------------------------------------------- #
# Demo data
# --------------------------------------------------------------------------- #
PRESETS: dict[str, dict] = {
    "Chicken Breast — out of stock": {
        "requested": {
            "id": "product_001", "name": "Chicken Breast 2kg", "category_id": "cat_chicken",
            "brand": "Brand A", "unit": "kg", "pack_size": 2.0, "base_price": 10.0,
            "dietary_tags": "halal",
        },
        "quantity": 20,
        "candidates": [
            {"id": "product_2033", "name": "Chicken Breast Premium 2kg", "category_id": "cat_chicken",
             "brand": "Brand B", "unit": "kg", "pack_size": 2.0, "base_price": 10.5,
             "stock_quantity": 150, "contract_price": 9.5, "is_preferred": True, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_2099", "name": "Organic Chicken Breast 2kg", "category_id": "cat_chicken",
             "brand": "Brand C", "unit": "kg", "pack_size": 2.0, "base_price": 11.0,
             "stock_quantity": 40, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": "halal,organic"},
            {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg", "category_id": "cat_poultry",
             "brand": "Brand D", "unit": "kg", "pack_size": 2.0, "base_price": 9.8,
             "stock_quantity": 80, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_5001", "name": "Pork Loin 2kg", "category_id": "cat_pork",
             "brand": "Brand X", "unit": "kg", "pack_size": 2.0, "base_price": 9.0,
             "stock_quantity": 120, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": ""},
        ],
    },
    "Halal request — allergen filter blocks pork": {
        "requested": {
            "id": "product_010", "name": "Beef Mince 1kg", "category_id": "cat_beef",
            "brand": "Brand A", "unit": "kg", "pack_size": 1.0, "base_price": 12.0,
            "dietary_tags": "halal",
        },
        "quantity": 10,
        "candidates": [
            {"id": "product_4001", "name": "Beef Sirloin 2kg", "category_id": "cat_beef",
             "brand": "Brand B", "unit": "kg", "pack_size": 2.0, "base_price": 13.0,
             "stock_quantity": 60, "contract_price": 12.5, "is_preferred": True, "is_active": True,
             "dietary_tags": "halal"},
            {"id": "product_5002", "name": "Pork Sausages 1kg", "category_id": "cat_pork",
             "brand": "Brand X", "unit": "kg", "pack_size": 1.0, "base_price": 8.0,
             "stock_quantity": 200, "contract_price": None, "is_preferred": False, "is_active": True,
             "dietary_tags": ""},
        ],
    },
}

SAMPLE_CATALOG = [
    {"id": "product_001", "name": "Chicken Breast 2kg", "category_id": "cat_chicken", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_2033", "name": "Chicken Breast Premium 2kg", "category_id": "cat_chicken", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_2099", "name": "Organic Chicken Breast 2kg", "category_id": "cat_chicken", "is_active": True, "dietary_tags": ["halal", "organic"]},
    {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg", "category_id": "cat_poultry", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_3003", "name": "Turkey Breast 2kg", "category_id": "cat_poultry", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_4001", "name": "Beef Sirloin 2kg", "category_id": "cat_beef", "is_active": True, "dietary_tags": ["halal"]},
    {"id": "product_5001", "name": "Pork Loin 2kg", "category_id": "cat_pork", "is_active": True, "dietary_tags": []},
    {"id": "product_6001", "name": "Atlantic Salmon Fillet 1kg", "category_id": "cat_fish", "is_active": True, "dietary_tags": ["pescatarian"]},
    {"id": "product_7001", "name": "Tofu Firm 500g", "category_id": "cat_plant_protein", "is_active": True, "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_7002", "name": "Plant-Based Chicken Strips 500g", "category_id": "cat_plant_protein", "is_active": True, "dietary_tags": ["vegan"]},
    {"id": "product_8001", "name": "Fresh Carrots 5kg", "category_id": "cat_vegetables", "is_active": True, "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_9002", "name": "Discontinued Chicken Nuggets 1kg", "category_id": "cat_chicken", "is_active": False, "dietary_tags": ["halal"]},
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
# UI
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="Smart Substitution Engine", page_icon="🔁", layout="wide")

# Hide Streamlit's developer chrome (Deploy button, menu, footer, status widget)
# so the app reads as a finished product rather than a dev tool.
st.markdown(
    """
    <style>
      [data-testid="stToolbar"] {visibility: hidden; height: 0; position: fixed;}
      [data-testid="stDecoration"] {display: none;}
      [data-testid="stStatusWidget"] {display: none;}
      #MainMenu {visibility: hidden;}
      footer {visibility: hidden;}
    </style>
    """,
    unsafe_allow_html=True,
)

if "preset" not in st.session_state:
    st.session_state.preset = next(iter(PRESETS))

st.title("🔁 Smart Substitution Engine")
st.caption("AI-powered product replacement — instantly ranks the best available alternatives when an item is out of stock.")

# ---- Sidebar: connection + health ----
with st.sidebar:
    st.header("Status")
    st.session_state.ai_url = st.text_input("Service URL", value=_base_url())
    if st.button("Refresh", use_container_width=True):
        st.session_state.pop("_health", None)
    if "_health" not in st.session_state:
        ok, data, err = api_get("/health")
        st.session_state._health = (ok, data, err)
    ok, health, err = st.session_state._health

    if not ok:
        st.error("● Service offline")
    else:
        emb = health.get("embeddings", {})
        vs = health.get("vector_store", {})
        ai_ready = health.get("ollama", {}).get("reachable")
        st.success("● Service online")
        st.markdown(
            f"- **AI explanations**: {'🟢 Ready' if ai_ready else '⚪ Standard'}\n"
            f"- **Semantic matching**: {'🟢 Ready' if emb.get('available') else '⚪ Basic'}\n"
            f"- **Search index**: {vs.get('indexed_products', 0) if vs.get('available') else '—'} products"
        )
    st.divider()
    st.caption("Smart Substitution Engine")

tab_reco, tab_search = st.tabs(["🔁 Replacements", "🔍 Vector Search"])

# =========================================================================== #
# Tab 1 — Replacements
# =========================================================================== #
with tab_reco:
    preset_name = st.selectbox("Scenario", list(PRESETS), key="preset")
    preset = PRESETS[preset_name]

    st.subheader("Out-of-stock product")
    rp = preset["requested"]
    c1, c2, c3, c4 = st.columns(4)
    name = c1.text_input("Name", rp["name"], key=f"name_{preset_name}")
    category_id = c2.text_input("Category", rp["category_id"], key=f"cat_{preset_name}")
    base_price = c3.number_input("Base price", value=float(rp["base_price"]), min_value=0.0, step=0.5, key=f"bp_{preset_name}")
    quantity = c4.number_input("Quantity needed", value=int(preset["quantity"]), min_value=1, step=1, key=f"qty_{preset_name}")
    c5, c6, c7 = st.columns(3)
    unit = c5.text_input("Unit", rp.get("unit") or "", key=f"unit_{preset_name}")
    pack_size = c6.number_input("Pack size", value=float(rp.get("pack_size") or 0), min_value=0.0, step=0.5, key=f"pack_{preset_name}")
    dietary = c7.text_input("Dietary tags (comma-sep)", rp.get("dietary_tags", ""), key=f"diet_{preset_name}",
                            help="A replacement must carry ALL of these (allergen safety).")

    st.subheader("Candidate products")
    st.caption("Edit freely — add/remove rows. Rows with a contract price or 'preferred' feed the contract scoring.")
    cand_df = pd.DataFrame(preset["candidates"], columns=CANDIDATE_COLUMNS)
    edited = st.data_editor(
        cand_df, num_rows="dynamic", use_container_width=True, key=f"cand_{preset_name}",
        column_config={
            "base_price": st.column_config.NumberColumn(format="%.2f"),
            "contract_price": st.column_config.NumberColumn(format="%.2f"),
            "is_preferred": st.column_config.CheckboxColumn(),
            "is_active": st.column_config.CheckboxColumn(),
        },
    )

    o1, o2, _ = st.columns([1, 1, 2])
    max_results = o1.slider("Max results", 1, 10, 3)
    use_ai = o2.toggle("AI explanations", value=True,
                       help="Off = instant rule-based explanations.")

    if st.button("🔎 Find replacements", type="primary", use_container_width=True):
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

        with st.spinner("Scoring candidates…"):
            ok, data, err = api_post("/recommendations/replacements", payload)
        if not ok:
            st.error(f"Request failed: {err}")
        else:
            reps = data.get("replacements", [])
            if not reps:
                st.warning(data.get("no_candidates_reason") or "No suitable replacement found.")
            for i, rep in enumerate(reps, 1):
                with st.container(border=True):
                    head, score = st.columns([4, 1])
                    color = LABEL_COLORS.get(rep["confidence_label"], "#666")
                    chips = ""
                    if rep.get("is_preferred"):
                        chips += " &nbsp;<span style='background:#1e293b;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75em'>preferred</span>"
                    elif rep.get("is_under_contract"):
                        chips += " &nbsp;<span style='background:#334155;color:#fff;padding:2px 8px;border-radius:10px;font-size:0.75em'>under contract</span>"
                    head.markdown(
                        f"#### {i}. {rep['name']}  \n"
                        f"<span style='background:{color};color:#fff;padding:2px 10px;border-radius:10px'>"
                        f"{rep['confidence_label']} · {rep['confidence_pct']}%</span>{chips}",
                        unsafe_allow_html=True,
                    )
                    score.metric("Score", f"{rep['final_score']}/93")
                    b = rep["score_breakdown"]
                    cols = st.columns(len(DIMENSIONS))
                    for col, (key, label, mx) in zip(cols, DIMENSIONS):
                        val = b[key]
                        col.progress(int(val / mx * 100), text=f"{label} {val}/{mx}")
                    tag = (
                        "<small style='opacity:0.55'>✨ AI-generated</small>"
                        if rep.get("explanation_source") == "ollama"
                        else ""
                    )
                    st.markdown(f"💬 *{rep['explanation']}* &nbsp; {tag}", unsafe_allow_html=True)

            rejected = data.get("rejected_candidates", [])
            if rejected:
                with st.expander(f"🚫 Rejected candidates ({len(rejected)})"):
                    st.dataframe(pd.DataFrame(rejected), use_container_width=True, hide_index=True)

# =========================================================================== #
# Tab 2 — Similar products
# =========================================================================== #
with tab_search:
    st.subheader("Find similar products")
    st.caption("Search the catalog by meaning, not just keywords — great for discovering substitutes.")

    if st.button("📥 Load sample catalog", use_container_width=True):
        with st.spinner("Loading…"):
            ok, data, err = api_post("/index/products", {"products": SAMPLE_CATALOG})
        if ok:
            st.success(f"Loaded {data['indexed']} products into the search index.")
            st.session_state.pop("_health", None)
        else:
            st.error("Couldn't load the catalog — the search service is unavailable.")

    st.divider()
    q1, q2, q3 = st.columns([3, 2, 1])
    query = q1.text_input("Find products similar to…", "Chicken Breast 2kg")
    query_cat = q2.text_input("Restrict to category (optional)", "")
    top_k = q3.number_input("Top K", value=5, min_value=1, max_value=20)
    active_only = st.toggle("Active products only", value=True)

    if st.button("🔍 Search", type="primary", use_container_width=True):
        payload = {"name": query, "top_k": int(top_k), "active_only": active_only}
        if query_cat.strip():
            payload["category_id"] = query_cat.strip()
        with st.spinner("Searching…"):
            ok, data, err = api_post("/search/similar", payload)
        if not ok:
            st.error("Search is unavailable — load the sample catalog first.")
        else:
            hits = data.get("results", [])
            if not hits:
                st.info("No matches found — load the sample catalog first.")
            for h in hits:
                c1, c2 = st.columns([4, 1])
                c1.progress(h["score"], text=f"{h['name']}  ·  [{h['category_id']}]")
                c2.markdown(f"**{h['score']:.3f}**")
