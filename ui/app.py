"""Smart Substitution Engine - demo UI (Streamlit), cisbox design.

Tab 1 – Replacements: searches the real MongoDB catalog via the .NET backend,
         lets the user pick an out-of-stock product by contract number, then
         calls POST /recommendations/replacements on the backend. Results show in
         three layouts (Cards / Compare / Swap).
Tab 2 – Similar products: semantic vector search via the Python AI service.

Visual language follows the cisbox "Global UI Components (Web)" design system:
forest-green brand (#215B33), Roboto, 8px radii, light-green nav rail + topbar,
border-forward surfaces. A dark variant keeps the same brand accent. The data
flow (contract numbers → catalog search → pick out-of-stock product → find
replacements) is unchanged.

Run locally:
    cd ui && pip install -r requirements.txt
    BACKEND_URL=http://localhost:8080 AI_SERVICE_URL=http://localhost:8000 streamlit run app.py
"""

from __future__ import annotations

import html
import math
import os
import time
import requests
import streamlit as st

# ── Config ────────────────────────────────────────────────────────────────────

BACKEND_URL_DEFAULT = os.environ.get("BACKEND_URL", "http://localhost:8080").rstrip("/")
AI_URL_DEFAULT      = os.environ.get("AI_SERVICE_URL", "http://localhost:8000").rstrip("/")
# Browser-reachable AI URL for the floating chat widget. The user's browser calls
# it directly, so it must NOT be an in-cluster hostname like "ai-service".
AI_PUBLIC_URL       = os.environ.get("AI_PUBLIC_URL", "http://localhost:8000").rstrip("/")
TIMEOUT = 90

# Quality-label colour → theme-aware CSS variable (adapts to light/dark).
LABEL_COLORS = {
    "Excellent": "var(--success-text)",
    "Strong":    "var(--accent-text)",
    "Good":      "var(--accent-text)",
    "Fair":      "var(--warn)",
    "Weak":      "var(--danger)",
}

# Keys match the camelCase .NET backend response; maxes sum to 93 (real weights).
DIMENSIONS = [
    ("categorySimilarity", "Product match",       30),
    ("contractMatch",      "Supplier & contract", 25),
    ("priceSimilarity",    "Price",               20),
    ("stockAvailability",  "Availability",        10),
    ("unitPackSimilarity", "Unit / pack",          8),
]
FIT_MAX = sum(mx for _, _, mx in DIMENSIONS)  # 93

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

# ── Demo sample catalog ─────────────────────────────────────────────────────────
# The .NET catalog Mongo is not provisioned in this environment (LocalMongoDB has
# no connection string → /catalog/search returns 500). So when the real catalog
# search yields nothing, the Replacements flow falls back to this built-in sample
# catalog and asks the LIVE Python AI engine (:8000) to rank the alternatives -
# a fully working demo with no backend/infra changes.

SAMPLE_CONTRACT = "3177"

def _p(item, name, brand, cat, label, price, pack, stock, cprice=None, pref=False, unit="kg"):
    """Build a sample product in the .NET catalog shape (+ helper _* keys for the AI)."""
    return {
        "itemNumber": item, "name": name, "sellerName": brand,
        "sellerAccountNumber": f"S-{SAMPLE_CONTRACT}-01", "contractNumber": SAMPLE_CONTRACT,
        "catalogCategories": [label],
        "partTypes": [{"code": "CU", "unit": unit, "price": {"unitPrice": price}}],
        "_demo": True, "_cat": cat, "_brand": brand, "_unit": unit, "_pack": pack,
        "_price": price, "_stock": stock, "_cprice": cprice, "_pref": pref,
    }

SAMPLE_CATALOG = [
    # - Kylling (chicken) -
    _p("K-100", "Kyllingfilet 2,5 kg",            "Prior Norge",      "kylling", "Kylling", 98.5, 2.5,   0),
    _p("K-101", "Kyllingfilet Premium 2,5 kg",    "Prior Norge",      "kylling", "Kylling", 95.0, 2.5, 150, cprice=92.0, pref=True),
    _p("K-102", "Økologisk kyllingfilet 2 kg",    "Norsk Kylling",    "kylling", "Kylling", 112.0, 2.0,  40),
    _p("K-103", "Kyllingbryst 5 kg",              "Prior Norge",      "kylling", "Kylling", 178.0, 5.0,  60, cprice=170.0),
    _p("K-104", "Kyllinglårfilet 2 kg",           "Den Stolte Hane",  "kylling", "Kylling", 86.0, 2.0,   90),
    # - Laks (salmon) -
    _p("L-200", "Laksefilet 1 kg",                "Salmar",           "laks", "Laks", 169.0, 1.0,   0),
    _p("L-201", "Laksefilet porsjon 1 kg",        "Lerøy",            "laks", "Laks", 175.0, 1.0,  80, cprice=162.0, pref=True),
    _p("L-202", "Økologisk laksefilet 1 kg",      "Lerøy",            "laks", "Laks", 199.0, 1.0,  25),
    _p("L-203", "Ørretfilet 1 kg",                "Salmar",           "laks", "Laks", 159.0, 1.0,  55),
    # - Frukt (orange / citrus) -
    _p("F-300", "Appelsin 10 kg",                 "Bama",             "frukt", "Frukt", 240.0, 10.0,  0),
    _p("F-301", "Appelsin Navel 10 kg",           "Bama",             "frukt", "Frukt", 250.0, 10.0, 120, cprice=232.0, pref=True),
    _p("F-302", "Økologisk appelsin 8 kg",        "Bama",             "frukt", "Frukt", 262.0, 8.0,  30),
    _p("F-303", "Klementin 5 kg",                 "Bama",             "frukt", "Frukt", 178.0, 5.0,  70),
]

def demo_search(query: str) -> list[dict]:
    q = query.strip().lower()
    return [p for p in SAMPLE_CATALOG if q in p["name"].lower() or q in p["_cat"]]

def _ai_product(p: dict, candidate: bool = False) -> dict:
    d = {"id": p["itemNumber"], "name": p["name"], "category_id": p["_cat"], "brand": p["_brand"],
         "unit": p["_unit"], "pack_size": p["_pack"], "base_price": p["_price"], "dietary_tags": []}
    if candidate:
        d.update(stock_quantity=p["_stock"], contract_price=p["_cprice"], is_active=True)
    return d

def demo_recommend(selected: dict, quantity: int, max_results: int, use_ai: bool):
    """Score the sample same-category alternatives with the live Python AI engine."""
    cands = [p for p in SAMPLE_CATALOG
             if p["_cat"] == selected.get("_cat") and p["itemNumber"] != selected.get("itemNumber")]
    contract_items = [{"product_id": c["itemNumber"], "contract_price": c["_cprice"], "is_preferred": c["_pref"]}
                      for c in cands if c["_cprice"] is not None or c["_pref"]]
    payload = {
        "company": {"id": selected.get("contractNumber", SAMPLE_CONTRACT), "name": "Demo"},
        "requested_product": _ai_product(selected),
        "requested_quantity": quantity,
        "contract_items": contract_items,
        "candidate_products": [_ai_product(c, candidate=True) for c in cands],
        "max_results": max_results,
        "use_ai_explanation": use_ai,
    }
    return ai_post("/recommendations/replacements", payload)

def map_ai_reco(data: dict) -> dict:
    """Map the AI service's snake_case response → the camelCase shape the cards render."""
    def m(r):
        sb = r.get("score_breakdown", {}) or {}
        return {
            "productId": r.get("product_id", ""), "name": r.get("name", ""),
            "finalScore": r.get("final_score", 0), "confidencePct": r.get("confidence_pct", 0),
            "confidenceLabel": r.get("confidence_label", ""),
            "scoreBreakdown": {
                "categorySimilarity": sb.get("category_similarity", 0),
                "contractMatch": sb.get("contract_match", 0),
                "priceSimilarity": sb.get("price_similarity", 0),
                "stockAvailability": sb.get("stock_availability", 0),
                "unitPackSimilarity": sb.get("unit_pack_similarity", 0),
            },
            "explanation": r.get("explanation", ""),
        }
    return {
        "replacementNeeded": data.get("replacement_needed", True),
        "replacements": [m(r) for r in (data.get("replacements") or [])],
        "rejectedCandidates": [{"productId": rc.get("product_id", ""), "name": rc.get("name", ""),
                                "rejectionReason": rc.get("rejection_reason", "")}
                               for rc in (data.get("rejected_candidates") or [])],
        "noCandidatesReason": data.get("no_candidates_reason"),
    }

def esc(value) -> str:
    return html.escape(str(value if value is not None else ""))

def catalog_price(p: dict):
    """Return (price, unit) from a catalog product's part types (CU preferred)."""
    cu = next((pt for pt in p.get("partTypes", []) if pt.get("code") == "CU"), None)
    tu = next((pt for pt in p.get("partTypes", []) if pt.get("code") == "TU"), None)
    pt = cu or tu
    price = pt["price"].get("unitPrice", "-") if pt and pt.get("price") else "-"
    unit  = pt.get("unit", "") if pt else ""
    return price, unit

# ── Inline icons (currentColor; no emoji, per cisbox guidelines) ────────────────

_SW = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
ICON_SWAP  = f'<svg viewBox="0 0 24 24" width="100%" height="100%" {_SW}><path d="M16 3l4 4-4 4"/><path d="M20 7H4"/><path d="M8 21l-4-4 4-4"/><path d="M4 17h16"/></svg>'
ICON_WARN  = f'<svg viewBox="0 0 24 24" width="100%" height="100%" {_SW}><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>'
ICON_CHECK = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>'
ICON_CHEV  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="m6 9 6 6 6-6"/></svg>'
ICON_CHEVR = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m9 6 6 6-6 6"/></svg>'
ICON_INFO  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z"/></svg>'
ICON_BOX   = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5l2.5 3 3.5-4.5 4.5 6H5z"/></svg>'
ICON_SHIP  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="currentColor"><path d="M3 4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h1a3 3 0 0 0 6 0h4a3 3 0 0 0 6 0h1a1 1 0 0 0 1-1v-4l-3-4h-3V5a1 1 0 0 0-1-1H3zm13 5h2.5l1.9 2.5H16V9zM7 17a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3zm10 0a1.5 1.5 0 1 1 0-3 1.5 1.5 0 0 1 0 3z"/></svg>'
ICON_BLOCK = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="m5.6 5.6 12.8 12.8"/></svg>'
ICON_SEARCH= '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>'
ICON_HOME  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/></svg>'
ICON_CART  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="9" cy="20" r="1.6"/><circle cx="18" cy="20" r="1.6"/><path d="M2 3h2l2.4 12.5a1.5 1.5 0 0 0 1.5 1.2h9.1a1.5 1.5 0 0 0 1.5-1.2L21 7H5"/></svg>'
ICON_GRID  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg>'
ICON_DOC   = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h6"/></svg>'
ICON_CHART = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></svg>'
ICON_BELL  = '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>'

def ico(svg: str, size: int = 16, color: str = "currentColor", mt: int = 0) -> str:
    return (f'<span class="ico" style="width:{size}px;height:{size}px;color:{color};'
            f'margin-top:{mt}px">{svg}</span>')

# ── Theme tokens + CSS ──────────────────────────────────────────────────────────

LIGHT = {
    "bg": "#f5f6fa", "surface": "#ffffff", "thumb": "#eef0f4", "sidebar": "#e8f7e8",
    "border": "#e0e0e0", "border-strong": "#cecece",
    "text": "#202020", "muted": "#565656", "faint": "#6b6b6b", "body": "#3a3a3a",
    "brand": "#215b33", "brand-hover": "#1a4a29", "brand-20": "#e8f7e8", "brand-10": "#f0f8f1",
    "accent-text": "#1a4a29",
    "success": "#218358", "success-text": "#186544", "success-20": "#e2f3ea",
    "danger": "#c8324f", "danger-text": "#851f41", "danger-20": "#fde7ec",
    "warn": "#c54600", "warn-bg": "#fbead9", "warn-text": "#8a4b00",
    "track": "#eeeeee", "on": "#218358", "navhover": "rgba(33,91,51,0.09)",
    "shadow-sm": "0 1px 2px rgba(32,32,32,.06)", "shadow-md": "0 2px 10px rgba(32,32,32,.10)",
}
DARK = {
    "bg": "#0e1411", "surface": "#161e1a", "thumb": "#1d2823", "sidebar": "#131a16",
    "border": "#2a3630", "border-strong": "#38473f",
    "text": "#e8f0ea", "muted": "#a6bbb0", "faint": "#87a094", "body": "#cdded4",
    "brand": "#2a6e3f", "brand-hover": "#348a4e", "brand-20": "#18271d", "brand-10": "#14201a",
    "accent-text": "#5cc07e",
    "success": "#2f9c64", "success-text": "#5fbf8c", "success-20": "#14271d",
    "danger": "#d8566f", "danger-text": "#f0a0af", "danger-20": "#2c1620",
    "warn": "#d88a4a", "warn-bg": "#2a1f12", "warn-text": "#e0b282",
    "track": "#232f29", "on": "#34a06b", "navhover": "rgba(90,200,126,0.12)",
    "shadow-sm": "0 1px 2px rgba(0,0,0,.4)", "shadow-md": "0 2px 12px rgba(0,0,0,.5)",
}

STATIC_CSS = """
*{box-sizing:border-box}
.ico{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;vertical-align:middle}

/* hide developer chrome but keep the toolbar (holds the sidebar » expander) */
[data-testid="stDecoration"],[data-testid="stStatusWidget"]{display:none!important}
[data-testid="stAppDeployButton"],[data-testid="stToolbarActions"]{display:none!important}
[data-testid="stHeader"],[data-testid="stToolbar"]{background:transparent!important}
#MainMenu,footer{visibility:hidden}

/* app shell */
html,body,.stApp{background:var(--bg);color:var(--text)}
.stApp{--background-color:var(--bg);--secondary-background-color:var(--surface);--text-color:var(--text)}
.stApp,.stApp [data-testid="stMarkdownContainer"],.stApp [data-baseweb],.stApp button,
.stApp input,.stApp textarea,.stApp [role="tab"],.stApp h1,.stApp h2,.stApp h3{
  font-family:"Roboto",system-ui,-apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
.block-container{padding-top:1.1rem;padding-bottom:4rem;max-width:1180px}
[data-testid="stSidebar"]{background:var(--sidebar);border-right:1px solid var(--border)}
[data-testid="stSidebar"] *,.stApp p,.stApp label,.stApp li,
[data-testid="stWidgetLabel"] p,[data-baseweb="tab"]{color:var(--text)}
.stApp [data-testid="stCaptionContainer"]{color:var(--muted)!important}

/* inputs / selects / steppers */
.stApp [data-baseweb="input"],.stApp [data-baseweb="textarea"],
.stApp [data-baseweb="select"]>div,.stApp [data-baseweb="base-input"]{
  background:var(--surface)!important;border-color:var(--border-strong)!important;border-radius:8px!important}
.stApp input,.stApp textarea,.stApp [data-baseweb="select"] div{color:var(--text)!important}
.stApp [data-testid="stNumberInput"] button{background:var(--surface)!important;border-color:var(--border-strong)!important;color:var(--text)!important}

/* primary action button - cisbox green */
.stApp button[kind="primary"],.stApp [data-testid="stBaseButton-primary"],
.stApp [data-testid="baseButton-primary"]{
  background:var(--brand)!important;border:none!important;color:#fff!important;
  border-radius:8px!important;font-weight:700!important}
.stApp button[kind="primary"]:hover,.stApp [data-testid="stBaseButton-primary"]:hover{background:var(--brand-hover)!important}

/* secondary buttons - surface with brand outline */
.stApp button[kind="secondary"],.stApp [data-testid="baseButton-secondary"],
.stApp [data-testid="stBaseButton-secondary"]{
  background:var(--surface)!important;color:var(--accent-text)!important;
  border:1.5px solid var(--brand)!important;border-radius:8px!important;font-weight:700!important}
.stApp button[kind="secondary"]:hover,.stApp [data-testid="stBaseButton-secondary"]:hover{background:var(--brand-20)!important}

/* tabs + expander + status + segmented control */
.stApp [data-baseweb="tab-list"]{border-bottom:1px solid var(--border);background:transparent;gap:8px}
.stApp [data-baseweb="tab"]{font-weight:700;padding:8px 16px}
.stApp [data-baseweb="tab"][aria-selected="true"]{color:var(--accent-text)}
.stApp [data-testid="stExpander"]{background:var(--surface);border:1px solid var(--border);border-radius:8px}
.stApp [data-testid="stExpander"] summary{color:var(--text)}
.stApp [data-testid="stStatus"]{background:var(--surface);border:1px solid var(--border);border-radius:8px}
.stApp [data-testid="stStatus"] *{color:var(--text)}
.stApp [data-baseweb="segmented-control"]{background:var(--track)}

/* ── topbar (account strip) ── */
.topbar{display:flex;align-items:center;gap:14px;margin:2px 0 10px}
.tb-search{flex:1;max-width:420px;display:flex;align-items:center;gap:10px;height:38px;padding:0 14px;
  border-radius:100px;background:var(--surface);border:1px solid var(--border-strong);color:var(--faint);font-size:13.5px}
.tb-spacer{flex:1}
.tb-pill{display:inline-flex;align-items:center;gap:8px;height:38px;padding:0 14px;border-radius:100px;
  background:var(--surface);border:1px solid var(--border-strong);color:var(--text);font-size:13.5px;font-weight:500}
.tb-bell{position:relative;width:38px;height:38px;border-radius:100px;background:var(--surface);
  border:1px solid var(--border-strong);display:flex;align-items:center;justify-content:center;color:var(--muted)}
.tb-bell .dot{position:absolute;top:8px;right:9px;width:8px;height:8px;border-radius:50%;background:var(--danger)}
.tb-avatar{width:38px;height:38px;border-radius:50%;background:var(--brand);color:#fff;font-weight:700;
  font-size:13px;display:flex;align-items:center;justify-content:center;flex-shrink:0}

/* breadcrumb + page header */
.crumb{font-size:13px;color:var(--muted);margin:2px 0 12px}
.crumb b{color:var(--text)}
.crumb .sep{color:var(--border-strong);margin:0 6px}
.phead{display:flex;align-items:center;gap:16px;margin-bottom:16px}
.phead .logo{width:52px;height:52px;border-radius:12px;background:var(--brand);color:#fff;
  display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow-sm);flex-shrink:0}
.phead h1{font-size:29px;line-height:34px;font-weight:700;margin:0;color:var(--text)}
.phead .tag{font-size:15px;color:var(--muted);margin-top:3px;max-width:760px}

/* section label */
.sec{text-transform:uppercase;letter-spacing:.08em;font-size:12px;font-weight:700;color:var(--faint);margin:10px 0 8px}

/* ── sidebar nav rail ── */
.sb-brand{display:flex;align-items:center;gap:10px;margin:0 0 14px}
.sb-logo{width:30px;height:30px;border-radius:7px;background:var(--brand);color:#fff;font-weight:700;
  font-size:17px;display:flex;align-items:center;justify-content:center}
.sb-word{font-weight:700;font-size:18px;letter-spacing:.5px;color:var(--text)}
.nav{display:flex;flex-direction:column;gap:4px;margin-bottom:6px}
.nav-item{display:flex;align-items:center;gap:12px;height:42px;padding:0 12px;border-radius:8px;
  font-weight:500;font-size:14px;color:var(--text)}
.nav-item.active{background:var(--brand);color:#fff}
.nav-item.muted{color:var(--muted)}
.sb-divider{height:1px;background:var(--border);margin:12px 2px 6px}
.sb-grouplabel{text-transform:uppercase;letter-spacing:.08em;font-size:11px;font-weight:700;color:var(--faint);margin:2px 2px 8px}
.stat{font-size:13.5px;margin:5px 0;color:var(--text);display:flex;align-items:center}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:9px;flex-shrink:0}
.dot.on{background:var(--on)}.dot.off{background:var(--border-strong)}

/* chips */
.chip{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:6px;font-size:12.5px;
  font-weight:700;line-height:16px;margin:0 6px 6px 0;white-space:nowrap;background:var(--track);color:var(--text)}
.chip.good{background:var(--brand-10);color:var(--accent-text)}
.chip.success{background:var(--success-20);color:var(--success-text)}
.chip.warn{background:var(--warn-bg);color:var(--warn-text)}
.chip.danger{background:var(--danger-20);color:var(--danger-text)}

/* ── out-of-stock context card ── */
.oos{background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);overflow:hidden;margin-bottom:6px}
.oos-banner{display:flex;align-items:center;gap:9px;padding:11px 18px;background:var(--danger-20);color:var(--danger-text)}
.oos-banner .st{font-weight:700;font-size:14px}
.oos-banner .sd{font-size:13px;opacity:.85}
.oos-body{padding:18px 20px}
.oos-head{display:flex;gap:14px;align-items:flex-start;margin-bottom:16px}
.oos-thumb,.rec-thumb,.swap-thumb{width:56px;height:56px;border-radius:6px;background:var(--thumb);color:var(--faint);
  display:flex;align-items:center;justify-content:center;flex-shrink:0;padding:14px}
.oos-name{font-weight:700;font-size:19px;color:var(--text)}
.oos-meta{font-size:14px;color:var(--muted);margin-top:2px}
.oos-stats{display:flex;flex-wrap:wrap;gap:14px 30px}
.ostat-l{font-size:12px;font-weight:700;color:var(--faint);margin-bottom:3px}
.ostat-v{font-size:15px;font-weight:700;color:var(--text)}

/* ── results header ── */
.res-head{display:flex;align-items:center;gap:10px;margin:2px 0 14px}
.res-count{font-weight:700;font-size:16px;color:var(--text)}
.res-sub{font-size:13.5px;color:var(--faint)}

/* ── recommendation card ── */
.rec{position:relative;background:var(--surface);border:1px solid var(--border);border-radius:8px;
  box-shadow:var(--shadow-sm);padding:18px 22px;margin-bottom:12px}
.rec.top{border:2px solid var(--brand);box-shadow:var(--shadow-md);padding:22px 22px 20px}
.rec-badge{position:absolute;top:-11px;left:20px;background:var(--brand);color:#fff;font-weight:700;
  font-size:11px;letter-spacing:.4px;text-transform:uppercase;padding:4px 10px;border-radius:6px;
  display:inline-flex;align-items:center;gap:5px}
.rec-head{display:flex;gap:18px;align-items:flex-start}
.rec-rankcol{display:flex;flex-direction:column;align-items:center;gap:8px;flex-shrink:0}
.rec-rank{width:24px;height:24px;border-radius:50%;background:var(--track);color:var(--muted);
  font-weight:700;font-size:13px;display:flex;align-items:center;justify-content:center}
.rec-rank.top{background:var(--brand);color:#fff}
.rec-main{flex:1;min-width:0}
.rec-titlerow{display:flex;align-items:flex-start;justify-content:space-between;gap:16px}
.rec-name{font-weight:700;font-size:17px;color:var(--text)}
.rec-sub{font-size:13.5px;color:var(--muted);margin-top:3px;display:flex;align-items:center;gap:6px}
.rec-score{display:flex;align-items:center;gap:10px;flex-shrink:0}
.rec-qlabel{font-weight:700;font-size:14px;line-height:1.1;text-align:right}
.rec-fit{font-size:12px;color:var(--muted);margin-top:2px;text-align:right}
.chips{display:flex;flex-wrap:wrap;margin-top:12px}

/* score ring */
.ring{position:relative;flex:0 0 auto}
.ring-c{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.ring-n{font-weight:700;color:var(--text);line-height:1}
.ring-l{font-size:8px;color:var(--faint);letter-spacing:.4px;margin-top:1px}

/* why this match */
.why{margin-top:12px}
.why summary{display:inline-flex;align-items:center;gap:6px;cursor:pointer;list-style:none;
  font-weight:700;font-size:13.5px;color:var(--accent-text);width:fit-content}
.why summary::-webkit-details-marker{display:none}
.why summary .chev{width:16px;height:16px;transition:transform .15s ease}
.why[open] summary .chev{transform:rotate(180deg)}
.why-body{margin-top:12px}
.brk{display:flex;flex-direction:column;gap:9px;max-width:480px}
.brk-row{display:grid;grid-template-columns:140px 1fr 52px;align-items:center;gap:12px}
.brk-l{font-size:13px;color:var(--muted)}
.brk-track{height:7px;border-radius:999px;background:var(--track);overflow:hidden}
.brk-fill{display:block;height:100%;border-radius:999px}
.brk-v{font-size:12.5px;font-weight:700;color:var(--text);text-align:right}
.brk-total{display:flex;justify-content:space-between;padding-top:7px;margin-top:2px;border-top:1px solid var(--border)}
.brk-total .l{font-weight:700;font-size:13px;color:var(--text)}
.brk-total .v{font-weight:700;font-size:13px}
.rationale{margin-top:14px;display:flex;gap:10px;background:var(--brand-10);border-radius:8px;padding:12px 14px;max-width:600px}
.rationale p{margin:0;font-size:14px;line-height:1.5;color:var(--text)}

/* excluded / filtered-out */
.excl{background:var(--surface);border:1px dashed var(--border-strong);border-radius:8px;padding:14px 18px;margin-top:4px}
.excl summary{display:flex;align-items:center;gap:10px;cursor:pointer;list-style:none}
.excl summary::-webkit-details-marker{display:none}
.excl summary .t{font-weight:700;font-size:14px;color:var(--muted)}
.excl summary .chev{width:18px;height:18px;margin-left:auto;color:var(--faint);transition:transform .15s ease}
.excl[open] summary .chev{transform:rotate(180deg)}
.excl-body{margin-top:12px;display:flex;flex-direction:column;gap:9px}
.excl-item{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.excl-name{font-size:14px;color:var(--muted);text-decoration:line-through;min-width:180px}

/* ── compare table ── */
.cmp{background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);overflow:hidden}
.cmp-scroll{overflow-x:auto}
.cmp table{border-collapse:collapse;width:100%}
.cmp th,.cmp td{padding:12px 16px;font-size:14px;color:var(--text);text-align:left;vertical-align:top;min-width:210px}
.cmp .rowlabel{font-weight:700;font-size:12px;letter-spacing:.3px;text-transform:uppercase;color:var(--faint);
  white-space:nowrap;width:150px;min-width:150px;position:sticky;left:0;background:var(--surface)}
.cmp tr{border-top:1px solid var(--border)}
.cmp thead tr{border-top:none}
.cmp-oos{background:var(--bg);color:var(--muted)}
.cmp-best{background:var(--brand-10)}
.cmp-name{font-weight:700;font-size:15px;color:var(--text)}
.cmp-sub{display:flex;align-items:center;gap:8px;margin-top:6px}
.cmp-bar{height:6px;border-radius:999px;background:var(--track);overflow:hidden;margin-top:5px}
.cmp-bar span{display:block;height:100%;border-radius:999px}
.cmp-expl{font-size:13px;color:var(--body);line-height:1.45;min-width:240px}

/* ── swap (before → after) ── */
.swap{background:var(--surface);border:1px solid var(--border);border-radius:8px;box-shadow:var(--shadow-md);padding:22px}
.swap-grid{display:grid;grid-template-columns:1fr 48px 1fr;align-items:stretch;gap:0}
.swap-arrow{display:flex;align-items:center;justify-content:center}
.swap-arrow span{width:40px;height:40px;border-radius:999px;background:var(--brand);color:#fff;
  display:flex;align-items:center;justify-content:center;box-shadow:var(--shadow-sm)}
.swap-pane{border-radius:8px;padding:18px}
.swap-pane.out{border:1px solid var(--border);background:var(--bg);opacity:.95}
.swap-pane.in{border:2px solid var(--brand);background:var(--surface);box-shadow:var(--shadow-sm)}
.swap-pane-head{display:flex;gap:12px;align-items:center;margin-top:10px}
.swap-thumb{width:48px;height:48px;padding:12px}
.swap-name{font-weight:700;font-size:16px;color:var(--text)}
.swap-meta{font-size:13px;color:var(--faint);margin-top:1px}
.swap-price{margin-top:12px;font-weight:700;font-size:19px;color:var(--text)}
.swap-price small{font-weight:400;font-size:12px;color:var(--faint);margin-left:6px}
.swap-chips{display:flex;flex-wrap:wrap;gap:0;margin-top:18px;justify-content:center}
.swap-diff{margin-top:18px;border:1px solid var(--border);border-radius:8px;overflow:hidden}
.swap-diff-row{display:grid;grid-template-columns:150px 1fr 28px 1fr;align-items:center;gap:10px;padding:10px 16px;border-top:1px solid var(--border)}
.swap-diff-row:first-child{border-top:none}
.swap-diff-row .l{font-weight:700;font-size:12px;text-transform:uppercase;letter-spacing:.3px;color:var(--faint)}
.swap-diff-row .from{font-size:14px;color:var(--muted)}
.swap-diff-row .to{font-size:14px;font-weight:700;color:var(--text);display:inline-flex;align-items:center;gap:6px}
.swap-foot{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-top:18px;flex-wrap:wrap}
.swap-impact{font-size:14px;color:var(--muted)}

/* similar-products rows */
.hit{display:flex;align-items:center;gap:16px;background:var(--surface);border:1px solid var(--border);
  border-radius:8px;box-shadow:var(--shadow-sm);padding:12px 16px;margin-bottom:8px}
.hit-meter{width:50px;flex-shrink:0}
.hit-meter .bar{height:6px;border-radius:999px;background:var(--track);overflow:hidden}
.hit-meter .bar span{display:block;height:100%;background:var(--brand);border-radius:999px}
.hit-meter .pct{font-size:11px;font-weight:700;color:var(--accent-text);margin-top:3px;text-align:center}
.hit-main{flex:1;min-width:0}
.hit-name{font-weight:700;font-size:15px;color:var(--text)}
.hit-cat{font-size:13px;color:var(--muted);margin-top:1px}

/* empty state */
.empty{background:var(--surface);border:1px dashed var(--border-strong);border-radius:8px;padding:46px 24px;text-align:center}
.empty .big{width:56px;height:56px;border-radius:999px;background:var(--brand-10);display:flex;
  align-items:center;justify-content:center;margin:0 auto 16px}
.empty .t{font-weight:700;font-size:18px;color:var(--text);margin-bottom:6px}
.empty .b{font-size:15px;color:var(--muted);max-width:430px;margin:0 auto;line-height:1.45}

/* card wrapper */
.card{background:var(--surface);border:1px solid var(--border);border-radius:8px;padding:6px 18px;
  box-shadow:var(--shadow-sm);margin-bottom:14px}
"""

def build_css(dark: bool) -> str:
    v = DARK if dark else LIGHT
    root = ":root{" + ";".join(f"--{k}:{val}" for k, val in v.items()) + "}"
    return ("<style>\n"
            "@import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap');\n"
            + root + "\n" + STATIC_CSS + "\n</style>")

# ── Render helpers ─────────────────────────────────────────────────────────────

def chip(text: str, tone: str = "") -> str:
    return f'<span class="chip {tone}">{esc(text)}</span>'

def score_ring(pct: int, size: int = 54) -> str:
    pct = max(0, min(100, int(pct or 0)))
    r = size / 2 - 4
    c = 2 * math.pi * r
    off = c * (1 - pct / 100)
    tone = "var(--success)" if pct >= 85 else "var(--brand)" if pct >= 70 else "var(--warn)"
    nfs = 15 if size >= 50 else 12
    lbl = '<span class="ring-l">MATCH</span>' if size >= 50 else ""
    return (
        f'<div class="ring" style="width:{size}px;height:{size}px">'
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r:.1f}" fill="none" stroke="var(--track)" stroke-width="4"/>'
        f'<circle cx="{size/2}" cy="{size/2}" r="{r:.1f}" fill="none" stroke="{tone}" stroke-width="4" stroke-linecap="round" '
        f'stroke-dasharray="{c:.1f}" stroke-dashoffset="{off:.1f}" transform="rotate(-90 {size/2} {size/2})"/>'
        f'</svg>'
        f'<div class="ring-c"><span class="ring-n" style="font-size:{nfs}px">{pct}</span>{lbl}</div>'
        f'</div>'
    )

def score_bar(label: str, got: int, mx: int) -> str:
    got = got or 0
    ratio = got / mx if mx else 0
    tone = "var(--success)" if ratio >= 0.999 else "var(--brand)" if ratio >= 0.6 else "var(--warn)"
    return (
        f'<div class="brk-row"><span class="brk-l">{label}</span>'
        f'<span class="brk-track"><span class="brk-fill" style="width:{round(ratio*100)}%;background:{tone}"></span></span>'
        f'<span class="brk-v">{got}/{mx}</span></div>'
    )

def reason_chips(b: dict) -> str:
    """Derive match-reason / caveat chips from the real score breakdown."""
    cm  = b.get("contractMatch", 0)
    cat = b.get("categorySimilarity", 0)
    pr  = b.get("priceSimilarity", 0)
    stk = b.get("stockAvailability", 0)
    up  = b.get("unitPackSimilarity", 0)
    out = []
    if cm >= 20:    out.append(chip("Contract match", "success"))
    elif cm >= 12:  out.append(chip("Partial contract", "good"))
    if cat >= 24:   out.append(chip("Same category", "good"))
    elif cat < 15:  out.append(chip("Different category", "warn"))
    if stk >= 10:   out.append(chip("In stock", "success"))
    elif stk <= 0:  out.append(chip("Low stock", "warn"))
    if pr >= 16:    out.append(chip("Similar price", "good"))
    elif pr <= 8:   out.append(chip("Price differs", "warn"))
    if up >= 6:     out.append(chip("Unit match", "good"))
    return "".join(out[:5])

def render_oos_card(p: dict) -> str:
    price, unit = catalog_price(p)
    cats = "".join(chip(c, "") for c in (p.get("catalogCategories") or [])[:3]) or "-"
    return (
        '<div class="oos">'
        f'<div class="oos-banner">{ico(ICON_WARN, 18, "var(--danger-text)")}'
        '<span class="st">Out of stock</span><span class="sd">· selected for replacement</span></div>'
        '<div class="oos-body">'
        f'<div class="oos-head"><div class="oos-thumb">{ICON_BOX}</div>'
        f'<div><div class="oos-name">{esc(p.get("name",""))}</div>'
        f'<div class="oos-meta">{esc(p.get("sellerName",""))} · contract {esc(p.get("contractNumber",""))} '
        f'· {esc(p.get("itemNumber",""))}</div></div></div>'
        '<div class="oos-stats">'
        f'<div><div class="ostat-l">Reference price</div><div class="ostat-v">{esc(price)} {esc(unit)}</div></div>'
        f'<div><div class="ostat-l">Contract</div><div class="ostat-v">{esc(p.get("contractNumber",""))}</div></div>'
        f'<div><div class="ostat-l">Seller #</div><div class="ostat-v">{esc(p.get("sellerAccountNumber",""))}</div></div>'
        f'<div><div class="ostat-l">Categories</div><div class="ostat-v">{cats}</div></div>'
        '</div></div></div>'
    )

def render_replacement(rep: dict, rank: int) -> str:
    top    = rank == 1
    label  = rep.get("confidenceLabel", "")
    qcolor = LABEL_COLORS.get(label, "var(--muted)")
    pct    = int(rep.get("confidencePct", 0) or 0)
    score  = rep.get("finalScore", 0)
    b      = rep.get("scoreBreakdown", {}) or {}
    bars   = "".join(score_bar(lbl, b.get(key, 0), mx) for key, lbl, mx in DIMENSIONS)
    expl   = esc(rep.get("explanation", "")) or "No explanation available."
    badge  = (f'<div class="rec-badge">{ico(ICON_CHECK, 12, "#fff")}Recommended</div>') if top else ""
    return (
        f'<div class="rec{" top" if top else ""}">{badge}'
        '<div class="rec-head">'
        f'<div class="rec-rankcol"><div class="rec-rank{" top" if top else ""}">{rank}</div>'
        f'<div class="rec-thumb">{ICON_BOX}</div></div>'
        '<div class="rec-main">'
        '<div class="rec-titlerow">'
        f'<div style="min-width:0"><div class="rec-name">{esc(rep.get("name",""))}</div>'
        f'<div class="rec-sub">{ico(ICON_SHIP, 15, "var(--faint)")}<span>{esc(rep.get("productId",""))}</span></div></div>'
        '<div class="rec-score"><div>'
        f'<div class="rec-qlabel" style="color:{qcolor}">{esc(label)} match</div>'
        f'<div class="rec-fit">Fit score {score}/{FIT_MAX}</div></div>'
        f'{score_ring(pct)}</div>'
        '</div>'
        f'<div class="chips">{reason_chips(b)}</div>'
        '<details class="why"><summary>'
        f'{ico(ICON_INFO, 16)}<span>Why this match</span><span class="chev ico">{ICON_CHEV}</span></summary>'
        '<div class="why-body">'
        f'<div class="brk">{bars}'
        f'<div class="brk-total"><span class="l">Total fit score</span>'
        f'<span class="v" style="color:{qcolor}">{score} / {FIT_MAX}</span></div></div>'
        f'<div class="rationale">{ico(ICON_SWAP, 18, "var(--accent-text)", mt=1)}<p>{expl}</p></div>'
        '</div></details>'
        '</div></div></div>'
    )

def render_excluded(rejected: list[dict]) -> str:
    n = len(rejected)
    items = "".join(
        f'<div class="excl-item"><span class="excl-name">{esc(rc.get("name", rc.get("productId","")))}</span>'
        f'<span>{chip(rc.get("rejectionReason",""), "danger")}</span></div>'
        for rc in rejected
    )
    return (
        '<details class="excl"><summary>'
        f'{ico(ICON_BLOCK, 18, "var(--faint)")}'
        f'<span class="t">{n} candidate{"s" if n != 1 else ""} filtered out by your requirements</span>'
        f'<span class="chev ico">{ICON_CHEV}</span></summary>'
        f'<div class="excl-body">{items}</div></details>'
    )

def render_compare(oos: dict, reps: list[dict]) -> str:
    """Side-by-side table: out-of-stock column + ranked candidate columns."""
    price, unit = catalog_price(oos or {})
    # header row
    head = '<th class="rowlabel"></th>'
    head += (f'<th class="cmp-oos"><div class="cmp-name">{esc((oos or {}).get("name","Out of stock item"))}</div>'
             f'<div class="cmp-sub">{chip("Out of stock","danger")}</div></th>')
    for i, m in enumerate(reps):
        cls = "cmp-best" if i == 0 else ""
        head += (f'<th class="{cls}"><div style="display:flex;align-items:center;gap:8px">'
                 f'{score_ring(int(m.get("confidencePct",0) or 0), 38)}'
                 f'<div class="cmp-name">{esc(m.get("name",""))}</div></div>'
                 f'<div class="cmp-sub">{chip("Best match","good") if i==0 else chip(m.get("confidenceLabel",""),"good")}</div></th>')

    def row(label, oos_val, render):
        cells = f'<th scope="row" class="rowlabel">{label}</th>'
        cells += f'<td class="cmp-oos">{oos_val}</td>'
        for i, m in enumerate(reps):
            cls = "cmp-best" if i == 0 else ""
            cells += f'<td class="{cls}">{render(m)}</td>'
        return f'<tr>{cells}</tr>'

    body = row("Fit score", "-",
               lambda m: f'<b>{m.get("finalScore",0)}/{FIT_MAX}</b> · {int(m.get("confidencePct",0) or 0)}%')
    for key, lbl, mx in DIMENSIONS:
        def render_dim(m, key=key, mx=mx):
            got = (m.get("scoreBreakdown", {}) or {}).get(key, 0)
            ratio = got / mx if mx else 0
            tone = "var(--success)" if ratio >= 0.999 else "var(--brand)" if ratio >= 0.6 else "var(--warn)"
            return (f'<b>{got}/{mx}</b>'
                    f'<div class="cmp-bar"><span style="width:{round(ratio*100)}%;background:{tone}"></span></div>')
        body += row(lbl, "-", render_dim)
    body += row("Why this match", f'Contract {esc((oos or {}).get("contractNumber",""))} · {esc(price)} {esc(unit)}',
                lambda m: f'<div class="cmp-expl">{esc(m.get("explanation",""))}</div>')

    return (f'<div class="cmp"><div class="cmp-scroll"><table>'
            f'<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div></div>')

def render_swap(oos: dict, m: dict, accepted: bool) -> str:
    """Focused before → after panel for one chosen candidate."""
    price, unit = catalog_price(oos or {})
    label = m.get("confidenceLabel", "")
    pct   = int(m.get("confidencePct", 0) or 0)
    b     = m.get("scoreBreakdown", {}) or {}
    diffs = "".join(
        f'<div class="swap-diff-row"><span class="l">{lbl}</span>'
        f'<span class="from">-</span>{ico(ICON_CHEVR, 16, "var(--border-strong)")}'
        f'<span class="to">{b.get(key,0)}/{mx}'
        f'{ico(ICON_CHECK, 15, "var(--success)") if (b.get(key,0)/mx if mx else 0) >= 0.999 else ""}</span></div>'
        for key, lbl, mx in DIMENSIONS
    )
    return (
        '<div class="swap"><div class="swap-grid">'
        '<div class="swap-pane out">'
        f'<div>{chip("Out of stock","danger")}</div>'
        f'<div class="swap-pane-head"><div class="swap-thumb">{ICON_BOX}</div>'
        f'<div><div class="swap-name">{esc((oos or {}).get("name","-"))}</div>'
        f'<div class="swap-meta">{esc((oos or {}).get("sellerName",""))} · contract {esc((oos or {}).get("contractNumber",""))}</div></div></div>'
        f'<div class="swap-price">{esc(price)} {esc(unit)}<small>reference</small></div>'
        '</div>'
        f'<div class="swap-arrow"><span>{ico(ICON_SWAP, 20, "#fff")}</span></div>'
        '<div class="swap-pane in">'
        f'<div style="display:flex;align-items:center;gap:8px">{chip((label + " match · best pick") if label else "Best pick","good")}{score_ring(pct, 40)}</div>'
        f'<div class="swap-pane-head"><div class="swap-thumb">{ICON_BOX}</div>'
        f'<div><div class="swap-name">{esc(m.get("name",""))}</div>'
        f'<div class="swap-meta">{ico(ICON_SHIP,13,"var(--faint)")} {esc(m.get("productId",""))}</div></div></div>'
        f'<div class="swap-price">Fit score {m.get("finalScore",0)}/{FIT_MAX}<small>{pct}% confidence</small></div>'
        '</div></div>'
        f'<div class="swap-chips">{reason_chips(b)}</div>'
        f'<div class="swap-diff">{diffs}</div>'
        f'<div class="rationale" style="margin-top:18px">{ico(ICON_INFO,18,"var(--accent-text)",mt=1)}<p>{esc(m.get("explanation","")) or "No explanation available."}</p></div>'
        '</div>'
    )

def render_hit(hit: dict) -> str:
    pct = round(max(0.0, min(1.0, hit.get("score", 0))) * 100)
    cat = f'<span class="hit-cat">{esc(hit.get("category_id",""))}</span>' if hit.get("category_id") else ""
    return (
        '<div class="hit">'
        f'<div class="hit-meter"><div class="bar"><span style="width:{pct}%"></span></div>'
        f'<div class="pct">{pct}%</div></div>'
        f'<div class="hit-main"><div class="hit-name">{esc(hit.get("name",""))}</div>{cat}</div>'
        f'<span>{chip(f"{hit.get('score',0):.2f}", "good")}</span>'
        '</div>'
    )

def empty_state(icon_svg: str, title: str, body: str) -> str:
    return (f'<div class="empty"><div class="big">{ico(icon_svg, 26, "var(--brand)")}</div>'
            f'<div class="t">{esc(title)}</div><div class="b">{esc(body)}</div></div>')

# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(page_title="Smart Substitution Engine - cisbox", page_icon="🔁", layout="wide")
# Theme is driven by the sidebar toggle (read here so the whole app re-themes on flip).
st.markdown(build_css(st.session_state.get("dark_mode", False)), unsafe_allow_html=True)

# Topbar (search · dark-mode toggle · account strip)
tb1, tb2, tb3 = st.columns([6, 2.2, 3.4], vertical_alignment="center")
tb1.markdown(
    f'<div class="tb-search">{ico(ICON_SEARCH, 17, "var(--faint)")}Search products, orders, suppliers…</div>',
    unsafe_allow_html=True,
)
tb2.toggle("🌙 Dark mode", key="dark_mode", help="Switch between light and dark themes.")
tb3.markdown(
    '<div style="display:flex;align-items:center;justify-content:flex-end;gap:12px">'
    f'<div class="tb-pill">{ico(ICON_SHIP, 17, "var(--muted)")}<span>TS cisbox</span>{ico(ICON_CHEV, 15, "var(--faint)")}</div>'
    f'<div class="tb-bell">{ico(ICON_BELL, 19)}<span class="dot"></span></div>'
    '<div class="tb-avatar">KH</div></div>',
    unsafe_allow_html=True,
)
# Breadcrumb + page header
st.markdown('<div class="crumb">Ordering<span class="sep">/</span><b>Smart substitution</b></div>', unsafe_allow_html=True)
st.markdown(
    f'<div class="phead"><div class="logo">{ico(ICON_SWAP, 26, "#fff")}</div>'
    '<div><h1>Smart Substitution Engine</h1>'
    '<div class="tag">AI - ranked replacements that protect your price, recipe and compliance '
    'when a product goes out of stock.</div></div></div>',
    unsafe_allow_html=True,
)

# ── Sidebar (cisbox nav rail + functional controls) ─────────────────────────────

NAV_ITEMS = [
    (ICON_HOME, "Dashboard", False), (ICON_CART, "Ordering", True),
    (ICON_GRID, "Catalogue", False), (ICON_SHIP, "Suppliers", False),
    (ICON_DOC, "Invoices", False), (ICON_CHART, "Reports", False),
]

with st.sidebar:
    st.markdown('<div class="sb-brand"><span class="sb-logo">c</span><span class="sb-word">cisbox</span></div>',
                unsafe_allow_html=True)
    st.markdown(
        '<div class="nav">' + "".join(
            f'<div class="nav-item {"active" if active else "muted"}">'
            f'{ico(svg, 20, "#fff" if active else "var(--muted)")}<span>{label}</span></div>'
            for svg, label, active in NAV_ITEMS
        ) + '</div>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="sb-divider"></div><div class="sb-grouplabel">Settings</div>', unsafe_allow_html=True)

    with st.expander("Advanced"):
        st.session_state.backend_url = st.text_input("Backend URL",  value=_backend())
        st.session_state.ai_url      = st.text_input("AI service URL", value=_ai())

    st.markdown(
        '<div style="color:var(--faint);font-size:.78rem;margin-top:18px;">Smart Substitution Engine</div>',
        unsafe_allow_html=True,
    )

# ── Tabs ──────────────────────────────────────────────────────────────────────

tab_reco, tab_search = st.tabs(["Replacements", "Similar products"])

# =========================================================================== #
# Tab 1 - Replacements
# =========================================================================== #
with tab_reco:

    # Surface a queued confirmation toast (set on "Accept swap", shown after rerun).
    _pt = st.session_state.pop("_pending_toast", None)
    if _pt:
        st.toast(_pt, icon=":material/check_circle:")

    # ── Step 1: Contract numbers ──────────────────────────────────────────────
    st.markdown('<div class="sec">Step 1 - Your contract numbers</div>', unsafe_allow_html=True)
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
    st.markdown('<div class="sec">Step 2 - Search for the out-of-stock product</div>', unsafe_allow_html=True)

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
            st.session_state.search_is_demo = False
        else:
            # Real catalog has no products in this environment - fall back to the
            # built-in sample catalog so the demo works against the live AI engine.
            demo = demo_search(search_query)
            st.session_state.catalog_results = demo
            st.session_state.selected_product = None
            st.session_state.search_is_demo = True
            if not demo:
                st.warning("No matches. Try a sample term: **kylling**, **laks**, or **appelsin**.")

    results = st.session_state.get("catalog_results", [])
    if results:
        if st.session_state.get("search_is_demo"):
            st.caption("Showing sample demo data - the live catalog backend has no products in this environment.")
        options = {
            f"[{p.get('contractNumber')}]  {p.get('name','')}  ({p.get('itemNumber','')})": p
            for p in results
        }
        chosen_label = st.selectbox(
            f"{len(results)} product(s) found - select the out-of-stock one:",
            list(options.keys()),
            key="product_select",
        )
        chosen = options[chosen_label]
        st.session_state.selected_product = chosen
        st.markdown(render_oos_card(chosen), unsafe_allow_html=True)

    selected = st.session_state.get("selected_product")

    # ── Step 3: Request details / run controls ────────────────────────────────
    st.markdown('<div class="sec">Step 3 - Request details</div>', unsafe_allow_html=True)
    o1, o2, o3 = st.columns([1.5, 1.5, 2])
    quantity    = o1.number_input("Quantity needed", value=10, min_value=1, step=1)
    max_results = o2.slider("Max results", 1, 10, 3)
    use_ai      = o3.toggle("Explanations", value=True,
                            help="Off = instant rule-based explanations.")

    go = st.button(
        "Find replacements",
        type="primary",
        use_container_width=True,
        disabled=selected is None or not contract_numbers,
    )

    if go and selected:
        is_demo = st.session_state.get("search_is_demo", False)
        # Animated "reasoning" sequence wrapped around the real engine call.
        with st.status("Finding the best replacement…", expanded=True) as status:
            st.write("Scanning catalogue for matching products…")
            time.sleep(0.35)
            st.write("Enforcing dietary & allergen requirements…")
            time.sleep(0.35)
            if is_demo:
                # Sample data → score directly with the live Python AI engine.
                ok, data, err = demo_recommend(selected, quantity, max_results, use_ai)
                if ok and data:
                    data = map_ai_reco(data)
            else:
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
                ok, data, err = backend_post("/recommendations/replacements", payload)
            st.write("Ranking on price, supplier & stock…")
            time.sleep(0.2)
            status.update(label="Replacements ready" if ok else "Couldn't fetch replacements",
                          state="complete" if ok else "error", expanded=False)
        st.session_state.reco = {"ok": ok, "data": data, "err": err}
        st.session_state.accepted_id = None

    # ── Results ───────────────────────────────────────────────────────────────
    st.markdown('<div class="sec">Recommended replacements</div>', unsafe_allow_html=True)
    reco = st.session_state.get("reco")
    if not reco:
        st.markdown(empty_state(ICON_SWAP, "Ready when you are",
                                "Search for a product, select it, then run the engine to see ranked, "
                                "compliant replacements."), unsafe_allow_html=True)
    elif not reco["ok"]:
        st.error(f"Could not get recommendations. {reco['err'] or ''}")
    else:
        data = reco["data"]
        if not data.get("replacementNeeded"):
            st.success("Product is in stock - no replacement needed.")
        else:
            reps = data.get("replacements") or []
            excluded = data.get("rejectedCandidates") or []
            if not reps:
                reason = data.get("noCandidatesReason") or "No suitable replacement found."
                st.markdown(empty_state(ICON_SEARCH, "No compliant replacement found", reason),
                            unsafe_allow_html=True)
            else:
                # results header
                st.markdown(
                    f'<div class="res-head">{ico(ICON_CHECK, 20, "var(--success)")}'
                    f'<span class="res-count">{len(reps)} compliant replacement{"s" if len(reps) != 1 else ""} found</span>'
                    f'<span class="res-sub">· {len(excluded)} filtered out</span></div>',
                    unsafe_allow_html=True,
                )
                view = st.segmented_control(
                    "Results view", ["Cards", "Compare", "Swap"],
                    default="Cards", key="view", label_visibility="collapsed",
                ) or "Cards"

                if view == "Cards":
                    for i, rep in enumerate(reps, 1):
                        st.markdown(render_replacement(rep, i), unsafe_allow_html=True)
                    if excluded:
                        st.markdown(render_excluded(excluded), unsafe_allow_html=True)

                elif view == "Compare":
                    st.markdown(render_compare(selected, reps), unsafe_allow_html=True)
                    if excluded:
                        st.markdown(render_excluded(excluded), unsafe_allow_html=True)

                else:  # Swap
                    labels = [f"{i+1} · {r.get('name','')}" for i, r in enumerate(reps)]
                    pick = st.radio("Focused option", labels, horizontal=True,
                                    label_visibility="collapsed", key="swap_pick")
                    idx = labels.index(pick) if pick in labels else 0
                    m = reps[idx]
                    accepted = st.session_state.get("accepted_id") == m.get("productId")
                    st.markdown(render_swap(selected, m, accepted), unsafe_allow_html=True)
                    if accepted:
                        st.button("✓ Swap added to order", disabled=True, use_container_width=True, key="swap_done")
                    elif st.button("Accept swap - add to order", type="primary",
                                   use_container_width=True, key="swap_accept"):
                        st.session_state.accepted_id = m.get("productId")
                        # Queue the toast so it survives the rerun (st.toast before
                        # st.rerun would be discarded); shown at the top of this tab.
                        st.session_state._pending_toast = f"{m.get('name','Replacement')} added to your order"
                        st.rerun()

# =========================================================================== #
# Tab 2 - Similar products (Python AI service - unchanged flow)
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
    st.caption("Semantic vector search - finds products by meaning, not just keywords.")

    if st.button("Load sample catalog", use_container_width=True):
        with st.spinner("Loading catalog into search index…"):
            ok, data, err = ai_post("/index/products", {"products": SAMPLE_CATALOG})
        if ok:
            st.session_state.pop("_health_ai", None)
            st.success(f"Loaded {data['indexed']} products into the search index.")
        else:
            st.error("Couldn't load the catalog - AI search service unavailable.")

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
        st.markdown(empty_state(ICON_SEARCH, "Search the catalogue",
                                "Load the sample catalog, then search for a product to see the closest matches."),
                    unsafe_allow_html=True)
    elif not sim["ok"]:
        st.error("Search unavailable - load the sample catalog first.")
    else:
        hits = sim["data"].get("results", [])
        if not hits:
            st.markdown(empty_state(ICON_SEARCH, "No matches found",
                                    "Try a different product name, or load the sample catalog first."),
                        unsafe_allow_html=True)
        else:
            st.markdown("".join(render_hit(h) for h in hits), unsafe_allow_html=True)

# =========================================================================== #
# Floating chat assistant
# Inject the self-contained widget (served by the AI service) into the parent
# document so the launcher floats over the whole app, bottom-right. It calls the
# AI service directly from the browser, so it uses the public URL + CORS.
#
# NB: st.components.v1.html is required here (not st.iframe / st.html): we need an
# iframe whose inline script reaches window.parent.document to mount a *floating*
# launcher. st.iframe only takes a URL (would box the chat inline) and st.html
# doesn't execute <script>. Streamlit marks v1.html deprecated - keep an eye on it
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
      // still warming up). No tight loop - so a slow load is never interrupted.
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
