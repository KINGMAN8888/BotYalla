/* BotYalla — ودجت الموقع (المرحلة 7). يُضمَّن في موقع العميل بسطر واحد:
     <script src="https://…/wg/KEY.js" async></script>
   زر واتساب و/أو محادثة ويب مع البوت نفسه (فلوهات · ذكاء · موظفون). بلا مكتبات، داخل Shadow DOM
   فلا تتسرّب أنماط الموقع إليه ولا أنماطه للموقع. كل نص يُعرض بـ textContent — لا innerHTML لمحتوى. */
(function () {
  "use strict";
  var BASE = __BASE__, KEY = __KEY__;
  if (window["__byw_" + KEY]) return;
  window["__byw_" + KEY] = 1;
  var store = { get: function (k) { try { return JSON.parse(localStorage.getItem("byw_" + KEY + "_" + k)); } catch (e) { return null; } },
                set: function (k, v) { try { localStorage.setItem("byw_" + KEY + "_" + k, JSON.stringify(v)); } catch (e) { /* خاص */ } } };
  function api(path, body) {
    var o = body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {};
    return fetch(BASE + "/wg/" + KEY + path, o).then(function (r) { return r.json(); });
  }
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }

  api("/config").then(function (cfg) {
    if (!cfg || !cfg.ok) return;
    var s = cfg.settings || {};
    var mobile = window.matchMedia("(max-width: 640px)").matches;
    if ((mobile && s.show_mobile === false) || (!mobile && s.show_desktop === false)) return;
    var rtl = s.lang !== "en", color = /^#[0-9a-fA-F]{6}$/.test(s.color || "") ? s.color : "#25D366";
    var side = s.position === "left" ? "left" : "right";
    var host = document.createElement("div");
    host.style.cssText = "position:fixed;z-index:2147483000;bottom:20px;" + side + ":20px";
    document.body.appendChild(host);
    var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;
    var css = el("style");
    css.textContent =
      "*{box-sizing:border-box;font-family:system-ui,-apple-system,'Segoe UI',Tahoma,sans-serif}" +
      ".fab{width:58px;height:58px;border-radius:50%;border:0;cursor:pointer;background:" + color + ";color:#fff;box-shadow:0 8px 24px rgba(0,0,0,.25);display:grid;place-items:center;position:relative}" +
      ".fab svg{width:30px;height:30px;fill:#fff}.dot{position:absolute;top:2px;" + (side === "right" ? "left" : "right") + ":2px;width:14px;height:14px;border-radius:50%;background:#ef4444;border:2px solid #fff;display:none}" +
      ".bubble{position:absolute;bottom:72px;" + side + ":0;width:250px;background:#fff;color:#111;border-radius:14px;padding:12px 30px 12px 14px;font-size:14px;line-height:1.5;box-shadow:0 10px 30px rgba(0,0,0,.18);cursor:pointer}" +
      ".bubble .x{position:absolute;top:6px;" + (rtl ? "left" : "right") + ":8px;border:0;background:none;cursor:pointer;color:#888;font-size:16px}" +
      ".panel{position:absolute;bottom:72px;" + side + ":0;width:360px;max-width:calc(100vw - 40px);height:520px;max-height:calc(100vh - 110px);background:#fff;color:#111;border-radius:18px;box-shadow:0 16px 48px rgba(0,0,0,.25);display:none;flex-direction:column;overflow:hidden}" +
      ".panel.open{display:flex}.hd{background:" + color + ";color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px}" +
      ".hd b{display:block;font-size:15px}.hd small{opacity:.9;font-size:12px}.hd .sp{flex:1}.hd button{border:0;background:rgba(255,255,255,.2);color:#fff;border-radius:10px;padding:6px 10px;cursor:pointer;font-size:12px;font-weight:700}" +
      ".msgs{flex:1;overflow-y:auto;padding:14px;background:#f4f5f7;display:flex;flex-direction:column;gap:8px}" +
      ".m{max-width:82%;padding:9px 12px;border-radius:14px;font-size:14px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}" +
      ".m.them{background:#fff;align-self:flex-start;border-" + (rtl ? "top-right" : "top-left") + "-radius:4px}" +
      ".m.me{background:" + color + ";color:#fff;align-self:flex-end;border-" + (rtl ? "top-left" : "top-right") + "-radius:4px}" +
      ".m img,.m video{max-width:100%;border-radius:10px;display:block;margin-bottom:6px}.m audio{width:220px;display:block}.m a{color:inherit}" +
      ".chips{display:flex;flex-wrap:wrap;gap:6px;align-self:flex-start;max-width:90%}" +
      ".chip{border:1px solid " + color + ";color:" + color + ";background:#fff;border-radius:999px;padding:6px 12px;font-size:13px;cursor:pointer}" +
      ".ft{display:flex;gap:8px;padding:10px;border-top:1px solid #eee;background:#fff}" +
      ".ft input{flex:1;border:1px solid #ddd;border-radius:12px;padding:10px 12px;font-size:14px;outline:none}" +
      ".ft button{border:0;background:" + color + ";color:#fff;border-radius:12px;padding:0 14px;cursor:pointer;font-weight:700}" +
      ".pw{text-align:center;font-size:10.5px;color:#999;padding:4px 0 8px;background:#fff}.pw a{color:#999}" +
      ".typing{align-self:flex-start;color:#888;font-size:12px}";
    root.appendChild(css);
    var wrap = el("div");
    wrap.dir = rtl ? "rtl" : "ltr";
    root.appendChild(wrap);
    var ICON_WA = '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 0 0-8.6 15.1L2 22l5-1.3A10 10 0 1 0 12 2zm0 18.2a8.2 8.2 0 0 1-4.2-1.2l-.3-.2-3 .8.8-2.9-.2-.3A8.2 8.2 0 1 1 12 20.2zm4.5-6.1c-.2-.1-1.5-.7-1.7-.8s-.4-.1-.6.1-.7.8-.8 1-.3.2-.5.1a6.7 6.7 0 0 1-3.3-2.9c-.3-.4.3-.4.7-1.3.1-.2 0-.3 0-.4l-.8-1.8c-.2-.5-.4-.4-.6-.4h-.5a1 1 0 0 0-.7.3 3 3 0 0 0-.9 2.2 5.2 5.2 0 0 0 1.1 2.7 11.9 11.9 0 0 0 4.5 4c1.7.7 2.3.8 3.1.7a2.7 2.7 0 0 0 1.8-1.3 2.2 2.2 0 0 0 .2-1.3c-.1-.1-.3-.2-.5-.3z"/></svg>';
    var ICON_CHAT = '<svg viewBox="0 0 24 24"><path d="M4 4h16a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2z"/></svg>';
    var chat = cfg.mode !== "whatsapp";
    var fab = el("button", "fab");
    fab.setAttribute("aria-label", s.label || (rtl ? "تواصل معنا" : "Chat with us"));
    fab.innerHTML = chat ? ICON_CHAT : ICON_WA;           // أيقونات ثابتة من الكود — لا محتوى من المستخدم
    var dot = el("span", "dot");
    fab.appendChild(dot);
    wrap.appendChild(fab);

    function openWa() { window.open(BASE + "/wg/" + KEY + "/wa", "_blank", "noopener"); }

    if (s.greeting && !store.get("greet_closed")) {
      setTimeout(function () {
        if (panel && panel.classList.contains("open")) return;
        var b = el("div", "bubble", s.greeting);
        var x = el("button", "x", "×");
        x.onclick = function (e) { e.stopPropagation(); b.remove(); store.set("greet_closed", 1); };
        b.appendChild(x);
        b.onclick = function () { b.remove(); fab.click(); };
        wrap.appendChild(b);
      }, Math.max(0, +s.greeting_delay || 3) * 1000);
    }
    api("/hello", { vid: (store.get("id") || {}).vid, sig: (store.get("id") || {}).sig }).then(function (r) { if (r && r.vid) store.set("id", { vid: r.vid, sig: r.sig }); });

    if (!chat) { fab.onclick = openWa; return; }

    var panel = el("div", "panel"), hd = el("div", "hd"), msgs = el("div", "msgs"), ft = el("form", "ft");
    var titles = el("div", "sp"), t1 = el("b", null, s.title || ""), t2 = el("small", null, s.subtitle || "");
    titles.appendChild(t1); titles.appendChild(t2); hd.appendChild(titles);
    if (cfg.wa) { var wb = el("button", null, rtl ? "واتساب" : "WhatsApp"); wb.type = "button"; wb.onclick = openWa; hd.appendChild(wb); }
    var cl = el("button", null, "✕"); cl.type = "button"; cl.onclick = function () { panel.classList.remove("open"); }; hd.appendChild(cl);
    var input = el("input"); input.placeholder = rtl ? "اكتب رسالتك…" : "Type a message…"; input.maxLength = 1000;
    var send = el("button", null, rtl ? "إرسال" : "Send"); send.type = "submit";
    ft.appendChild(input); ft.appendChild(send);
    panel.appendChild(hd); panel.appendChild(msgs); panel.appendChild(ft);
    if (cfg.branding) { var pw = el("div", "pw"); var a = el("a", null, "BotYalla"); a.href = "https://botyalla.com"; a.target = "_blank"; a.rel = "noopener"; pw.appendChild(document.createTextNode("⚡ ")); pw.appendChild(a); panel.appendChild(pw); }
    wrap.appendChild(panel);

    var last = 0, seen = {}, timer = null, started = false;
    function add(m) {
      if (seen[m.id]) return; seen[m.id] = 1;
      var b = el("div", "m " + (m.me ? "me" : "them"));
      var md = m.media;
      if (md && /^https?:\/\//.test(md.url || "")) {
        var n = el(md.kind === "video" ? "video" : md.kind === "audio" ? "audio" : "img");
        n.src = md.url; if (md.kind !== "image") n.controls = true;
        b.appendChild(n);
      }
      if (m.text) b.appendChild(document.createTextNode(m.text));
      if (m.link && /^https:\/\//.test(m.link)) { var l = el("a", null, " ↗"); l.href = m.link; l.target = "_blank"; l.rel = "noopener noreferrer"; b.appendChild(l); }
      if (m.text || md || m.link) msgs.appendChild(b);
      if (m.buttons && m.buttons.length) {
        var c = el("div", "chips");
        m.buttons.forEach(function (o) { var ch = el("button", "chip", o); ch.type = "button"; ch.onclick = function () { c.remove(); say(o); }; c.appendChild(ch); });
        msgs.appendChild(c);
      }
      msgs.scrollTop = msgs.scrollHeight;
    }
    function poll() {
      var id = store.get("id");
      if (!id) return;
      api("/poll?vid=" + encodeURIComponent(id.vid) + "&sig=" + encodeURIComponent(id.sig) + "&after=" + last).then(function (r) {
        (r.items || []).forEach(function (m) { add(m); last = Math.max(last, m.id); });
        if (r.items && r.items.length && !panel.classList.contains("open")) dot.style.display = "block";
      }).catch(function () {});
    }
    function say(text) {
      var id = store.get("id");
      if (!text || !id) return;
      api("/send", { vid: id.vid, sig: id.sig, text: text, first: !started }).then(function (r) { if (r && r.ok) poll(); });
      started = true;
      setTimeout(poll, 1200);
    }
    ft.onsubmit = function (e) { e.preventDefault(); var v = input.value.trim(); input.value = ""; say(v); };
    fab.onclick = function () {
      var open = panel.classList.toggle("open");
      dot.style.display = "none";
      var gb = wrap.querySelector(".bubble");
      if (gb) { gb.remove(); store.set("greet_closed", 1); }   // فتح المحادثة يُغني عن فقاعة الترحيب
      clearInterval(timer);
      timer = setInterval(poll, open ? 3000 : 20000);
      if (open) {
        poll();
        if (!started && !msgs.childNodes.length && s.welcome) add({ id: "w", text: s.welcome, buttons: s.icebreakers || [] });
        input.focus();
      }
    };
    setTimeout(poll, 1500);
  }).catch(function () { /* الودجت لا يكسر موقع العميل أبداً */ });
})();
