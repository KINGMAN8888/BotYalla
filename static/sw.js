/* عامل خدمة BotYalla — يُقدَّم من /sw.js (نطاقه الموقع كله). ثلاث مهام فقط:
   1) الإشعارات الفورية: تصل والمتصفح/التطبيق مغلق، بأيقونة وشارة واهتزاز، والعاجل منها
      (مكالمة · عميل يطلب موظفاً) يبقى على الشاشة حتى يُلمس.
   2) صفحة «لا اتصال» بدل صفحة خطأ المتصفح حين تنقطع الشبكة.
   3) عدّاد غير المقروء على أيقونة التطبيق (Badging API).
   ⚠️ لا نخزّن أي صفحة أو بيانات للمستخدم — لوحة فيها محادثات عملاء ومدفوعات لا تُحفظ في
   ذاكرة جهاز قد يُشارَك. المخزَّن: صفحة offline الثابتة وأيقونتان. انظر AGENTS §75. */
const V = "by-v1";
const OFFLINE = "/offline";
const PRECACHE = [OFFLINE, "/static/brand/icon-192.png", "/static/brand/badge-96.png"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(V).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil((async () => {
    for (const k of await caches.keys()) if (k !== V) await caches.delete(k);
    if (self.registration.navigationPreload) { try { await self.registration.navigationPreload.enable(); } catch { /* */ } }
    await self.clients.claim();
  })());
});

self.addEventListener("fetch", (e) => {
  const r = e.request;
  if (r.mode !== "navigate" || r.method !== "GET") return;          // كل ما عدا فتح صفحة: المتصفح كالمعتاد
  e.respondWith((async () => {
    try {
      return (await e.preloadResponse) || await fetch(r);
    } catch {
      return (await caches.match(OFFLINE)) || Response.error();
    }
  })());
});

/* سفاري (آيفون/ماك) يلغي الاشتراك إن وصل دفعٌ بلا إشعار ظاهر — فيُعرض دائماً هناك. غيره:
   لو التطبيق أمام المستخدم الآن نعرض تنبيهاً داخله (أجمل ولا يتكرر) بدل إشعار النظام. */
const APPLE = /iPhone|iPad|Macintosh/.test(self.navigator.userAgent) && !/Chrome|CriOS|Edg|Firefox|FxiOS/.test(self.navigator.userAgent);

self.addEventListener("push", (e) => {
  let d = {};
  try { d = e.data ? e.data.json() : {}; } catch { d = { t: "BotYalla", b: e.data ? e.data.text() : "" }; }
  e.waitUntil((async () => {
    if (typeof d.n === "number" && self.navigator.setAppBadge) {
      try { if (d.n > 0) await self.navigator.setAppBadge(d.n); else await self.navigator.clearAppBadge(); } catch { /* */ }
    }
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    for (const w of wins) w.postMessage({ type: "by:push", d });
    const front = wins.some((w) => w.focused && w.visibilityState === "visible");
    if (front && !APPLE) return;
    const en = d.lang === "en";
    await self.registration.showNotification(d.t || "BotYalla", {
      body: d.b || "",
      icon: "/static/brand/icon-192.png",
      badge: "/static/brand/badge-96.png",
      tag: d.tag || undefined,
      renotify: !!d.tag,
      requireInteraction: !!d.ri,
      timestamp: d.ts || Date.now(),
      dir: d.dir || "auto",
      lang: d.lang || "ar",
      vibrate: d.ri ? [240, 90, 240, 90, 480] : [160, 70, 160],
      data: { u: d.u || "/home", id: d.id || 0 },
      actions: [{ action: "open", title: en ? "Open" : "فتح" }, { action: "later", title: en ? "Later" : "لاحقاً" }],
    });
  })());
});

self.addEventListener("notificationclick", (e) => {
  e.notification.close();
  if (e.action === "later") return;
  const data = e.notification.data || {};
  const url = new URL(data.u || "/home", self.location.origin);
  if (url.origin !== self.location.origin) return;                    // لا فتح لأي موقع آخر
  if (data.id) url.searchParams.set("by_n", String(data.id));         // الصفحة تعلّمه مقروءاً
  e.waitUntil((async () => {
    const wins = await self.clients.matchAll({ type: "window", includeUncontrolled: true });
    const w = wins.find((x) => new URL(x.url).origin === url.origin);
    if (w) {
      await w.focus();
      try { await w.navigate(url.href); } catch { w.postMessage({ type: "by:go", u: url.href }); }
      return;
    }
    await self.clients.openWindow(url.href);
  })());
});
