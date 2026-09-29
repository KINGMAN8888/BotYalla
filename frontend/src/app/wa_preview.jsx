/* معاينة رسالة واتساب (مظهر التطبيق الداكن) لكل أنواع القوالب — مشتركة بين Template Studio
   ومعالج البث. تقبل شكلاً موحّداً: {header:{format,text}, body, footer, buttons:[{type,text}],
   lto:{text}, cards:[{format, body, buttons}]} — و`fromComponents` تحوّل قالباً كما تعيده Meta إليه. */
import { Icon, bi } from "./kit.jsx";

export function fromComponents(components) {
  const out = { header: null, body: "", footer: "", buttons: [], lto: null, cards: [] };
  for (const c of components || []) {
    const t = (c.type || "").toUpperCase();
    if (t === "HEADER") out.header = { format: (c.format || "TEXT").toUpperCase(), text: c.text || "" };
    else if (t === "BODY") out.body = c.text || (c.add_security_recommendation !== undefined ? "{{1}} is your verification code." : "");
    else if (t === "FOOTER") out.footer = c.text || (c.code_expiration_minutes ? `This code expires in ${c.code_expiration_minutes} minutes.` : "");
    else if (t === "BUTTONS") out.buttons = (c.buttons || []).map((b) => ({ type: b.type, text: b.text || (b.type === "COPY_CODE" ? "Copy code" : "") }));
    else if (t === "LIMITED_TIME_OFFER") out.lto = { text: c.limited_time_offer?.text || "" };
    else if (t === "CAROUSEL") out.cards = (c.cards || []).map((cd) => fromComponents(cd.components));
  }
  return out;
}

const BTN_ICON = { URL: "link", PHONE_NUMBER: "phone", COPY_CODE: "copy", QUICK_REPLY: "return", OTP: "copy" };

function Buttons({ buttons }) {
  if (!buttons?.length) return null;
  const shown = buttons.length > 3 ? [...buttons.slice(0, 2), { type: "LIST", text: bi("كل الخيارات", "See all options") }] : buttons;
  return shown.map((b, i) => (
    <div key={i} className="mt-1 flex items-center justify-center gap-1.5 border-t border-white/10 pt-1.5 text-[12.5px] font-bold text-[#53bdeb]">
      <Icon name={BTN_ICON[b.type] || "menu"} size={13} />{b.text || "…"}
    </div>
  ));
}

function Media({ format, h = "h-28" }) {
  const icon = { IMAGE: "image", VIDEO: "play", DOCUMENT: "folder", LOCATION: "globe" }[format] || "image";
  return (
    <div className={`mb-1.5 grid ${h} place-items-center rounded-lg bg-white/10 text-white/60`}>
      <span className="flex flex-col items-center gap-1 text-[11px]"><Icon name={icon} size={22} />{format === "LOCATION" ? bi("موقع", "Location") : ""}</span>
    </div>
  );
}

/* `fill(text)` اختياري: يستبدل {{n}} بعيّنات للعرض */
export function WaPreview({ m, fill = (s) => s, empty }) {
  if (!m) return <div className="grid min-h-[240px] place-items-center text-[13px] text-ink-3">{empty}</div>;
  const hf = m.header?.format;
  return (
    <div className="rounded-2xl bg-[#0b141a] p-3" dir="auto">
      <div className="max-w-[310px] rounded-xl rounded-ss-sm bg-[#1f2c34] p-2 text-[13px] leading-relaxed text-[#e9edef] shadow">
        {hf && hf !== "TEXT" && hf !== "NONE" && <Media format={hf} />}
        {m.lto && (
          <div className="mb-1.5 flex items-center gap-2 rounded-lg bg-white/10 p-2">
            <Icon name="clock" size={16} className="text-[#25D366]" />
            <b className="text-[12.5px]">{m.lto.text || "…"}</b>
          </div>
        )}
        {hf === "TEXT" && m.header.text && <b className="mb-1 block">{fill(m.header.text)}</b>}
        <div className="whitespace-pre-wrap">{fill(m.body) || <span className="text-white/40">…</span>}</div>
        {m.footer && <div className="mt-1 text-[11px] text-white/50">{m.footer}</div>}
        <Buttons buttons={m.buttons} />
      </div>
      {m.cards?.length > 0 && (
        <div className="mt-2 flex gap-2 overflow-x-auto pb-1">
          {m.cards.map((c, i) => (
            <div key={i} className="w-[180px] shrink-0 rounded-xl bg-[#1f2c34] p-2 text-[12.5px] text-[#e9edef]">
              <Media format={c.header?.format || "IMAGE"} h="h-20" />
              <div className="whitespace-pre-wrap">{fill(c.body) || "…"}</div>
              <Buttons buttons={c.buttons} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
