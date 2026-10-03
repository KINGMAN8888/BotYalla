/* ============================================================================
   محرك صوت «مساعد BotYalla» — بلا مكتبات.
   الاستماع: SpeechRecognition في المتصفح (مجاني، نص حيّ أثناء الكلام) — وإلا تسجيل
   مقطع (MediaRecorder) بكشف صمت بسيط يُرسل إلى /api/assistant/stt.
   النطق: صوت المتصفح لو عنده صوت عربي طبيعي (Edge: ar-EG Salma · Chrome: Google) —
   وإلا صوت Gemini من /api/assistant/tts — وأي فشل يرجع لصوت المتصفح.
   المستوى (0..1) يُبلَّغ عبر onLevel لتحريك الكرة؛ لا تُعاد رسمة React مع كل إطار.
   ========================================================================== */

const W = typeof window !== "undefined" ? window : {};
const SR = W.SpeechRecognition || W.webkitSpeechRecognition || null;
const coarse = () => { try { return W.matchMedia("(pointer: coarse)").matches; } catch { return false; } };

export const hasBrowserSTT = !!SR;
export const hasRecorder = !!(W.navigator?.mediaDevices?.getUserMedia && W.MediaRecorder);
export const canListen = (boot) => hasBrowserSTT || (hasRecorder && !!boot?.voice?.stt);
export const canSpeak = (boot) => "speechSynthesis" in W || !!boot?.voice?.tts;

/* ---------------------------------------------------------------- نصّ يُقال */
export function speakable(text) {
  return String(text || "")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/[\u{1F000}-\u{1FAFF}\u{2600}-\u{27BF}️‍]/gu, "")
    .replace(/^\s*(\d+)[.)]\s*/gm, "$1، ")
    .replace(/[«»“”*_#`]/g, "")
    .replace(/[ \t]+/g, " ")
    .trim()
    .slice(0, 700);
}

/* موافقة/رفض منطوقة على بطاقة إجراء — جمل قصيرة فقط ("اه نفّذ"، "لا مش دلوقتي") */
const norm = (s) => String(s || "").toLowerCase()
  .replace(/[ً-ْـ]/g, "").replace(/[أإآ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي")
  .replace(/[^\p{L}\p{N}\s]/gu, " ").replace(/\s+/g, " ").trim();
const YES = /(^| )(نعم|اه|ايوه|ايوا|تمام|موافق|ماشي|نفذ|نفذها|نفذه|اعملها|اعمله|اعمل|يلا|اوك|اوكي|اكيد|طبعا|ok|okay|yes|yeah|yep|sure|go ahead|do it)( |$)/;
const NO = /(^| )(لا|لأ|مش دلوقتي|بلاش|الغي|الغيها|استني|no|nope|cancel|not now|stop)( |$)/;
export function yesNo(text) {
  const t = norm(text);
  if (!t || t.split(" ").length > 6) return null;
  if (NO.test(t)) return "no";
  if (YES.test(t)) return "yes";
  return null;
}

/* ---------------------------------------------------------------- مستوى الصوت */
function meter(stream, onLevel) {
  let ctx, raf, stopped = false;
  try {
    ctx = new (W.AudioContext || W.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    const an = ctx.createAnalyser();
    an.fftSize = 512;
    src.connect(an);
    const buf = new Uint8Array(an.fftSize);
    const tick = () => {
      if (stopped) return;
      an.getByteTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; sum += v * v; }
      onLevel(Math.min(1, Math.sqrt(sum / buf.length) * 4.5));
      raf = requestAnimationFrame(tick);
    };
    tick();
  } catch { /* بلا Web Audio: الكرة تتنفّس وحدها */ }
  return () => { stopped = true; cancelAnimationFrame(raf); try { ctx && ctx.close(); } catch { /* */ } };
}

/* ---------------------------------------------------------------- الاستماع */
export function createListener({ lang, boot, csrf, onInterim, onFinal, onLevel = () => {}, onError, onEnd, onState }) {
  let rec = null, media = null, stopMeter = null, stream = null, done = false, finalText = "";

  const cleanup = () => {
    stopMeter && stopMeter(); stopMeter = null;
    stream && stream.getTracks().forEach((t) => t.stop()); stream = null;
    onLevel(0);
  };
  const finish = (text) => {
    if (done) return;
    done = true;
    cleanup();
    if (text && text.trim()) onFinal(text.trim()); else onEnd && onEnd();
  };

  async function startBrowser() {
    rec = new SR();
    rec.lang = lang === "en" ? "en-US" : "ar-EG";
    rec.interimResults = true;
    // الحاسب: استماع متصل ونحن نقرّر نهاية الكلام (أسرع بكثير من انتظار المتصفح ~2ث).
    // أندرويد: الوضع المتصل يكرّر النتائج — نتركه للمتصفح ونختصر بنفس المؤقّت.
    rec.continuous = !coarse();
    rec.maxAlternatives = 1;
    let silence = null;
    const hardStop = setTimeout(() => { try { rec.stop(); } catch { /* */ } }, 20000);
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += (finalText ? " " : "") + r[0].transcript.trim(); else interim += r[0].transcript;
      }
      onInterim && onInterim((finalText + " " + interim).trim());
      if (!stopMeter) onLevel(0.35 + Math.random() * 0.4);   // بلا مقياس حقيقي: نبضة مع كل كلمة
      clearTimeout(silence);
      // سكتّ بعد جملة كاملة ⇒ 650ms · وسط جملة ⇒ 1100ms
      silence = setTimeout(() => { try { rec.stop(); } catch { /* */ } }, interim.trim() ? 1100 : 650);
    };
    rec.addEventListener("end", () => { clearTimeout(silence); clearTimeout(hardStop); });
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      done = true; cleanup();
      onError && onError(e.error === "not-allowed" || e.error === "service-not-allowed" ? "denied" : e.error || "error");
    };
    rec.onend = () => finish(finalText);
    // على اللمس: فتح المايك مرتين (التعرّف + المقياس) يُفشل التعرّف في أندرويد — مقياس على الحاسب فقط
    if (!coarse() && W.navigator?.mediaDevices?.getUserMedia) {
      try {
        stream = await W.navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
        stopMeter = meter(stream, onLevel);
      } catch (e) {
        if (e && e.name === "NotAllowedError") { done = true; onError && onError("denied"); return; }
      }
    }
    rec.start();
    onState && onState("listening");
  }

  async function startRecorder() {
    try {
      stream = await W.navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    } catch (e) {
      done = true; onError && onError(e && e.name === "NotAllowedError" ? "denied" : "mic"); return;
    }
    const types = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];
    const mime = types.find((t) => W.MediaRecorder.isTypeSupported && W.MediaRecorder.isTypeSupported(t)) || "";
    media = new W.MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks = [];
    media.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
    // كشف صمت: بدأ الكلام ثم 1.3ث هدوء ⇒ إنهاء · لا كلام خلال 7ث ⇒ إلغاء · 20ث حدّ أقصى
    let spoke = false, quietSince = 0;
    const t0 = Date.now();
    stopMeter = meter(stream, (lvl) => {
      onLevel(lvl);
      const now = Date.now();
      if (lvl > 0.12) { spoke = true; quietSince = 0; } else if (spoke && !quietSince) quietSince = now;
      if (media && media.state === "recording" &&
          ((spoke && quietSince && now - quietSince > 1300) || (!spoke && now - t0 > 7000) || now - t0 > 20000)) {
        media.stop();
      }
    });
    media.onstop = async () => {
      const heard = spoke;
      cleanup();
      if (done) return;
      if (!heard || !chunks.length) { finish(""); return; }
      onState && onState("thinking");
      const blob = new Blob(chunks, { type: (mime || "audio/webm").split(";")[0] });
      try {
        const r = await fetch(boot.stt, { method: "POST", credentials: "same-origin",
          headers: { "Content-Type": blob.type, "X-CSRF-Token": csrf || "" }, body: blob });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || !d.ok) { done = true; onError && onError(d.error || "stt"); return; }
        finish(d.text || "");
      } catch { done = true; onError && onError("offline"); }
    };
    media.start(250);
    onState && onState("listening");
  }

  return {
    start() {
      done = false; finalText = "";
      if (hasBrowserSTT) startBrowser().catch(() => { done = true; onError && onError("error"); });
      else if (hasRecorder && boot?.voice?.stt) startRecorder();
      else onError && onError("unsupported");
    },
    /* إنهاء الآن وإرسال ما قيل */
    stop() {
      if (rec) { try { rec.stop(); } catch { /* */ } }
      else if (media && media.state === "recording") media.stop();
    },
    /* إلغاء بلا إرسال */
    abort() {
      done = true;
      if (rec) { try { rec.abort(); } catch { /* */ } }
      if (media && media.state === "recording") { try { media.stop(); } catch { /* */ } }
      cleanup();
    },
  };
}

/* ---------------------------------------------------------------- النطق */
const NATURAL = /natural|neural|online|google|premium|enhanced|siri/i;
let voicesCache = [];
function voices() {
  try { voicesCache = W.speechSynthesis.getVoices() || voicesCache; } catch { /* */ }
  return voicesCache;
}
if ("speechSynthesis" in W) {
  try { W.speechSynthesis.onvoiceschanged = voices; voices(); } catch { /* */ }
}
export function pickVoice(lang) {
  const all = voices();
  const want = lang === "en" ? /^en/i : /^ar/i;
  const cands = all.filter((v) => want.test(v.lang));
  const score = (v) => (NATURAL.test(v.name) ? 4 : 0) + (/ar-EG|en-US/i.test(v.lang) ? 2 : 0) + (v.localService ? 0 : 1);
  cands.sort((a, b) => score(b) - score(a));
  const v = cands[0] || null;
  return { voice: v, natural: !!v && NATURAL.test(v.name) };
}

/* Chrome يقطع النطق الطويل بعد ~15ث — نقسّم على الجُمل */
function sentences(t) {
  const parts = t.split(/(?<=[.!?؟\n،])\s+/).map((s) => s.trim()).filter(Boolean);
  const out = [];
  for (const p of parts) {
    if (out.length && out.length > 1 && (out[out.length - 1] + " " + p).length < 200) out[out.length - 1] += " " + p; else out.push(p);
  }
  return out;
}

export function createSpeaker({ boot, csrf, lang, onLevel = () => {} }) {
  let audio = null, url = null, stopMeter = null, token = 0, pulse = null, release = null;

  const stopAll = () => {
    token++;
    clearInterval(pulse); pulse = null;
    if (release) { release(); release = null; }       // مقاطعة: الوعد المنتظر ينتهي فوراً لا يعلق
    if (audio) { try { audio.pause(); } catch { /* */ } audio = null; }
    if (url) { URL.revokeObjectURL(url); url = null; }
    stopMeter && stopMeter(); stopMeter = null;
    try { W.speechSynthesis && W.speechSynthesis.cancel(); } catch { /* */ }
    onLevel(0);
  };

  function browserSay(text, my) {
    return new Promise((resolve) => {
      if (!("speechSynthesis" in W)) return resolve();
      release = resolve;
      const { voice } = pickVoice(lang);
      const parts = sentences(text);
      let i = 0;
      pulse = setInterval(() => onLevel(0.25 + Math.random() * 0.55), 110);
      const next = () => {
        if (my !== token || i >= parts.length) { clearInterval(pulse); pulse = null; onLevel(0); return resolve(); }
        const u = new SpeechSynthesisUtterance(parts[i++]);
        if (voice) u.voice = voice;
        u.lang = voice ? voice.lang : (lang === "en" ? "en-US" : "ar-EG");
        u.rate = 1.02;
        u.onend = next;
        u.onerror = next;
        W.speechSynthesis.speak(u);
      };
      next();
    });
  }

  /* الجُمل تُطلب كلها معاً وتُشغَّل بالترتيب: الصوت يبدأ مع أول جملة لا بعد الرد كله */
  const fetchTts = (text) => fetch(boot.tts, { method: "POST", credentials: "same-origin",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf || "" }, body: JSON.stringify({ text }) })
    .then((r) => (r.status === 200 ? r.blob() : null)).then((b) => (b && b.size ? b : null)).catch(() => null);

  async function serverSay(text, my) {
    const parts = sentences(text).slice(0, 5);
    const jobs = parts.map(fetchTts);
    for (let i = 0; i < parts.length; i++) {
      const blob = await jobs[i];
      if (my !== token) return true;
      if (!blob) {
        if (i === 0) return false;                       // الخادم لا ينطق ⇒ صوت المتصفح للرد كله
        await browserSay(parts.slice(i).join(" "), my);
        return true;
      }
      if (!(await playBlob(blob, my))) return true;
    }
    return true;
  }

  async function playBlob(blob, my) {
    try {
      if (my !== token) return false;
      url = URL.createObjectURL(blob);
      audio = new Audio(url);
      try {
        const ctx = new (W.AudioContext || W.webkitAudioContext)();
        const src = ctx.createMediaElementSource(audio);
        const an = ctx.createAnalyser();
        an.fftSize = 512; src.connect(an); an.connect(ctx.destination);
        const buf = new Uint8Array(an.fftSize);
        let raf, live = true;
        const tick = () => {
          if (!live) return;
          an.getByteTimeDomainData(buf);
          let s = 0; for (let i = 0; i < buf.length; i++) { const v = (buf[i] - 128) / 128; s += v * v; }
          onLevel(Math.min(1, Math.sqrt(s / buf.length) * 5));
          raf = requestAnimationFrame(tick);
        };
        tick();
        stopMeter = () => { live = false; cancelAnimationFrame(raf); try { ctx.close(); } catch { /* */ } };
      } catch { pulse = setInterval(() => onLevel(0.3 + Math.random() * 0.5), 110); }
      await new Promise((resolve) => {
        release = resolve;
        audio.onended = resolve; audio.onerror = resolve;
        audio.play().catch(resolve);
      });
      release = null;
      stopMeter && stopMeter(); stopMeter = null; clearInterval(pulse); pulse = null; onLevel(0);
      if (url) { URL.revokeObjectURL(url); url = null; }
      return my === token;
    } catch { return false; }
  }

  return {
    /* يُنادى داخل ضغطة المستخدم — يفتح النطق في Safari/Chrome قبل أول رد */
    unlock() {
      try { const u = new SpeechSynthesisUtterance(" "); u.volume = 0; W.speechSynthesis.speak(u); } catch { /* */ }
    },
    async say(text) {
      stopAll();
      const my = token;
      const t = speakable(text);
      if (!t) return;
      const { natural } = pickVoice(lang);
      if (!natural && boot?.voice?.tts && (await serverSay(t, my))) return;
      if (my !== token) return;
      await browserSay(t, my);
    },
    stop: stopAll,
  };
}
