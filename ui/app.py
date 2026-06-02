"""Smart Substitution Engine — demo UI (Streamlit).

Tab 1 – Replacements: searches the real MongoDB catalog via the .NET backend,
         lets the user pick an out-of-stock product by contract number, then
         calls POST /recommendations/replacements on the backend.
Tab 2 – Similar products: semantic vector search via the Python AI service.

Run locally:
    cd ui && pip install -r requirements.txt
    BACKEND_URL=http://localhost:8080 AI_SERVICE_URL=http://localhost:8000 streamlit run app.py
"""

from __future__ import annotations

import os
import requests
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://localhost:8080").rstrip("/")
AI_URL_DEFAULT      = os.environ.get("AI_SERVICE_URL", "http://localhost:8000").rstrip("/")
# Browser-reachable AI URL for the floating chat widget. The user's browser calls
# it directly, so it must NOT be an in-cluster hostname like "ai-service".
AI_PUBLIC_URL       = os.environ.get("AI_PUBLIC_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 90

LABEL_COLORS = {
    "Excellent": "#15803d",
    "Strong":    "#2563eb",
    "Good":      "#0891b2",
    "Fair":      "#d97706",
    "Weak":      "#dc2626",
}

# Keys match the camelCase .NET backend response
DIMENSIONS = [
    ("categorySimilarity", "Category",   30),
    ("contractMatch",      "Contract",   25),
    ("priceSimilarity",    "Price",      20),
    ("stockAvailability",  "Stock",      10),
    ("unitPackSimilarity", "Unit / pack", 8),
]

# ── API helpers ───────────────────────────────────────────────────────────────

def _backend() -> str:
    return st.session_state.get("backend_url", BACKEND_URL_DEFAULT).rstrip("/")

def _ai() -> str:
    return st.session_state.get("ai_url", AI_URL_DEFAULT).rstrip("/")

def _get(base: str, path: str, timeout: int = 10):
    try:
        r = requests.get(base + path, timeout=timeout)
        return r.ok, (r.json() if r.content else {}), None
    except Exception as exc:
        return False, None, str(exc)

def _post(base: str, path: str, payload: dict):
    try:
        r = requests.post(base + path, json=payload, timeout=TIMEOUT)
        data = r.json() if r.content else {}
        if not r.ok:
            return False, None, f"HTTP {r.status_code}: {data.get('detail', data)}"
        return True, data, None
    except Exception as exc:
        return False, None, str(exc)

def backend_get(path: str, timeout: int = 10):
    return _get(_backend(), path, timeout)

def backend_post(path: str, payload: dict):
    return _post(_backend(), path, payload)

def ai_get(path: str):
    return _get(_ai(), path)

def ai_post(path: str, payload: dict):
    return _post(_ai(), path, payload)

def catalog_search(query: str, contracts: list[str], limit: int = 12):
    cn = ",".join(contracts)
    return backend_get(f"/catalog/search?q={requests.utils.quote(query)}&contracts={cn}&limit={limit}", timeout=15)

# ── CSS / theming ───────────────────────────────────────────────────────────────

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

  /* catalog product card (selected out-of-stock item) */
  .pcard {{ background:var(--expl); border:1px solid var(--border); border-radius:10px; padding:12px 16px;
           font-size:.88rem; color:var(--body); line-height:1.7; }}
  .pcard .pid {{ font-family:monospace; background:var(--rankbg); color:var(--ranktext); padding:1px 6px; border-radius:4px;
                font-size:.8rem; margin-right:6px; }}
  .pcard .plabel {{ color:var(--faint); font-size:.75rem; margin-right:4px; }}

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
  .chip.contract {{ background:#3730a3; color:#e0e7ff; }}
  .chip.cat {{ background:var(--chipbg); color:var(--chiptext); font-weight:600; }}

  .bars {{ margin-top:12px; }}
  .bar-row {{ display:flex; align-items:center; gap:10px; margin:5px 0; font-size:.78rem; }}
  .bar-label {{ flex:0 0 78px; color:var(--muted); }}
  .bar-track {{ flex:1; height:7px; background:var(--track); border-radius:5px; overflow:hidden; }}
  .bar-fill {{ display:block; height:100%; background:linear-gradient(90deg,#6366f1,#2563eb); border-radius:5px; }}
  .bar-val {{ flex:0 0 46px; text-align:right; color:var(--body); font-variant-numeric:tabular-nums; }}

  .expl {{ margin-top:13px; background:var(--expl); border-left:3px solid #2563eb; border-radius:8px;
          padding:10px 14px; color:var(--body); font-size:.9rem; line-height:1.5; }}

  /* similar-products rows */
  .hit {{ display:flex; align-items:center; gap:14px; padding:10px 2px; border-bottom:1px solid var(--border); }}
  .hit-main {{ flex:1; min-width:0; }}
  .hit-name {{ font-weight:600; color:var(--text); }}
  .hit-track {{ flex:0 0 150px; height:7px; background:var(--track); border-radius:5px; overflow:hidden; }}
  .hit-fill {{ display:block; height:100%; background:linear-gradient(90deg,#6366f1,#2563eb); border-radius:5px; }}
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

# ── Render helpers ─────────────────────────────────────────────────────────────

def chip(text: str, cls: str = "") -> str:
    return f'<span class="chip {cls}">{text}</span>'

def render_replacement(rep: dict, rank: int) -> str:
    label  = rep.get("confidenceLabel", "")
    color  = LABEL_COLORS.get(label, "#64748b")
    pct    = rep.get("confidencePct", 0)
    score  = rep.get("finalScore", 0)
    b      = rep.get("scoreBreakdown", {})
    bars   = "".join(
        f'<div class="bar-row"><span class="bar-label">{lbl}</span>'
        f'<span class="bar-track"><span class="bar-fill" style="width:{round(b.get(key,0)/mx*100)}%"></span></span>'
        f'<span class="bar-val">{b.get(key,0)}/{mx}</span></div>'
        for key, lbl, mx in DIMENSIONS
    )
    return (
        f'<div class="card">'
        f'<div class="rep-head">'
        f'<div class="rank">{rank}</div>'
        f'<div class="rep-main">'
        f'<div class="rep-name">{rep.get("name","")}</div>'
        f'<div class="rep-sub">{chip(rep.get("productId",""), "contract")}</div>'
        f'</div>'
        f'<div class="rep-right">'
        f'<div class="conf" style="color:{color}">{pct}%</div>'
        f'<div class="conf-label" style="color:{color}">{label} match</div>'
        f'<div class="fit">Fit score {score}/93</div>'
        f'</div></div>'
        f'<div class="bars">{bars}</div>'
        f'<div class="expl">{rep.get("explanation","")}</div>'
        f'</div>'
    )

def render_product_card(p: dict) -> str:
    cu = next((pt for pt in p.get("partTypes", []) if pt.get("code") == "CU"), None)
    tu = next((pt for pt in p.get("partTypes", []) if pt.get("code") == "TU"), None)
    pt = cu or tu
    price = pt["price"].get("unitPrice", "—") if pt else "—"
    unit  = pt.get("unit", "") if pt else ""
    cats  = " ".join(chip(c, "cat") for c in (p.get("catalogCategories") or [])[:2])
    return (
        f'<div class="pcard">'
        f'<span class="pid">{p.get("itemNumber","")}</span>'
        f'<strong>{p.get("name","")}</strong><br>'
        f'<span class="plabel">Seller</span>{p.get("sellerName","")} &nbsp;'
        f'<span class="plabel">Contract</span>{p.get("contractNumber","")} &nbsp;'
        f'<span class="plabel">Seller #</span>{p.get("sellerAccountNumber","")} &nbsp;'
        f'<span class="plabel">Price</span>{price} {unit}'
        f'<div style="margin-top:5px">{cats}</div>'
        f'</div>'
    )

def render_hit(hit: dict) -> str:
    pct = round(max(0.0, min(1.0, hit.get("score", 0))) * 100)
    return (
        f'<div class="hit">'
        f'<div class="hit-main"><span class="hit-name">{hit["name"]}</span> {chip(hit.get("category_id",""),"cat")}</div>'
        f'<span class="hit-track"><span class="hit-fill" style="width:{pct}%"></span></span>'
        f'<span class="hit-score">{hit.get("score",0):.2f}</span>'
        f'</div>'
    )

# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Smart Substitution Engine", page_icon="🔁", layout="wide")
# Theme is driven by the sidebar toggle (read here so the whole app re-themes on flip).
st.markdown(build_css(st.session_state.get("dark_mode", False)), unsafe_allow_html=True)
st.markdown(
    '<div class="brand"><div class="logo">🔁</div>'
    '<div><h1>Smart Substitution Engine</h1>'
    '<div class="tag">AI-powered replacements for out-of-stock products</div></div></div>'
    '<div class="rule"></div>',
    unsafe_allow_html=True,
)

# ── Sidebar ───────────────────────────────────────────────────────────────────

with st.sidebar:
    st.toggle("🌙 Dark mode", key="dark_mode", help="Switch between light and dark themes.")
    st.markdown("### Status")

    if "_health_backend" not in st.session_state:
        st.session_state._health_backend = backend_get("/health")
    if "_health_ai" not in st.session_state:
        st.session_state._health_ai = ai_get("/health")

    ok_b, h_b, _ = st.session_state._health_backend
    ok_a, h_a, _ = st.session_state._health_ai
    db_ok  = ok_b and h_b and h_b.get("status") == "ok"
    emb_ok = ok_a and h_a and h_a.get("embeddings", {}).get("available")
    ai_ok  = ok_a and h_a and h_a.get("ollama", {}).get("reachable")
    vs     = h_a.get("vector_store", {}) if h_a else {}
    idx    = vs.get("indexed_products", 0) if vs.get("available") else "—"

    st.markdown("".join(
        f'<div class="stat"><span class="dot {"on" if ok else "off"}"></span>{label}</div>'
        for ok, label in [
            (db_ok,  "Backend + database"),
            (ai_ok,  "AI explanations" + ("" if ai_ok else " · template fallback")),
            (emb_ok, "Semantic matching" + ("" if emb_ok else " · basic")),
            (ok_a,   f"Search index · {idx} products"),
        ]
    ), unsafe_allow_html=True)

    if st.button("Refresh", use_container_width=True):
        for k in ("_health_backend", "_health_ai"):
            st.session_state.pop(k, None)
        st.rerun()

    with st.expander("Advanced"):
        st.session_state.backend_url = st.text_input("Backend URL",  value=_backend())
        st.session_state.ai_url      = st.text_input("AI service URL", value=_ai())

    st.markdown(
        '<div style="color:#94a3b8;font-size:.78rem;margin-top:18px;">Smart Substitution Engine · demo</div>',
        unsafe_allow_html=True,
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_reco, tab_search = st.tabs(["Replacements", "Similar products"])

# =========================================================================== #
# Tab 1 — Replacements
# =========================================================================== #
with tab_reco:

    # ── Step 1: Contract numbers ──────────────────────────────────────────────
    st.markdown('<div class="sec">Step 1 — Your contract numbers</div>', unsafe_allow_html=True)
    contracts_input = st.text_input(
        "Contract numbers (comma-separated)",
        value=st.session_state.get("contracts_input", "3177"),
        placeholder="e.g. 3177, 1396, 1405",
        help="The catalogs you have access to. Candidates will only come from these contracts.",
        label_visibility="collapsed",
    )
    st.session_state.contracts_input = contracts_input
    contract_numbers = [c.strip() for c in contracts_input.split(",") if c.strip()]

    # ── Step 2: Find the out-of-stock product ────────────────────────────────
    st.markdown('<div class="sec">Step 2 — Search for the out-of-stock product</div>', unsafe_allow_html=True)

    s1, s2 = st.columns([4, 1])
    search_query = s1.text_input("Product name", value=st.session_state.get("search_query", ""),
                                  placeholder="e.g. appelsin, kylling, laks…", label_visibility="collapsed")
    search_go = s2.button("Search catalog", use_container_width=True, disabled=not contract_numbers)

    if search_go and search_query.strip():
        with st.spinner("Searching catalog…"):
            ok, data, err = catalog_search(search_query.strip(), contract_numbers)
        if ok and data:
            st.session_state.catalog_results = data
            st.session_state.selected_product = None
        else:
            st.error(f"Search failed: {err or 'no results'}")
            st.session_state.catalog_results = []

    results = st.session_state.get("catalog_results", [])
    if results:
        options = {
            f"[{p.get('contractNumber')}]  {p.get('name','')}  ({p.get('itemNumber','')})": p
            for p in results
        }
        chosen_label = st.selectbox(
            f"{len(results)} product(s) found — select the out-of-stock one:",
            list(options.keys()),
            key="product_select",
        )
        chosen = options[chosen_label]
        st.session_state.selected_product = chosen
        st.markdown(render_product_card(chosen), unsafe_allow_html=True)

    selected = st.session_state.get("selected_product")

    # ── Step 3: Request details ───────────────────────────────────────────────
    st.markdown('<div class="sec">Step 3 — Request details</div>', unsafe_allow_html=True)
    o1, o2, o3 = st.columns([1.5, 1.5, 2])
    quantity    = o1.number_input("Quantity needed", value=10, min_value=1, step=1)
    max_results = o2.slider("Max results", 1, 10, 3)
    use_ai      = o3.toggle("AI explanations", value=True,
                            help="Off = instant rule-based explanations.")

    go = st.button(
        "Find replacements",
        type="primary",
        use_container_width=True,
        disabled=selected is None or not contract_numbers,
    )

    if go and selected:
        payload = {
            "product": {
                "itemNumber":          selected["itemNumber"],
                "sellerAccountNumber": selected["sellerAccountNumber"],
                "contractNumber":      selected["contractNumber"],
            },
            "contractNumbers":  contract_numbers,
            "requestedQuantity": quantity,
            "maxResults":        max_results,
            "useAiExplanation":  use_ai,
        }
        with st.spinner("Finding the best alternatives…"):
            ok, data, err = backend_post("/recommendations/replacements", payload)
        st.session_state.reco = {"ok": ok, "data": data, "err": err}

    # ── Results ───────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Recommended replacements</div>', unsafe_allow_html=True)
    reco = st.session_state.get("reco")
    if not reco:
        st.markdown(
            '<div class="empty"><div class="big">🛒</div>'
            'Search for a product, select it, then click <b>Find replacements</b>.</div>',
            unsafe_allow_html=True,
        )
    elif not reco["ok"]:
        st.error(f"Could not get recommendations. {reco['err'] or ''}")
    else:
        data = reco["data"]
        if not data.get("replacementNeeded"):
            st.success("Product is in stock — no replacement needed.")
        else:
            reps = data.get("replacements") or []
            if not reps:
                reason = data.get("noCandidatesReason") or "No suitable replacement found."
                st.markdown(
                    f'<div class="empty"><div class="big">🔍</div>{reason}</div>',
                    unsafe_allow_html=True,
                )
            for i, rep in enumerate(reps, 1):
                st.markdown(render_replacement(rep, i), unsafe_allow_html=True)

            rejected = data.get("rejectedCandidates") or []
            if rejected:
                with st.expander(f"Not recommended ({len(rejected)})"):
                    for rc in rejected:
                        st.markdown(
                            f'**{rc.get("name",rc.get("productId",""))}** — '
                            f'<span style="color:#b91c1c">{rc.get("rejectionReason","")}</span>',
                            unsafe_allow_html=True,
                        )

# =========================================================================== #
# Tab 2 — Similar products (Python AI service — unchanged flow)
# =========================================================================== #
SAMPLE_CATALOG = [
    {"id": "product_001",  "name": "Chicken Breast 2kg",              "category_id": "chicken",      "is_active": True,  "dietary_tags": ["halal"]},
    {"id": "product_2033", "name": "Chicken Breast Premium 2kg",      "category_id": "chicken",      "is_active": True,  "dietary_tags": ["halal"]},
    {"id": "product_2099", "name": "Organic Chicken Breast 2kg",      "category_id": "chicken",      "is_active": True,  "dietary_tags": ["halal", "organic"]},
    {"id": "product_3001", "name": "Chicken Thigh Fillet 2kg",        "category_id": "poultry",      "is_active": True,  "dietary_tags": ["halal"]},
    {"id": "product_3003", "name": "Turkey Breast 2kg",               "category_id": "poultry",      "is_active": True,  "dietary_tags": ["halal"]},
    {"id": "product_4001", "name": "Beef Sirloin 2kg",                "category_id": "beef",         "is_active": True,  "dietary_tags": ["halal"]},
    {"id": "product_5001", "name": "Pork Loin 2kg",                   "category_id": "pork",         "is_active": True,  "dietary_tags": []},
    {"id": "product_6001", "name": "Atlantic Salmon Fillet 1kg",      "category_id": "fish",         "is_active": True,  "dietary_tags": ["pescatarian"]},
    {"id": "product_7001", "name": "Tofu Firm 500g",                  "category_id": "plant_protein","is_active": True,  "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_7002", "name": "Plant-Based Chicken Strips 500g", "category_id": "plant_protein","is_active": True,  "dietary_tags": ["vegan"]},
    {"id": "product_8001", "name": "Fresh Carrots 5kg",               "category_id": "vegetables",   "is_active": True,  "dietary_tags": ["vegan", "gluten_free"]},
    {"id": "product_9002", "name": "Discontinued Chicken Nuggets 1kg","category_id": "chicken",      "is_active": False, "dietary_tags": ["halal"]},
]

with tab_search:
    st.markdown('<div class="sec">Find similar products</div>', unsafe_allow_html=True)
    st.caption("Semantic vector search — finds products by meaning, not just keywords.")

    if st.button("📥 Load sample catalog", use_container_width=True):
        with st.spinner("Loading catalog into search index…"):
            ok, data, err = ai_post("/index/products", {"products": SAMPLE_CATALOG})
        if ok:
            st.session_state.pop("_health_ai", None)
            st.success(f"Loaded {data['indexed']} products into the search index.")
        else:
            st.error("Couldn't load the catalog — AI search service unavailable.")

    q1, q2, q3 = st.columns([3, 2, 1])
    query     = q1.text_input("Search for", "Chicken Breast 2kg")
    query_cat = q2.text_input("Category (optional)", "")
    top_k     = q3.number_input("Results", value=5, min_value=1, max_value=20)
    active_only = st.toggle("In-stock products only", value=True)

    if st.button("Search", type="primary", use_container_width=True):
        payload = {"name": query, "top_k": int(top_k), "active_only": active_only}
        if query_cat.strip():
            payload["category_id"] = query_cat.strip()
        with st.spinner("Searching…"):
            ok, data, err = ai_post("/search/similar", payload)
        st.session_state.sim_search = {"ok": ok, "data": data, "err": err}

    sim = st.session_state.get("sim_search")
    if not sim:
        st.markdown(
            '<div class="empty"><div class="big">🔎</div>'
            'Load the sample catalog, then search for a product.</div>',
            unsafe_allow_html=True,
        )
    elif not sim["ok"]:
        st.error("Search unavailable — load the sample catalog first.")
    else:
        hits = sim["data"].get("results", [])
        if not hits:
            st.markdown(
                '<div class="empty"><div class="big">🤷</div>No matches found.</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="card">' + "".join(render_hit(h) for h in hits) + '</div>',
                unsafe_allow_html=True,
            )

# =========================================================================== #
# Floating chat assistant
# Inject the self-contained widget (served by the AI service) into the parent
# document so the launcher floats over the whole app, bottom-right. It calls the
# AI service directly from the browser, so it uses the public URL + CORS.
#
# NB: st.components.v1.html is required here (not st.iframe / st.html): we need an
# iframe whose inline script reaches window.parent.document to mount a *floating*
# launcher. st.iframe only takes a URL (would box the chat inline) and st.html
# doesn't execute <script>. Streamlit marks v1.html deprecated — keep an eye on it
# on major Streamlit upgrades.
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
