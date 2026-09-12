import { useEffect, useRef, useState, useCallback } from "react";
import { BY, P, t, bi, Icon, Card, Btn, Pill, Empty, PageHead } from "../kit.jsx";
import { AssetPicker, postJSON } from "../media.jsx";

/* ============================================================================
   صندوق الوارد — كل محادثات البوت، والدخول على أي محادثة والرد يدوياً.
   الرد اليدوي = «تولّي»: البوت والذكاء الاصطناعي يسكتان لهذا العميل حتى
   يُعيدها صاحب النشاط (أو تعود وحدها بعد 12 ساعة من آخر رد له).
   تحديث بالاستطلاع (لا WebSocket): gunicorn بخيوط محدودة، والاستطلاع يتوقف
   حين يكون التبويب مخفياً.
   ========================================================================== */

const hhmm = (ts) => {
  if (!ts) return "";
  const d = new Date(ts * 1000), now = new Date();
  const same = d.toDateString() === now.toDateString();
  return same ? d.toTimeString().slice(0, 5) : d.toISOString().slice(5, 10).replace("-", "/");
};

function usePoll(fn, ms, deps) {
  useEffect(() => {
    let alive = true, timer = null;
    const tick = async () => {
      if (!alive) return;
      if (!document.hidden) { try { await fn(); } catch { /* الشبكة — نعيد لاحقاً */ } }
      if (alive) timer = setTimeout(tick, ms);
    };
    tick();
    return () => { alive = false; clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
}

function ConvItem({ c, active, onOpen }) {
  const name = c.name || c.peer.replace(/^(tg|wa):/, "+");
  return (
    <button type="button" onClick={() => onOpen(c.peer)}
            className={"flex w-full cursor-pointer items-center gap-3 rounded-2xl border-0 px-3 py-3 text-start " +
                       "transition-colors duration-200 " +
                       (active ? "bg-au-violet/20 shadow-[inset_0_0_0_1px_rgb(124_108_246/0.5)]"
                               : "bg-transparent hover:bg-white/[0.05]")}>
      <span className="grid size-10 shrink-0 place-items-center rounded-full text-[15px] font-extrabold text-[#07090F]
                       bg-[linear-gradient(140deg,#8FE9FF,#B9AFFF)]">
        {(name || "?").trim().charAt(0).toUpperCase()}
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex items-center justify-between gap-2">
          <span className="truncate text-[14px] font-extrabold text-ink">{name}</span>
          <span className="shrink-0 text-[11px] text-ink-3 tnum">{hhmm(c.last_at)}</span>
        </span>
        <span className="mt-0.5 flex items-center justify-between gap-2">
          <span className="truncate text-[12.5px] text-ink-3">{c.last_text || "—"}</span>
          <span className="flex shrink-0 items-center gap-1.5">
            {c.mode === "human" && <Icon name="users" size={13} className="text-au-cyan" />}
            {c.unread > 0 && (
              <span className="grid min-w-5 place-items-center rounded-full bg-au-teal px-1.5 text-[11px] font-extrabold text-[#04140E]">
                {c.unread}
              </span>
            )}
          </span>
        </span>
      </span>
    </button>
  );
}

function Bubble({ m, botId }) {
  const mine = m.direction === "out";
  const who = m.sender === "human" ? t("inbox_you") : m.sender === "ai" ? t("inbox_ai")
            : m.sender === "bot" ? t("inbox_bot") : "";
  const skin = !mine ? "bg-white/[0.07] text-ink rounded-es-md"
    : m.sender === "human" ? "text-[#07090F] bg-[linear-gradient(120deg,#8FE9FF,#B9AFFF)] rounded-ee-md"
    : m.sender === "ai" ? "bg-au-violet/25 text-ink shadow-[inset_0_0_0_1px_rgb(124_108_246/0.45)] rounded-ee-md"
    : "bg-white/[0.035] text-ink-2 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.08)] rounded-ee-md";
  return (
    <div className={"flex " + (mine ? "justify-end" : "justify-start")}>
      <div className={"max-w-[82%] rounded-2xl px-3.5 py-2.5 " + skin}>
        {m.media_id ? (
          <a href={`/bot/${botId}/media/${m.media_id}`} target="_blank" rel="noopener"
             className="mb-1.5 block overflow-hidden rounded-xl">
            <img src={`/bot/${botId}/media/${m.media_id}`} alt="" loading="lazy"
                 className="max-h-56 w-full object-cover" />
          </a>
        ) : m.kind === "media" ? (
          <span className="mb-1 flex items-center gap-1.5 text-[12px] opacity-80"><Icon name="image" size={13} />📎</span>
        ) : null}
        {m.text && <div className="whitespace-pre-wrap break-words text-[14px] leading-relaxed">{m.text}</div>}
        <div className={"mt-1 flex items-center gap-1.5 text-[10.5px] " + (m.sender === "human" ? "text-[#07090F]/70" : "text-ink-3")}>
          {who && <span className="font-bold">{who}</span>}<span className="tnum">{hhmm(m.created_at)}</span>
        </div>
      </div>
    </div>
  );
}

export default function Inbox() {
  const { bot, canReply = false, isWa = false, windowSec = 86400 } = P;
  const [convs, setConvs] = useState(P.conversations || []);
  const [peer, setPeer] = useState(P.peer || "");
  const [msgs, setMsgs] = useState([]);
  const [conv, setConv] = useState(null);
  const [lastIn, setLastIn] = useState(0);
  const [now, setNow] = useState(Math.floor(Date.now() / 1000));
  const [text, setText] = useState("");
  const [asset, setAsset] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const lastId = useRef(0);
  const scroller = useRef(null);

  const loadList = useCallback(async () => {
    const r = await fetch(`/api/bot/${bot.id}/inbox`);
    const d = await r.json();
    setConvs(d.conversations || []);
  }, [bot.id]);

  const loadThread = useCallback(async (fresh) => {
    if (!peer) return;
    const after = fresh ? 0 : lastId.current;
    const r = await fetch(`/api/bot/${bot.id}/inbox/thread?peer=${encodeURIComponent(peer)}&after=${after}`);
    if (!r.ok) return;
    const d = await r.json();
    setConv(d.conv); setLastIn(d.lastIn || 0); setNow(d.now || Math.floor(Date.now() / 1000));
    if (fresh) setMsgs(d.messages || []);
    else if (d.messages && d.messages.length) setMsgs((x) => [...x, ...d.messages]);
    const all = d.messages || [];
    if (all.length) lastId.current = all[all.length - 1].id;
  }, [bot.id, peer]);

  usePoll(loadList, 8000, [loadList]);
  useEffect(() => { lastId.current = 0; setMsgs([]); setErr(""); if (peer) loadThread(true); }, [peer, loadThread]);
  usePoll(() => loadThread(false), 4000, [loadThread]);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs.length, peer]);
  useEffect(() => {
    const url = new URL(location.href);
    if (peer) url.searchParams.set("peer", peer); else url.searchParams.delete("peer");
    history.replaceState(null, "", url);
  }, [peer]);

  const windowClosed = isWa && lastIn && now - lastIn > windowSec;
  const human = conv && conv.mode === "human";

  async function send(e) {
    e && e.preventDefault();
    if (busy || (!text.trim() && !asset)) return;
    setBusy(true); setErr("");
    const d = await postJSON(`/bot/${bot.id}/inbox/send`, { peer, text: text.trim(), asset_id: asset || undefined });
    setBusy(false);
    if (!d.ok) { setErr(d.error || t("inbox_err_send")); return; }
    setText(""); setAsset(""); setConv(d.conv);
    loadThread(false); loadList();
  }

  async function setMode(mode) {
    const d = await postJSON(`/bot/${bot.id}/inbox/mode`, { peer, mode });
    if (d.ok) { setConv(d.conv); loadList(); } else setErr(d.error || "");
  }

  const current = convs.find((c) => c.peer === peer);
  const title = current ? (current.name || peer.replace(/^(tg|wa):/, "+")) : "";

  return (
    <>
      <PageHead icon="inbox" title={`${t("inbox_title")} · ${bot.name}`} sub={t("inbox_sub")}
        actions={<Btn variant="ghost" sm icon="back" href={`/bot/${bot.id}`}>{t("back")}</Btn>} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[320px_minmax(0,1fr)]">
        {/* القائمة — على الموبايل تختفي حين تُفتح محادثة */}
        <Card className={"!p-3 " + (peer ? "hidden lg:block" : "")}>
          {convs.length ? (
            <div className="flex max-h-[70vh] flex-col gap-1 overflow-y-auto">
              {convs.map((c) => <ConvItem key={c.peer} c={c} active={c.peer === peer} onOpen={setPeer} />)}
            </div>
          ) : <Empty icon="inbox" title={t("inbox_none")} />}
        </Card>

        <Card className={"flex min-h-[60vh] flex-col !p-0 " + (peer ? "" : "hidden lg:flex")}>
          {!peer ? (
            <div className="grid flex-1 place-items-center p-8"><Empty icon="inbox" title={t("inbox_pick")} /></div>
          ) : (
            <>
              <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3.5
                              shadow-[inset_0_-1px_0_rgb(255_255_255/0.08)]">
                <div className="flex min-w-0 items-center gap-2.5">
                  <Btn sm variant="ghost" type="button" icon="back" className="lg:hidden"
                       onClick={() => setPeer("")} aria-label={t("inbox_back")} />
                  <div className="min-w-0">
                    <div className="truncate text-[15px] font-extrabold text-ink">{title}</div>
                    <div className="text-[11.5px] text-ink-3" dir="ltr">{peer.replace(/^(tg|wa):/, isWa ? "+" : "id ")}</div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {human ? <Pill tone="on" dot>{t("inbox_mode_human")}</Pill> : <Pill tone="mute">{t("inbox_mode_bot")}</Pill>}
                  {canReply && (human
                    ? <Btn sm variant="ghost" type="button" icon="bot" onClick={() => setMode("bot")}>{t("inbox_return")}</Btn>
                    : <Btn sm type="button" icon="users" onClick={() => setMode("human")}>{t("inbox_takeover")}</Btn>)}
                </div>
              </div>

              <div ref={scroller} className="flex flex-1 flex-col gap-2.5 overflow-y-auto px-4 py-4"
                   style={{ maxHeight: "58vh" }} aria-live="polite">
                {msgs.map((m) => <Bubble key={m.id} m={m} botId={bot.id} />)}
                {!msgs.length && <div className="m-auto text-[13px] text-ink-3">…</div>}
              </div>

              <div className="px-4 pb-4 pt-3 shadow-[inset_0_1px_0_rgb(255_255_255/0.08)]">
                {!canReply ? (
                  <p className="m-0 flex flex-wrap items-center gap-2 text-[13px] text-ink-3">
                    <Icon name="lock" size={14} />{t("inbox_readonly")}
                    <a href={BY.urls.pricing} className="font-bold text-au-cyan underline-offset-4 hover:underline">
                      {t("brain_upgrade")}
                    </a>
                  </p>
                ) : (
                  <form onSubmit={send}>
                    {windowClosed && (
                      <p className="mt-0 mb-3 rounded-xl bg-yellow-400/10 px-3 py-2 text-[12.5px] text-yellow-200">
                        {t("inbox_wa_window")}{" "}
                        <a href={`/bot/${bot.id}/templates`} className="font-bold underline">{t("wa_tpl_link")}</a>
                      </p>
                    )}
                    <div className="flex items-end gap-2">
                      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2}
                                disabled={busy || windowClosed} placeholder={t("inbox_ph")}
                                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }}
                                className="min-h-[46px] w-full flex-1 resize-none rounded-xl bg-black/25 px-3.5 py-2.5 text-[14px]
                                           text-ink outline-none shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)]
                                           focus:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.8)]" />
                      <Btn type="submit" icon="rocket" disabled={busy || windowClosed || (!text.trim() && !asset)}>
                        {t("inbox_send")}
                      </Btn>
                    </div>
                    <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
                      <AssetPicker compact value={asset} onChange={(v) => setAsset(v)} />
                      <span className="text-[11.5px] text-ink-3">{t("inbox_auto_note")}</span>
                    </div>
                    {err && <p role="alert" className="mt-2 mb-0 text-[12.5px] font-bold text-red-300">{err}</p>}
                  </form>
                )}
              </div>
            </>
          )}
        </Card>
      </div>
    </>
  );
}
