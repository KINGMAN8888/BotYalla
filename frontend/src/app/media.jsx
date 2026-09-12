import { useEffect, useRef, useState, useCallback } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Input, PageHead, Pill, Empty, SectionTitle,
} from "./kit.jsx";

/* ============================================================================
   مكتبة الوسائط — رفع من الجهاز أو من رابط، ثم اختيار الملف في أي مكان:
   الترحيب · المنتجات · خطوات المحادثة (فيديو تفاعلي) · الحملات · صندوق الوارد.
   الخادم يفحص البايتات والحجم والحصة — هنا عرض ومساعدة فقط.
   ========================================================================== */

export const fmtSize = (n) =>
  n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round((n || 0) / 1024))} KB`;

export async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
    body: JSON.stringify(body || {}),
  });
  if (r.status === 404) return { ok: false, error: bi("غير موجود.", "Not found.") };
  try { return await r.json(); } catch { return { ok: false, error: bi("تعذّر الاتصال.", "Connection failed.") }; }
}

async function uploadAsset(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/assets/upload", {
    method: "POST", headers: { "X-CSRF-Token": BY.csrf }, body: fd,
  });
  if (r.status === 413) return { ok: false, error: t("asset_err_too_large") };
  try { return await r.json(); } catch { return { ok: false, error: bi("تعذّر الرفع.", "Upload failed.") }; }
}

/* قائمة الوسائط — تُجلب عند الحاجة فقط */
function useAssets(initial) {
  const [data, setData] = useState(initial || null);
  const reload = useCallback(async () => {
    try {
      const r = await fetch("/api/assets");
      setData(await r.json());
    } catch { setData((d) => d || { assets: [], quota: null }); }
  }, []);
  return [data, reload, setData];
}

export function AssetThumb({ a, className = "" }) {
  if (!a) return null;
  const cls = "size-full object-cover " + className;
  return a.kind === "video"
    ? <video src={a.url} muted playsInline preload="metadata" className={cls} />
    : <img src={a.url} alt={a.name || ""} loading="lazy" className={cls} />;
}

/* منطقة الرفع: سحب وإفلات · اختيار ملفات · رابط */
function Uploader({ onAdded, compact = false }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [over, setOver] = useState(false);
  const [url, setUrl] = useState("");
  const input = useRef(null);

  async function files(list) {
    setErr(""); setBusy(true);
    for (const f of Array.from(list || [])) {
      const d = await uploadAsset(f);
      if (d.ok) onAdded(d.asset, d.quota);
      else { setErr(`${f.name}: ${d.error}`); break; }
    }
    setBusy(false);
    if (input.current) input.current.value = "";
  }

  async function fromUrl(e) {
    e.preventDefault();
    if (!url.trim()) return;
    setErr(""); setBusy(true);
    const d = await postJSON("/api/assets/url", { url: url.trim() });
    setBusy(false);
    if (d.ok) { onAdded(d.asset, d.quota); setUrl(""); } else setErr(d.error);
  }

  return (
    <div>
      <button type="button" onClick={() => input.current?.click()}
              onDragOver={(e) => { e.preventDefault(); setOver(true); }}
              onDragLeave={() => setOver(false)}
              onDrop={(e) => { e.preventDefault(); setOver(false); files(e.dataTransfer.files); }}
              disabled={busy}
              className={"flex w-full cursor-pointer flex-col items-center justify-center gap-2 rounded-2xl border-0 " +
                         "text-center transition-colors duration-300 " + (compact ? "px-4 py-5 " : "px-6 py-9 ") +
                         (over ? "bg-au-violet/20 shadow-[inset_0_0_0_2px_rgb(124_108_246/0.8)]"
                               : "bg-white/[0.03] shadow-[inset_0_0_0_1.5px_rgb(255_255_255/0.14)] hover:bg-white/[0.06]")}>
        <span className="grid size-11 place-items-center rounded-xl bg-au-violet/20 text-au-cyan">
          <Icon name="upload" size={22} />
        </span>
        <span className="text-[14px] font-extrabold text-ink">
          {busy ? t("media_uploading") : t("media_upload")}
        </span>
        <span className="text-[12px] text-ink-3">{t("media_drop")}</span>
      </button>
      <input ref={input} type="file" hidden multiple accept="image/jpeg,image/png,video/mp4"
             onChange={(e) => files(e.target.files)} />

      <form onSubmit={fromUrl} className="mt-3 flex gap-2">
        <Input value={url} onChange={(e) => setUrl(e.target.value)} placeholder={t("media_url_ph")}
               dir="ltr" inputMode="url" aria-label={t("media_url")} className="min-w-0 flex-1" />
        <Btn sm variant="ghost" icon="link" type="submit" disabled={busy || !url.trim()}>{t("media_add")}</Btn>
      </form>
      <p className="mt-2 mb-0 text-[11.5px] text-ink-3">{t("media_limits")}</p>
      {err && <p role="alert" className="mt-2 mb-0 text-[12.5px] font-bold text-red-300">{err}</p>}
    </div>
  );
}

/* نافذة اختيار — تُستعمل في كل مكان يقبل ملفاً */
function PickerModal({ open, onClose, onPick, kinds }) {
  const [data, reload, setData] = useAssets();
  useEffect(() => { if (open && !data) reload(); }, [open, data, reload]);
  useEffect(() => {
    if (!open) return;
    const k = (e) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [open, onClose]);
  if (!open) return null;
  const list = (data?.assets || []).filter((a) => !kinds || kinds.includes(a.kind));
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4 backdrop-blur-sm"
         onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div role="dialog" aria-modal="true" aria-label={t("media_pick")}
           className="glass relative max-h-[88vh] w-full max-w-[720px] overflow-y-auto rounded-[22px] p-5 sm:p-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="m-0 flex items-center gap-2 text-[17px] font-extrabold text-ink">
            <Icon name="image" size={18} className="text-au-cyan" />{t("media_pick")}
          </h2>
          <Btn sm variant="ghost" type="button" onClick={onClose} aria-label={t("cancel")}><Icon name="close" size={16} /></Btn>
        </div>
        <Uploader compact onAdded={(a, q) => setData((d) => ({ assets: [a, ...((d && d.assets) || [])], quota: q }))} />
        <div className="mt-5 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {list.map((a) => (
            <button key={a.id} type="button" onClick={() => onPick(a)}
                    className="group relative aspect-square cursor-pointer overflow-hidden rounded-xl border-0 p-0
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.12)] outline-offset-2
                               focus-visible:outline-2 focus-visible:outline-au-cyan">
              <AssetThumb a={a} className="transition-transform duration-500 group-hover:scale-105" />
              {a.kind === "video" && (
                <span className="absolute start-2 top-2 grid size-7 place-items-center rounded-full bg-black/60 text-white">
                  <Icon name="play" size={13} />
                </span>
              )}
              <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-2 py-1 text-start text-[11px] text-white">
                {a.name || fmtSize(a.size)}
              </span>
            </button>
          ))}
        </div>
        {data && !list.length && <Empty icon="image" title={t("media_empty")} />}
      </div>
    </div>
  );
}

/* حقل اختيار ملف داخل نموذج: input مخفي بالمعرّف + معاينة + تغيير/إزالة.
   `value` معرّف الملف · `onChange(id|"" , asset)` اختياري للحالة الخارجية. */
export function AssetPicker({ name, value, onChange, kinds, compact = false }) {
  const [id, setId] = useState(value ? String(value) : "");
  const [asset, setAsset] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => { setId(value ? String(value) : ""); }, [value]);
  useEffect(() => {
    if (!id || (asset && String(asset.id) === id)) return;
    let alive = true;
    fetch("/api/assets").then((r) => r.json())
      .then((d) => alive && setAsset((d.assets || []).find((a) => String(a.id) === id) || null))
      .catch(() => {});
    return () => { alive = false; };
  }, [id, asset]);

  const pick = (a) => { setId(String(a.id)); setAsset(a); setOpen(false); onChange && onChange(String(a.id), a); };
  const clear = () => { setId(""); setAsset(null); onChange && onChange("", null); };

  return (
    <div className="flex flex-wrap items-center gap-3">
      {name && <input type="hidden" name={name} value={id} />}
      {id && asset && (
        <span className={"relative block shrink-0 overflow-hidden rounded-xl shadow-[inset_0_0_0_1px_rgb(255_255_255/0.14)] " +
                         (compact ? "size-11" : "size-16")}>
          <AssetThumb a={asset} />
          {asset.kind === "video" && (
            <span className="absolute inset-0 grid place-items-center bg-black/30 text-white"><Icon name="play" size={14} /></span>
          )}
        </span>
      )}
      <Btn sm variant="ghost" icon="image" type="button" onClick={() => setOpen(true)}>
        {id ? t("media_change") : t("media_pick")}
      </Btn>
      {id && <Btn sm variant="ghost" type="button" onClick={clear}>{t("media_remove")}</Btn>}
      <PickerModal open={open} onClose={() => setOpen(false)} onPick={pick} kinds={kinds} />
    </div>
  );
}

/* ------------------------------------------------------------ صفحة المكتبة */
export function MediaLibrary() {
  const [data, , setData] = useAssets({ assets: P.assets || [], quota: P.quota || null });
  const [busyId, setBusyId] = useState(null);
  const q = data.quota;
  const pct = q && q.limit ? Math.min(100, Math.round((q.used / q.limit) * 100)) : 0;

  async function del(a) {
    if (!window.confirm(t("media_delete_q"))) return;
    setBusyId(a.id);
    const d = await postJSON(`/api/assets/${a.id}/delete`);
    setBusyId(null);
    if (d.ok) setData((x) => ({ assets: x.assets.filter((y) => y.id !== a.id), quota: d.quota }));
  }

  return (
    <>
      <PageHead icon="image" title={t("media_title")} sub={t("media_sub")} />
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <Card className="h-fit">
          <SectionTitle icon="upload">{t("media_upload")}</SectionTitle>
          <Uploader onAdded={(a, quota) => setData((x) => ({ assets: [a, ...x.assets], quota }))} />
          {q && (
            <div className="mt-5">
              <div className="flex justify-between text-[12.5px] font-bold text-ink-3">
                <span>{t("media_quota").replace("{a}", fmtSize(q.used))
                                        .replace("{b}", q.limit ? fmtSize(q.limit) : "∞")}</span>
                {q.limit ? <span className="tnum">{pct}%</span> : null}
              </div>
              {q.limit ? (
                <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
                  <div className={"h-full rounded-full " + (pct > 85 ? "bg-red-400" : "bg-au-teal")}
                       style={{ width: pct + "%" }} />
                </div>
              ) : null}
            </div>
          )}
          <p className="mt-5 mb-0 text-[12px] leading-relaxed text-ink-3">{t("media_used_in")}</p>
        </Card>

        <Card>
          <SectionTitle icon="image" extra={<Pill tone="mute">{data.assets.length}</Pill>}>{t("media_title")}</SectionTitle>
          {data.assets.length ? (
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
              {data.assets.map((a) => (
                <figure key={a.id} className="group m-0 overflow-hidden rounded-2xl bg-black/25
                                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">
                  <div className="relative aspect-square overflow-hidden">
                    {a.kind === "video"
                      ? <video src={a.url} controls preload="metadata" playsInline className="size-full object-cover" />
                      : <a href={a.url} target="_blank" rel="noopener"><AssetThumb a={a} /></a>}
                  </div>
                  <figcaption className="flex items-center justify-between gap-2 px-3 py-2.5">
                    <span className="min-w-0">
                      <span className="block truncate text-[12.5px] font-bold text-ink">{a.name || "—"}</span>
                      <span className="text-[11px] text-ink-3">{a.kind === "video" ? "MP4" : a.mime.split("/")[1].toUpperCase()} · {fmtSize(a.size)}</span>
                    </span>
                    <Btn sm variant="ghost" type="button" icon="trash" disabled={busyId === a.id}
                         onClick={() => del(a)} aria-label={t("media_delete")} />
                  </figcaption>
                </figure>
              ))}
            </div>
          ) : <Empty icon="image" title={t("media_empty")} />}
        </Card>
      </div>
    </>
  );
}
