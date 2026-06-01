/*!
 * Smart Substitution Engine — floating chat widget (dependency-free).
 *
 * Drop-in: <script src="http://localhost:8000/chat/static/widget.js" data-api="http://localhost:8000"></script>
 * Renders a bottom-right launcher that opens a chat panel (in a Shadow DOM, so
 * host-page CSS can't leak in). Talks to POST {api}/chat and renders the
 * assistant's reply, quick-reply chips, and rich result cards.
 */
(function () {
  "use strict";
  if (window.__sseChat && window.__sseChat.loaded) return;
  window.__sseChat = { loaded: true };

  // --- config ------------------------------------------------------------
  var script =
    document.currentScript ||
    (function () {
      var s = document.getElementsByTagName("script");
      return s[s.length - 1];
    })();
  var API = (
    (script && script.getAttribute("data-api")) ||
    window.SSE_CHAT_API ||
    "http://localhost:8000"
  ).replace(/\/+$/, "");

  var STORAGE_KEY = "sse_chat_session";
  var sessionId = null;
  try {
    sessionId = localStorage.getItem(STORAGE_KEY);
  } catch (e) {}

  var DIMS = [
    ["category_similarity", "Category", 30],
    ["contract_match", "Contract", 25],
    ["price_similarity", "Price", 20],
    ["stock_availability", "Stock", 10],
    ["unit_pack_similarity", "Unit/pack", 8],
  ];
  var LABEL_COLORS = {
    Excellent: "#15803d",
    Strong: "#2563eb",
    Good: "#0891b2",
    Fair: "#d97706",
    Weak: "#dc2626",
  };
  var WELCOME =
    "👋 Hi! I'm your **Substitution Assistant**. When a product is " +
    "out of stock, I find the best alternatives for you — no forms, just ask.";
  var WELCOME_SUGGESTIONS = [
    "Find a replacement for Chicken Breast 2kg",
    "Show similar products to Beef Mince",
    "Check stock for Chicken Breast 2kg",
  ];

  // --- styles (scoped to the shadow root) --------------------------------
  var CSS =
    ":host{all:initial;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;" +
    "--sse-bg:#f8fafc;--sse-surface:#fff;--sse-surface2:#f8fafc;--sse-border:#e8ebf0;--sse-text:#0f172a;" +
    "--sse-muted:#64748b;--sse-faint:#94a3b8;--sse-body:#334155;--sse-track:#eef1f5;--sse-rankbg:#dcfce7;" +
    "--sse-ranktext:#15803d;--sse-expl:#f1f5f9;--sse-chipbg:#f1f5f9;--sse-chiptext:#475569;--sse-input:#fff;" +
    "--sse-grad:linear-gradient(135deg,#059669,#16a34a);}" +
    "@media (prefers-color-scheme:dark){:host{--sse-bg:#0b1220;--sse-surface:#141d2e;--sse-surface2:#0f1828;" +
    "--sse-border:#25324a;--sse-text:#e9eef7;--sse-muted:#9fb0c9;--sse-faint:#6f8099;--sse-body:#c7d2e0;" +
    "--sse-track:#1f2a3e;--sse-rankbg:#0f2e1f;--sse-ranktext:#86efac;--sse-expl:#111c30;--sse-chipbg:#1f2a3e;" +
    "--sse-chiptext:#cbd5e1;--sse-input:#0f1828;}}" +
    "*{box-sizing:border-box;}" +
    /* launcher */
    ".sse-launcher{position:fixed;right:24px;bottom:24px;width:60px;height:60px;border-radius:50%;border:none;" +
    "background:var(--sse-grad);box-shadow:0 8px 24px rgba(5,150,105,.42);cursor:pointer;display:flex;" +
    "align-items:center;justify-content:center;z-index:2147483646;transition:transform .18s ease;}" +
    ".sse-launcher:hover{transform:scale(1.06);}" +
    ".sse-launcher .ic{position:absolute;display:flex;align-items:center;justify-content:center;transition:transform .2s ease,opacity .2s ease;}" +
    ".sse-launcher .ic-close{opacity:0;transform:rotate(-90deg) scale(.6);}" +
    ".sse-launcher.active .ic-chat{opacity:0;transform:rotate(90deg) scale(.6);}" +
    ".sse-launcher.active .ic-close{opacity:1;transform:none;}" +
    ".sse-launcher.active .sse-dot{display:none;}" +
    ".sse-dot{position:absolute;top:12px;right:13px;width:11px;height:11px;border-radius:50%;background:#22c55e;" +
    "border:2px solid #fff;}" +
    /* panel sits ABOVE the always-visible launcher so the icon never disappears */
    ".sse-panel{position:fixed;right:24px;bottom:96px;width:386px;height:min(600px,calc(100vh - 132px));" +
    "background:var(--sse-surface);border:1px solid var(--sse-border);border-radius:18px;" +
    "box-shadow:0 24px 60px rgba(2,6,23,.28);display:flex;flex-direction:column;overflow:hidden;" +
    "opacity:0;transform:translateY(18px) scale(.98);pointer-events:none;transform-origin:bottom right;" +
    "transition:opacity .2s ease,transform .2s ease;z-index:2147483647;}" +
    ".sse-panel.open{opacity:1;transform:none;pointer-events:auto;}" +
    /* header */
    ".sse-head{background:var(--sse-grad);color:#fff;padding:14px 16px;display:flex;align-items:center;gap:11px;}" +
    ".sse-head .av{width:38px;height:38px;border-radius:11px;background:rgba(255,255,255,.18);display:flex;" +
    "align-items:center;justify-content:center;font-size:20px;flex:0 0 auto;}" +
    ".sse-head .ti{flex:1;min-width:0;}" +
    ".sse-head .ti b{font-size:15px;font-weight:700;display:block;line-height:1.2;}" +
    ".sse-head .ti span{font-size:11.5px;opacity:.9;display:flex;align-items:center;gap:5px;}" +
    ".sse-head .ti i{width:7px;height:7px;border-radius:50%;background:#4ade80;display:inline-block;}" +
    ".sse-head button{background:rgba(255,255,255,.16);border:none;color:#fff;width:28px;height:28px;" +
    "border-radius:8px;cursor:pointer;font-size:16px;line-height:1;display:flex;align-items:center;justify-content:center;}" +
    ".sse-head button:hover{background:rgba(255,255,255,.3);}" +
    /* messages */
    ".sse-msgs{flex:1;overflow-y:auto;padding:14px;background:var(--sse-bg);display:flex;flex-direction:column;gap:10px;}" +
    ".sse-msgs::-webkit-scrollbar{width:7px;}.sse-msgs::-webkit-scrollbar-thumb{background:var(--sse-border);border-radius:4px;}" +
    ".sse-row{display:flex;gap:8px;align-items:flex-end;}" +
    ".sse-row.user{justify-content:flex-end;}" +
    ".sse-av{width:28px;height:28px;border-radius:50%;background:var(--sse-grad);display:flex;align-items:center;" +
    "justify-content:center;font-size:14px;flex:0 0 auto;}" +
    ".sse-av.ghost{background:transparent;}" +
    ".sse-bub{padding:10px 13px;border-radius:15px;font-size:14px;line-height:1.5;max-width:80%;color:var(--sse-text);" +
    "background:var(--sse-surface);border:1px solid var(--sse-border);border-bottom-left-radius:5px;word-wrap:break-word;overflow-wrap:anywhere;}" +
    ".sse-row.user .sse-bub{background:var(--sse-grad);color:#fff;border:none;border-radius:15px;border-bottom-right-radius:5px;}" +
    ".sse-bub code{background:var(--sse-chipbg);padding:1px 5px;border-radius:5px;font-size:12.5px;}" +
    ".sse-bub strong{font-weight:700;}" +
    /* typing */
    ".sse-typing{display:flex;gap:4px;padding:4px 2px;}" +
    ".sse-typing i{width:7px;height:7px;border-radius:50%;background:var(--sse-faint);animation:sseb 1.2s infinite;}" +
    ".sse-typing i:nth-child(2){animation-delay:.2s;}.sse-typing i:nth-child(3){animation-delay:.4s;}" +
    "@keyframes sseb{0%,60%,100%{opacity:.3;transform:translateY(0);}30%{opacity:1;transform:translateY(-4px);}}" +
    /* cards */
    ".sse-cards{display:flex;flex-direction:column;gap:8px;max-width:92%;}" +
    ".sse-card{background:var(--sse-surface2);border:1px solid var(--sse-border);border-radius:13px;padding:11px 13px;}" +
    ".sse-chead{display:flex;gap:9px;align-items:flex-start;}" +
    ".sse-rank{width:23px;height:23px;border-radius:7px;background:var(--sse-rankbg);color:var(--sse-ranktext);" +
    "font-weight:800;font-size:12px;display:flex;align-items:center;justify-content:center;flex:0 0 auto;}" +
    ".sse-cmain{flex:1;min-width:0;}" +
    ".sse-cname{font-weight:700;font-size:13.5px;color:var(--sse-text);}" +
    ".sse-csub{color:var(--sse-muted);font-size:11.5px;margin-top:1px;}" +
    ".sse-cconf{text-align:right;font-weight:800;font-size:17px;line-height:1;flex:0 0 auto;}" +
    ".sse-clab{font-size:10px;font-weight:700;margin-top:2px;}" +
    ".sse-bars{margin-top:9px;display:flex;flex-direction:column;gap:3px;}" +
    ".sse-brow{display:flex;align-items:center;gap:7px;font-size:11px;}" +
    ".sse-bl{flex:0 0 56px;color:var(--sse-muted);}" +
    ".sse-bar{flex:1;height:6px;background:var(--sse-track);border-radius:4px;overflow:hidden;}" +
    ".sse-bar>span{display:block;height:100%;background:var(--sse-grad);border-radius:4px;}" +
    ".sse-bar.wide{flex:0 0 96px;}" +
    ".sse-bv{flex:0 0 40px;text-align:right;color:var(--sse-body);font-variant-numeric:tabular-nums;}" +
    ".sse-tags{margin-top:8px;display:flex;gap:5px;flex-wrap:wrap;}" +
    ".sse-tag{padding:2px 9px;border-radius:999px;font-size:10.5px;font-weight:700;background:var(--sse-chipbg);color:var(--sse-chiptext);}" +
    ".sse-tag.pref{background:#15803d;color:#fff;}.sse-tag.contract{background:#065f46;color:#d1fae5;}" +
    ".sse-tag.ok{background:#dcfce7;color:#15803d;}.sse-tag.warn{background:#fef3c7;color:#b45309;}" +
    ".sse-expl{margin-top:9px;background:var(--sse-expl);border-left:3px solid #059669;border-radius:7px;" +
    "padding:8px 11px;color:var(--sse-body);font-size:12.5px;line-height:1.45;}" +
    ".sse-card.sim,.sse-card.prod{padding:10px 13px;}" +
    ".sse-simrow{display:flex;align-items:center;gap:10px;}.sse-simrow .sse-cname{flex:1;}" +
    ".sse-prow{display:flex;align-items:center;justify-content:space-between;margin-top:7px;}" +
    ".sse-pprice{font-weight:700;color:var(--sse-body);font-size:13px;}" +
    /* suggestions */
    ".sse-sug{display:flex;flex-wrap:wrap;gap:6px;padding:9px 12px 4px;border-top:1px solid var(--sse-border);}" +
    ".sse-chip{padding:6px 11px;border-radius:999px;border:1px solid var(--sse-border);background:var(--sse-surface);" +
    "color:var(--sse-ranktext);font-size:12.5px;cursor:pointer;font-weight:600;transition:background .15s,transform .1s;font-family:inherit;}" +
    ".sse-chip:hover{background:var(--sse-chipbg);transform:translateY(-1px);}" +
    /* input */
    ".sse-in{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--sse-border);align-items:flex-end;background:var(--sse-surface);}" +
    ".sse-in textarea{flex:1;resize:none;border:1px solid var(--sse-border);border-radius:13px;padding:9px 13px;" +
    "font-size:14px;max-height:104px;outline:none;font-family:inherit;background:var(--sse-input);color:var(--sse-text);line-height:1.4;}" +
    ".sse-in textarea:focus{border-color:#10b981;}" +
    ".sse-send{flex:0 0 auto;width:39px;height:39px;border-radius:50%;border:none;background:var(--sse-grad);" +
    "cursor:pointer;display:flex;align-items:center;justify-content:center;}" +
    ".sse-send:disabled{opacity:.5;cursor:default;}" +
    ".sse-foot{text-align:center;font-size:10.5px;color:var(--sse-faint);padding:5px;background:var(--sse-surface);}" +
    "@media (max-width:480px){.sse-panel{right:12px;bottom:88px;width:calc(100vw - 24px);height:calc(100vh - 108px);}" +
    ".sse-launcher{right:16px;bottom:16px;}}";

  // --- DOM ---------------------------------------------------------------
  var BUBBLE_SVG =
    '<svg width="26" height="26" viewBox="0 0 24 24" fill="none"><path d="M12 3C6.9 3 3 6.4 3 11c0 2 1 3.9 2.6 5.2L5 21l4.4-1.9c.8.2 1.7.3 2.6.3 5.1 0 9-3.4 9-8s-3.9-8-9-8z" fill="#fff"/></svg>';
  var CLOSE_SVG =
    '<svg width="24" height="24" viewBox="0 0 24 24" fill="none"><path d="M6 6l12 12M18 6L6 18" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/></svg>';
  var SEND_SVG =
    '<svg width="18" height="18" viewBox="0 0 24 24" fill="#fff"><path d="M3.4 20.4l17.4-7.5c.8-.3.8-1.4 0-1.8L3.4 3.6c-.7-.3-1.4.2-1.4 1L2 9.1c0 .5.4.9.9 1L17 12 2.9 13.9c-.5.1-.9.5-.9 1l0 4.6c0 .7.7 1.2 1.4.9z"/></svg>';

  var host = document.createElement("div");
  host.id = "sse-chat-widget";
  document.body.appendChild(host);
  var root = host.attachShadow({ mode: "open" });
  root.innerHTML =
    "<style>" + CSS + "</style>" +
    '<button class="sse-launcher" aria-label="Open chat assistant">' +
    '<span class="ic ic-chat">' + BUBBLE_SVG + '</span>' +
    '<span class="ic ic-close">' + CLOSE_SVG + '</span>' +
    '<span class="sse-dot"></span></button>' +
    '<div class="sse-panel" role="dialog" aria-label="Substitution Assistant">' +
    '  <div class="sse-head">' +
    '    <div class="av">🔁</div>' +
    '    <div class="ti"><b>Substitution Assistant</b><span><i></i>Online · AI-powered</span></div>' +
    '    <button class="sse-min" aria-label="Minimize" title="Minimize">–</button>' +
    '    <button class="sse-close" aria-label="Close" title="Close">×</button>' +
    "  </div>" +
    '  <div class="sse-msgs"></div>' +
    '  <div class="sse-sug" style="display:none"></div>' +
    '  <div class="sse-in"><textarea rows="1" placeholder="Ask about a replacement…"></textarea>' +
    '    <button class="sse-send" aria-label="Send">' + SEND_SVG + "</button></div>" +
    '  <div class="sse-foot">Grounded answers · deterministic ranking</div>' +
    "</div>";

  var launcher = root.querySelector(".sse-launcher");
  var panel = root.querySelector(".sse-panel");
  var msgs = root.querySelector(".sse-msgs");
  var sug = root.querySelector(".sse-sug");
  var input = root.querySelector(".sse-in textarea");
  var sendBtn = root.querySelector(".sse-send");
  var sending = false;
  var booted = false;

  // --- helpers -----------------------------------------------------------
  function esc(s) {
    return (s == null ? "" : String(s))
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
  function fmt(text) {
    return esc(text)
      .replace(/\*\*([^*]+?)\*\*/g, "<strong>$1</strong>")
      .replace(/`([^`]+?)`/g, "<code>$1</code>")
      .replace(/_([^_]+?)_/g, "<em>$1</em>")
      .replace(/\n/g, "<br>");
  }
  function num(v) {
    return typeof v === "number" ? v : null;
  }
  function down() {
    msgs.scrollTop = msgs.scrollHeight;
  }
  function addMsg(role, html) {
    var row = document.createElement("div");
    row.className = "sse-row " + role;
    row.innerHTML =
      (role === "bot" ? '<div class="sse-av">🔁</div>' : "") +
      '<div class="sse-bub">' + html + "</div>";
    msgs.appendChild(row);
    down();
    return row;
  }
  function bars(sb) {
    return DIMS.map(function (d) {
      var v = (sb && num(sb[d[0]])) || 0;
      var pct = Math.round((v / d[2]) * 100);
      return (
        '<div class="sse-brow"><span class="sse-bl">' + d[1] + "</span>" +
        '<span class="sse-bar"><span style="width:' + pct + '%"></span></span>' +
        '<span class="sse-bv">' + v + "/" + d[2] + "</span></div>"
      );
    }).join("");
  }
  function cardHtml(c) {
    if (c.type === "replacement") {
      var color = LABEL_COLORS[c.confidence_label] || "#64748b";
      var sub = [];
      if (c.brand) sub.push(esc(c.brand));
      if (num(c.effective_price) != null) sub.push(c.effective_price.toFixed(2) + "/" + (c.unit || "unit"));
      if (num(c.stock_quantity) != null) sub.push(Math.round(c.stock_quantity) + " in stock");
      var tags = "";
      if (c.is_preferred) tags = '<span class="sse-tag pref">★ Preferred</span>';
      else if (c.is_under_contract) tags = '<span class="sse-tag contract">Under contract</span>';
      return (
        '<div class="sse-card">' +
        '<div class="sse-chead"><span class="sse-rank">' + (c.rank || "") + "</span>" +
        '<div class="sse-cmain"><div class="sse-cname">' + esc(c.name) + "</div>" +
        '<div class="sse-csub">' + sub.join(" · ") + "</div></div>" +
        '<div class="sse-cconf" style="color:' + color + '">' + (num(c.confidence_pct) != null ? c.confidence_pct + "%" : "") +
        '<div class="sse-clab" style="color:' + color + '">' + esc(c.confidence_label || "") + "</div></div></div>" +
        '<div class="sse-bars">' + bars(c.score_breakdown) + "</div>" +
        (tags ? '<div class="sse-tags">' + tags + "</div>" : "") +
        (c.explanation ? '<div class="sse-expl">' + esc(c.explanation) + "</div>" : "") +
        "</div>"
      );
    }
    if (c.type === "similar") {
      var pct = Math.round(Math.max(0, Math.min(1, num(c.score) || 0)) * 100);
      return (
        '<div class="sse-card sim"><div class="sse-simrow">' +
        '<span class="sse-cname">' + esc(c.name) + "</span>" +
        (c.category_id ? '<span class="sse-tag">' + esc(c.category_id) + "</span>" : "") +
        '<span class="sse-bar wide"><span style="width:' + pct + '%"></span></span></div></div>'
      );
    }
    if (c.type === "product") {
      var inStock = num(c.stock_quantity) != null && c.stock_quantity > 0;
      var price = num(c.base_price) != null ? c.base_price.toFixed(2) + "/" + (c.unit || "unit") : "—";
      return (
        '<div class="sse-card prod"><div class="sse-cname">' + esc(c.name) +
        (c.category_id ? ' <span class="sse-tag">' + esc(c.category_id) + "</span>" : "") + "</div>" +
        '<div class="sse-prow"><span class="sse-tag ' + (inStock ? "ok" : "warn") + '">' +
        (inStock ? Math.round(c.stock_quantity) + " in stock" : "out of stock") + "</span>" +
        '<span class="sse-pprice">' + price + "</span></div></div>"
      );
    }
    return "";
  }
  function addCards(cards) {
    if (!cards || !cards.length) return;
    var row = document.createElement("div");
    row.className = "sse-row bot";
    var wrap = '<div class="sse-cards">' + cards.map(cardHtml).join("") + "</div>";
    row.innerHTML = '<div class="sse-av ghost"></div>' + wrap;
    msgs.appendChild(row);
    down();
  }
  function showSug(list) {
    sug.innerHTML = "";
    (list || []).forEach(function (s) {
      var b = document.createElement("button");
      b.className = "sse-chip";
      b.textContent = s;
      b.onclick = function () {
        send(s);
      };
      sug.appendChild(b);
    });
    sug.style.display = list && list.length ? "flex" : "none";
  }
  function typing(on) {
    var ex = root.querySelector(".sse-typing-row");
    if (on) {
      if (ex) return;
      var row = document.createElement("div");
      row.className = "sse-row bot sse-typing-row";
      row.innerHTML =
        '<div class="sse-av">🔁</div><div class="sse-bub"><div class="sse-typing"><i></i><i></i><i></i></div></div>';
      msgs.appendChild(row);
      down();
    } else if (ex) {
      ex.remove();
    }
  }
  function setSending(on) {
    sending = on;
    sendBtn.disabled = on;
  }

  // --- networking --------------------------------------------------------
  function send(text) {
    text = (text || input.value || "").trim();
    if (!text || sending) return;
    input.value = "";
    resize();
    addMsg("user", esc(text));
    showSug([]);
    setSending(true);
    typing(true);
    fetch(API + "/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message: text }),
    })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        typing(false);
        if (data.session_id) {
          sessionId = data.session_id;
          try {
            localStorage.setItem(STORAGE_KEY, sessionId);
          } catch (e) {}
        }
        addMsg("bot", fmt(data.reply || ""));
        addCards(data.cards);
        showSug(data.suggestions);
      })
      .catch(function () {
        typing(false);
        addMsg(
          "bot",
          fmt("I couldn't reach the assistant service. Please check it's running and try again.")
        );
      })
      .then(function () {
        setSending(false);
      });
  }

  // --- interactions ------------------------------------------------------
  function open() {
    panel.classList.add("open");
    launcher.classList.add("active"); // launcher stays visible, icon morphs to ×
    launcher.setAttribute("aria-label", "Close chat assistant");
    if (!booted) {
      booted = true;
      addMsg("bot", fmt(WELCOME));
      showSug(WELCOME_SUGGESTIONS);
    }
    setTimeout(function () {
      input.focus();
    }, 220);
  }
  function close() {
    panel.classList.remove("open");
    launcher.classList.remove("active");
    launcher.setAttribute("aria-label", "Open chat assistant");
  }
  function toggle() {
    panel.classList.contains("open") ? close() : open();
  }
  function resize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 104) + "px";
  }

  launcher.onclick = toggle; // one always-present button toggles the panel
  root.querySelector(".sse-close").onclick = close;
  root.querySelector(".sse-min").onclick = close;
  sendBtn.onclick = function () {
    send();
  };
  input.addEventListener("input", resize);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  });
})();
