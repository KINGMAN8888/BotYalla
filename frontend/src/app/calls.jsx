/* هاتف المتصفح لمكالمات واتساب (المرحلة 8): يستطلع ما يرنّ، ويرد بـ WebRTC — عرض Meta ⇒ جواب المتصفح ⇒ الخادم
   يرسله (pre_accept ثم accept). الصوت مباشر بين المتصفح وخوادم Meta؛ الخادم لا يمرّ به صوت. */
import { useEffect, useRef, useState } from "react";
import { BY, bi, Icon, Btn } from "./kit.jsx";

async function call(url, body, method = "POST") {
  try {
    const r = await fetch(url, method === "GET" ? { headers: { Accept: "application/json" } } : {
      method, headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf }, body: JSON.stringify(body || {}),
    });
    return { status: r.status, ...(await r.json().catch(() => ({ ok: false }))) };
  } catch { return { ok: false, error: "network" }; }
}
const label = (c) => c.name || c.peer.replace(/^wa:/, "+");
const why = (r) => (r.error === "channel" ? bi("رقم واتساب غير مربوط بتوكن صالح", "The WhatsApp number has no valid token")
  : r.error === "sdp" ? bi("تعذّر تجهيز الصوت في المتصفح", "The browser could not prepare audio") : r.message || r.error || "");
const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/* نغمة رنين خفيفة بـ WebAudio — تتوقّف فور الرد أو الرفض أو انتهاء الرنين */
function useRing(on) {
  useEffect(() => {
    if (!on) return undefined;
    let ctx, timer;
    try {
      ctx = new (window.AudioContext || window.webkitAudioContext)();
      const beep = () => {
        const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 660; g.gain.value = 0.06; o.connect(g); g.connect(ctx.destination);
        o.start(); o.stop(ctx.currentTime + 0.35);
      };
      beep(); timer = setInterval(beep, 1600);
    } catch { /* متصفح بلا صوت */ }
    return () => { clearInterval(timer); try { ctx && ctx.close(); } catch { /* */ } };
  }, [on]);
}

export function CallBar({ onOpen }) {
  const [calls, setCalls] = useState([]);
  const [active, setActive] = useState(null);         // {id, name, peer, bot_id, start}
  const [muted, setMuted] = useState(false);
  const [err, setErr] = useState("");
  const [tick, setTick] = useState(0);
  const pc = useRef(null), stream = useRef(null), audio = useRef(null);

  useEffect(() => {
    let alive = true, t;
    const poll = async () => {
      const r = await call("/api/calls/ringing", null, "GET");
      if (!alive) return;
      if (r.ok) {
        setCalls(r.calls);
        const mine = active && r.calls.find((c) => c.id === active.id);
        if (active && !mine) cleanup();                                     // انتهت من طرف العميل
        else if (mine && active.out && mine.answer && pc.current && !pc.current.remoteDescription) {
          // مكالمتنا الصادرة: العميل ردّ — جواب Meta يكمل الاتصال الصوتي
          try { await pc.current.setRemoteDescription({ type: "answer", sdp: mine.answer }); setActive({ ...active, start: Date.now(), dialing: false }); }
          catch { setErr(bi("تعذّر إكمال الاتصال الصوتي", "Could not complete the audio connection")); hangup(); }
        }
      }
      t = setTimeout(poll, active && !active.dialing ? 4000 : active ? 1500 : 2500);
    };
    poll();
    return () => { alive = false; clearTimeout(t); };
  }, [active]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!active) return undefined; const i = setInterval(() => setTick((x) => x + 1), 1000); return () => clearInterval(i); }, [active]);

  const ringing = calls.filter((c) => c.status === "ringing" && c.sdp && (!active || c.id !== active.id));
  useRing(!active && ringing.length > 0);

  const cleanup = () => {
    try { pc.current && pc.current.close(); } catch { /* */ }
    try { stream.current && stream.current.getTracks().forEach((x) => x.stop()); } catch { /* */ }
    pc.current = null; stream.current = null; setActive(null); setMuted(false);
  };

  /* ميكروفون + اتصال WebRTC. مرشّحو ICE كاملون داخل الوصف — Meta لا تقبل trickle */
  const media = async () => {
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setErr(bi("اسمح للمتصفح باستعمال الميكروفون", "Allow microphone access")); return null;
    }
    const p = new RTCPeerConnection({ iceServers: [{ urls: "stun:stun.l.google.com:19302" }] });
    pc.current = p;
    stream.current.getTracks().forEach((tr) => p.addTrack(tr, stream.current));
    p.ontrack = (e) => { if (audio.current) { audio.current.srcObject = e.streams[0]; audio.current.play().catch(() => {}); } };
    p.onconnectionstatechange = () => { if (["failed", "closed"].includes(p.connectionState)) cleanup(); };
    return p;
  };
  const gathered = (p) => new Promise((res) => {
    if (p.iceGatheringState === "complete") return res();
    const done = () => { if (p.iceGatheringState === "complete") { p.removeEventListener("icegatheringstatechange", done); res(); } };
    p.addEventListener("icegatheringstatechange", done);
    setTimeout(res, 2500);
  });

  const answer = async (c) => {
    setErr("");
    const p = await media();
    if (!p) return;
    await p.setRemoteDescription({ type: "offer", sdp: c.sdp });
    await p.setLocalDescription(await p.createAnswer());
    await gathered(p);
    const r = await call(`/api/calls/${encodeURIComponent(c.id)}/answer`, { sdp: p.localDescription.sdp });
    if (!r.ok) {
      cleanup();
      setErr(r.error === "taken" ? bi("ردّ زميل على المكالمة", "A teammate answered this call") : bi("تعذّر الرد — ", "Could not answer — ") + why(r));
      return;
    }
    setActive({ ...c, start: Date.now() });
    onOpen && onOpen({ bot_id: c.bot_id, peer: c.peer });
  };
  /* اتصال صادر — من زر «اتصال» في رأس المحادثة (حدث by:dial) */
  const dial = async ({ bot_id, peer, name }) => {
    if (active) { setErr(bi("أنهِ المكالمة الحالية أولاً", "End the current call first")); return; }
    setErr("");
    const p = await media();
    if (!p) return;
    await p.setLocalDescription(await p.createOffer({ offerToReceiveAudio: true }));
    await gathered(p);
    const r = await call("/api/calls/start", { bot: bot_id, peer, sdp: p.localDescription.sdp });
    if (!r.ok) {
      cleanup();
      setErr(r.error === "permission" ? bi("العميل لم يمنح إذن الاتصال بعد — اطلبه أولاً", "The customer hasn't granted call permission yet — request it first")
        : r.error === "busy" ? bi("عندك مكالمة جارية", "You already have a call in progress")
        : r.error === "window" ? bi("انتهت نافذة الـ24 ساعة", "The 24-hour window has closed")
        : bi("تعذّر الاتصال — ", "Could not call — ") + why(r));
      return;
    }
    setActive({ id: r.id, bot_id, peer, name, out: true, dialing: true, start: null });
  };
  useEffect(() => {
    const h = (e) => dial(e.detail || {});
    window.addEventListener("by:dial", h);
    return () => window.removeEventListener("by:dial", h);
  });

  const reject = async (c) => {
    const r = await call(`/api/calls/${encodeURIComponent(c.id)}/reject`);
    if (r.ok || r.error === "taken") setCalls(calls.filter((x) => x.id !== c.id));
    else setErr(bi("تعذّر الرفض — ", "Could not decline — ") + why(r));
  };
  const hangup = async () => { if (active) await call(`/api/calls/${encodeURIComponent(active.id)}/hangup`); cleanup(); };
  const mute = () => { const m = !muted; stream.current && stream.current.getAudioTracks().forEach((x) => { x.enabled = !m; }); setMuted(m); };

  if (!active && !ringing.length && !err) return <audio ref={audio} autoPlay hidden />;
  return (
    <div className="fixed inset-x-3 bottom-3 z-50 mx-auto grid max-w-md gap-2 sm:inset-x-auto sm:end-5" role="status" aria-live="assertive">
      <audio ref={audio} autoPlay hidden />
      {err && <div className="rounded-2xl bg-red-500/90 px-4 py-2.5 text-[13px] font-bold text-white shadow-2xl">
        {err} <button type="button" className="ms-2 cursor-pointer border-0 bg-transparent text-white underline" onClick={() => setErr("")}>{bi("إغلاق", "Close")}</button></div>}
      {active && (
        <div className="flex items-center justify-between gap-3 rounded-2xl bg-emerald-600 px-4 py-3 text-white shadow-2xl" data-tick={tick}>
          <div className="min-w-0"><b className="block truncate" dir="auto">{label(active)}</b>
            <span className="tnum text-[12px] opacity-90">{active.dialing ? bi("يتصل… بانتظار رد العميل", "Calling… waiting for the customer")
              : `${bi("مكالمة جارية", "On call")} · ${mmss(Math.floor((Date.now() - (active.start || Date.now())) / 1000))}`}</span></div>
          <div className="flex gap-2">
            <Btn sm variant="ghost" className="!text-white" onClick={mute} aria-label={muted ? bi("إلغاء الكتم", "Unmute") : bi("كتم", "Mute")}>{muted ? "🔇" : "🎙️"}</Btn>
            <Btn sm variant="red" onClick={hangup}>{bi("إنهاء", "Hang up")}</Btn>
          </div>
        </div>
      )}
      {!active && ringing.map((c) => (
        <div key={c.id} className="flex items-center justify-between gap-3 rounded-2xl bg-[rgb(var(--menu-rgb))] px-4 py-3 shadow-2xl ring-2 ring-emerald-400/60">
          <div className="flex min-w-0 items-center gap-3">
            <span className="grid size-10 shrink-0 animate-pulse place-items-center rounded-full bg-emerald-500 text-white"><Icon name="phone" size={18} /></span>
            <div className="min-w-0"><b className="block truncate text-ink" dir="auto">{label(c)}</b>
              <span className="text-[12px] text-ink-3">{bi("مكالمة واتساب واردة", "Incoming WhatsApp call")} · {c.bot_name}</span></div>
          </div>
          <div className="flex gap-2">
            <Btn sm variant="green" onClick={() => answer(c)}>{bi("رد", "Answer")}</Btn>
            <Btn sm variant="ghost" onClick={() => reject(c)}>{bi("رفض", "Decline")}</Btn>
          </div>
        </div>
      ))}
    </div>
  );
}
