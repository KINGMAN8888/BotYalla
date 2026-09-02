/* ============================================================================
   BotYalla — طبقة التفاعل. فانيلا JS بلا أي مكتبة (لا build step).
   كل شيء اختياري: لو فشل أي جزء تبقى الصفحة تعمل بالكامل (progressive enhancement).
   ========================================================================== */
(function () {
  "use strict";

  var reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };

  /* ---------------------------------------------- 1) الظهور عند التمرير */
  function initReveal() {
    var els = $$(".reveal");
    if (!els.length) return;
    if (reduced || !("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.classList.add("in"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12, rootMargin: "0px 0px -40px 0px" });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------------------------- 2) موجة النقر (ripple) */
  function initRipple() {
    document.addEventListener("pointerdown", function (ev) {
      if (reduced) return;
      var btn = ev.target.closest ? ev.target.closest(".btn") : null;
      if (!btn || btn.disabled) return;
      var r = btn.getBoundingClientRect();
      var size = Math.max(r.width, r.height);
      var span = document.createElement("span");
      span.className = "ripple";
      span.style.width = span.style.height = size + "px";
      span.style.left = (ev.clientX - r.left - size / 2) + "px";
      span.style.top = (ev.clientY - r.top - size / 2) + "px";
      btn.appendChild(span);
      setTimeout(function () { span.remove(); }, 600);
    }, { passive: true });
  }

  /* ------------------------------------------- 3) عدّادات رقمية متحرّكة */
  function initCounters() {
    var els = $$("[data-count]");
    if (!els.length) return;
    if (reduced || !("IntersectionObserver" in window)) {
      els.forEach(function (el) { el.textContent = el.getAttribute("data-count"); });
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        io.unobserve(e.target);
        var el = e.target;
        var target = parseFloat(el.getAttribute("data-count")) || 0;
        var dec = (String(target).split(".")[1] || "").length;
        var t0 = null, dur = 1100;
        function tick(ts) {
          if (!t0) t0 = ts;
          var p = Math.min((ts - t0) / dur, 1);
          var eased = 1 - Math.pow(1 - p, 3);
          el.textContent = (target * eased).toFixed(dec);
          if (p < 1) requestAnimationFrame(tick);
          else el.textContent = target.toFixed(dec);
        }
        requestAnimationFrame(tick);
      });
    }, { threshold: 0.4 });
    els.forEach(function (el) { io.observe(el); });
  }

  /* ------------------------------------------------ 4) درج التنقّل للجوال */
  function initNav() {
    var toggle = $(".navtoggle"), side = $(".sidebar"), scrim = $(".scrim");
    if (!toggle || !side) return;
    function setOpen(open) {
      side.classList.toggle("open", open);
      if (scrim) scrim.classList.toggle("show", open);
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
      document.body.style.overflow = open ? "hidden" : "";
    }
    toggle.addEventListener("click", function () {
      setOpen(toggle.getAttribute("aria-expanded") !== "true");
    });
    if (scrim) scrim.addEventListener("click", function () { setOpen(false); });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") setOpen(false);
    });
    // أغلق الدرج عند اختيار وجهة
    $$(".sidebar a").forEach(function (a) {
      a.addEventListener("click", function () { setOpen(false); });
    });
  }

  /* ----------------------------------------------- 5) الإشعارات المنبثقة */
  function toast(msg, kind, ms) {
    var box = $(".toasts");
    if (!box) {
      box = document.createElement("div");
      box.className = "toasts";
      box.setAttribute("aria-live", "polite");
      document.body.appendChild(box);
    }
    var el = document.createElement("div");
    el.className = "toast " + (kind || "ok");
    el.textContent = msg;
    box.appendChild(el);
    setTimeout(function () {
      el.classList.add("out");
      setTimeout(function () { el.remove(); }, 320);
    }, ms || 3200);
  }
  window.botyallaToast = toast;

  /* حوّل رسائل flash الموجودة إلى إشعارات على الشاشات الصغيرة فقط لو أردت لاحقاً */

  /* --------------------------------------------------------- 6) النسخ */
  function initCopy() {
    document.addEventListener("click", function (ev) {
      var b = ev.target.closest ? ev.target.closest("[data-copy]") : null;
      if (!b) return;
      ev.preventDefault();
      var text = b.getAttribute("data-copy");
      if (!text) {
        var sel = b.getAttribute("data-copy-from");
        var src = sel ? $(sel) : null;
        text = src ? (src.value || src.textContent || "").trim() : "";
      }
      if (!text) return;
      var done = function () { toast(b.getAttribute("data-copied") || "Copied", "ok", 1800); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, function () { fallback(text, done); });
      } else { fallback(text, done); }
    });
    function fallback(text, done) {
      var ta = document.createElement("textarea");
      ta.value = text; ta.setAttribute("readonly", "");
      ta.style.position = "fixed"; ta.style.opacity = "0";
      document.body.appendChild(ta); ta.select();
      try { document.execCommand("copy"); done(); } catch (e) { /* تجاهل */ }
      ta.remove();
    }
  }

  /* ------------------------------- 7) حالة التحميل عند إرسال أي نموذج */
  function initFormLoading() {
    $$("form").forEach(function (f) {
      f.addEventListener("submit", function (ev) {
        var btn = f.querySelector("button[type=submit], button:not([type])");
        if (!btn || btn.classList.contains("no-load")) return;
        // setTimeout(0) يعمل بعد انتهاء توزيع الحدث، فتكون defaultPrevented نهائية:
        // لو ألغى المستخدم confirm() أو فشل تحقّق HTML5 لا نقفل الزرّ إطلاقاً.
        setTimeout(function () {
          if (ev.defaultPrevented) return;
          btn.classList.add("loading");
          btn.disabled = true;
          // شبكة أمان: لو بقيت الصفحة مفتوحة أعِد الزرّ
          setTimeout(function () {
            btn.classList.remove("loading"); btn.disabled = false;
          }, 8000);
        }, 0);
      });
    });
  }

  /* ----------------------------------- 8) تمييز رابط التنقّل الحالي */
  function initActiveNav() {
    var path = window.location.pathname.replace(/\/+$/, "") || "/";
    $$(".sidebar .navlink").forEach(function (a) {
      var href = (a.getAttribute("href") || "").replace(/\/+$/, "") || "/";
      if (href === path) a.classList.add("active");
      else if (href !== "/" && path.indexOf(href) === 0) a.classList.add("active");
    });
  }

  /* -------------------------------------------------------- 9) التشغيل */
  function boot() {
    initReveal(); initRipple(); initCounters(); initNav();
    initCopy(); initFormLoading(); initActiveNav(); initConfirm();
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else { boot(); }

  /* ----------------------------------------- 10) مودال تأكيد احترافي */
  /**
   * botyallaConfirm(msg, opts) → Promise<boolean>
   * opts.icon  = "warn" (default) | "danger"
   * opts.okText / opts.cancelText  — تخصيص أزرار
   * opts.okClass — مثلاً "btn green sm" بدل الأحمر
   */
  function botyallaConfirm(msg, opts) {
    opts = opts || {};
    var overlay = document.getElementById("confirmModal");
    var msgEl   = document.getElementById("confirmMsg");
    var okBtn   = document.getElementById("confirmOk");
    var cancelBtn = document.getElementById("confirmCancel");
    var iconEl  = document.getElementById("confirmIcon");
    if (!overlay) return Promise.resolve(true); // fallback لو المودال غير موجود

    msgEl.textContent = msg;
    if (opts.okText)     okBtn.textContent = opts.okText;
    if (opts.cancelText) cancelBtn.textContent = opts.cancelText;
    if (opts.okClass)    okBtn.className = opts.okClass;
    else                 okBtn.className = "btn red sm";
    iconEl.className = "confirm-icon" + (opts.icon === "warn" ? " warn" : "");

    overlay.classList.add("show");
    okBtn.focus();

    return new Promise(function (resolve) {
      function close(result) {
        overlay.classList.remove("show");
        okBtn.removeEventListener("click", onOk);
        cancelBtn.removeEventListener("click", onCancel);
        overlay.removeEventListener("click", onBg);
        document.removeEventListener("keydown", onKey);
        resolve(result);
      }
      function onOk()     { close(true); }
      function onCancel() { close(false); }
      function onBg(e)    { if (e.target === overlay) close(false); }
      function onKey(e)   { if (e.key === "Escape") close(false); }

      okBtn.addEventListener("click", onOk);
      cancelBtn.addEventListener("click", onCancel);
      overlay.addEventListener("click", onBg);
      document.addEventListener("keydown", onKey);
    });
  }
  window.botyallaConfirm = botyallaConfirm;

  /* ربط تلقائي: أي عنصر data-confirm="رسالة" يعترض الإرسال ويعرض المودال */
  function initConfirm() {
    document.addEventListener("submit", function (ev) {
      var form = ev.target;
      var msg = form.getAttribute("data-confirm");
      if (!msg) {
        // تحقّق إن كان الزر الضاغط يحتوي data-confirm
        var btn = form.querySelector("button[data-confirm]");
        if (btn) msg = btn.getAttribute("data-confirm");
      }
      if (!msg) return;
      // لو المودال مفتوح بالفعل وجاهز (flag على الفورم)
      if (form._confirmed) { form._confirmed = false; return; }
      ev.preventDefault();
      var opts = {};
      var okClass = form.getAttribute("data-confirm-ok-class");
      if (okClass) opts.okClass = okClass;
      var iconType = form.getAttribute("data-confirm-icon");
      if (iconType) opts.icon = iconType;
      botyallaConfirm(msg, opts).then(function (yes) {
        if (yes) {
          form._confirmed = true;
          // أعد إطلاق submit بالطريقة الصحيحة
          if (form.requestSubmit) form.requestSubmit();
          else form.submit();
        }
      });
    }, true);

    // لأزرار onclick بدل forms
    document.addEventListener("click", function (ev) {
      var btn = ev.target.closest ? ev.target.closest("[data-confirm-click]") : null;
      if (!btn) return;
      var msg = btn.getAttribute("data-confirm-click");
      if (!msg) return;
      if (btn._confirmed) { btn._confirmed = false; return; }
      ev.preventDefault(); ev.stopPropagation();
      botyallaConfirm(msg).then(function (yes) {
        if (yes) { btn._confirmed = true; btn.click(); }
      });
    }, true);
  }
})();
