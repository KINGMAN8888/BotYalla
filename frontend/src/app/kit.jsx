import { useRef, useEffect, useLayoutEffect, useState, useCallback, useId, Children, isValidElement } from "react";
import { createPortal } from "react-dom";
import { motion, useInView, useReducedMotion, animate, AnimatePresence } from "motion/react";

/* ============================================================================
   عناصر واجهة مشتركة للوحة التحكم. البيانات كلها من الخادم (window.BY).
   ========================================================================== */
export const BY = window.BY || { t: {}, urls: {}, icons: {}, props: {}, nav: [], adminNav: [] };
export const t = (k) => (BY.t[k] != null ? BY.t[k] : k);
export const P = BY.props || {};
export const isRTL = BY.dir === "rtl";
export const AR = BY.lang === "ar";

/* نصّ قصير ثنائي اللغة للحالات النادرة جداً فقط */
export const bi = (ar, en) => (AR ? ar : en);

export const fmtDate = (ts) =>
  ts ? new Date(Number(ts) * 1000).toISOString().slice(0, 10) : "—";
export const daysLeft = (ts) =>
  ts ? Math.max(0, Math.floor((Number(ts) - Date.now() / 1000) / 86400)) : 0;
export const num = (v) => Number(v || 0).toLocaleString("en-US");

/* ------------------------------------------------------------------ أيقونة */
export function Icon({ name, size = 18, className = "" }) {
  const svg = BY.icons[name];
  if (!svg) return null;
  return (
    <span aria-hidden="true" style={{ width: size, height: size }}
          className={"inline-flex shrink-0 items-center justify-center " + className}
          dangerouslySetInnerHTML={{ __html: svg }} />
  );
}

/* ------------------------------------------------- ظهور تدريجي (CSS-first) */
export function Reveal({ children, delay = 0, className = "" }) {
  const ref = useRef(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const show = () => el.classList.add("in");
    if (!("IntersectionObserver" in window)) { show(); return; }
    const io = new IntersectionObserver(
      (es) => es.forEach((e) => { if (e.isIntersecting) { show(); io.unobserve(el); } }),
      { threshold: 0.08, rootMargin: "0px 0px -40px 0px" }
    );
    io.observe(el);
    // شبكة أمان: المحتوى لا يبقى مخفياً أبداً بسبب حركة
    const safety = setTimeout(() => { if (!el.classList.contains("in")) show(); }, 2000);
    return () => { clearTimeout(safety); io.disconnect(); };
  }, []);
  return (
    <div ref={ref} className={"rv " + className} style={{ transitionDelay: delay + "s" }}>
      {children}
    </div>
  );
}

/* --------------------------------------------------------------- بقعة ضوء */
export function useSpotlight() {
  return useCallback((e) => {
    const el = e.currentTarget, r = el.getBoundingClientRect();
    el.style.setProperty("--mx", `${e.clientX - r.left}px`);
    el.style.setProperty("--my", `${e.clientY - r.top}px`);
  }, []);
}

/* ------------------------------------------------------------------ بطاقة */
export function Card({ children, className = "", spot = false, as: As = "div", ...rest }) {
  const onMove = useSpotlight();
  return (
    <As {...rest}
        onMouseMove={spot ? onMove : rest.onMouseMove}
        className={`glass ${spot ? "spot" : ""} relative overflow-hidden rounded-[22px] p-6 ${className}`}>
      {children}
    </As>
  );
}

/* صورة الحساب أو أول حرف من الاسم على تدرّج العلامة — في الهيدر والقائمة و«حسابي» */
export function Avatar({ src, name = "", size = 36, className = "" }) {
  const letter = (name || "?").trim().charAt(0).toUpperCase();
  const style = { width: size, height: size, fontSize: Math.round(size * 0.42) };
  return src
    ? <img src={src} alt="" style={style}
           className={`shrink-0 rounded-full object-cover shadow-[0_0_0_2px_rgb(255_255_255/0.12)] ${className}`} />
    : <span style={style}
            className={`grid shrink-0 place-items-center rounded-full font-extrabold text-[#07090F]
                        bg-[linear-gradient(135deg,#8FE9FF,#B9AFFF)] ${className}`}>{letter}</span>;
}

/* ---------------------------------------------------------------- عناوين */
export function PageHead({ icon, title, sub, actions }) {
  return (
    <div className="mb-7 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0">
        <h1 className="m-0 flex items-center gap-2.5 text-[clamp(22px,3vw,30px)] font-extrabold tracking-tight text-ink">
          {icon && <Icon name={icon} size={24} className="text-au-cyan" />}
          <span className="truncate">{title}</span>
        </h1>
        {sub && <p className="mt-1.5 mb-0 text-[14px] leading-relaxed text-ink-3">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ icon, children, extra }) {
  return (
    <div className="mb-5 flex items-center justify-between gap-3">
      <h2 className="m-0 flex items-center gap-2 text-[17px] font-extrabold tracking-tight text-ink">
        {icon && <Icon name={icon} size={18} className="text-au-cyan" />}
        {children}
      </h2>
      {extra}
    </div>
  );
}

/* ------------------------------------------------------------------ أزرار */
const BTN_BASE =
  "relative inline-flex items-center justify-center gap-2 overflow-hidden rounded-xl " +
  "px-4 py-2.5 text-[14px] font-bold no-underline whitespace-nowrap cursor-pointer border-0 " +
  "transition-[transform,box-shadow,background,color] duration-300 " +
  "ease-[cubic-bezier(0.175,0.885,0.32,1.275)] active:scale-[0.97] " +
  "disabled:opacity-50 disabled:cursor-not-allowed disabled:active:scale-100";

const SKINS = {
  primary: "text-[#07090F] bg-[linear-gradient(100deg,#8FE9FF,#B9AFFF)] " +
           "shadow-[0_8px_24px_-8px_rgb(124_108_246/0.7)] hover:-translate-y-0.5 " +
           "hover:shadow-[0_14px_32px_-8px_rgb(124_108_246/0.9)]",
  ghost:   "text-ink bg-white/[0.04] shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] " +
           "hover:bg-white/[0.09] hover:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.2)]",
  green:   "text-[#04140E] bg-[linear-gradient(100deg,#5EEAD4,#2DD4A7)] " +
           "shadow-[0_8px_24px_-8px_rgb(45_212_167/0.7)] hover:-translate-y-0.5",
  red:     "text-[#2A0A0A] bg-[linear-gradient(100deg,#FCA5A5,#F87171)] " +
           "shadow-[0_8px_24px_-8px_rgb(248_113_113/0.6)] hover:-translate-y-0.5",
};

export function Btn({ children, variant = "primary", icon, sm, block, as, href, ...rest }) {
  const cls = `${BTN_BASE} ${SKINS[variant] || SKINS.primary} ` +
              (sm ? "!px-3 !py-2 !text-[13px] !rounded-[10px] " : "") +
              (block ? "w-full " : "") + (rest.className || "");
  const inner = (<>{icon && <Icon name={icon} size={sm ? 14 : 16} />}{children}</>);
  if (href) return <a href={href} {...rest} className={cls}>{inner}</a>;
  const Tag = as || "button";
  return <Tag {...rest} className={cls}>{inner}</Tag>;
}

/* ------------------------------------------------------------------ حقول */
export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={"block " + className}>
      {label && <span className="mb-1.5 block text-[13px] font-bold text-ink-2">{label}</span>}
      {children}
      {hint && <span className="mt-1.5 block text-[12px] leading-relaxed text-ink-3">{hint}</span>}
    </label>
  );
}

export const INPUT =
  "w-full rounded-xl bg-black/25 px-3.5 py-2.5 text-[14px] text-ink " +
  "shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] outline-none transition-all duration-300 " +
  "placeholder:text-ink-3/70 hover:shadow-[inset_0_0_0_1px_rgb(255_255_255/0.18)] " +
  "focus:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.8),0_0_0_3px_rgb(124_108_246/0.18)]";

export const Input = (p) => <input {...p} className={`${INPUT} ${p.className || ""}`} />;
export const Textarea = (p) => (
  <textarea {...p} className={`${INPUT} min-h-[96px] resize-y ${p.className || ""}`} />
);
/* قائمة منسدلة بمظهر المنصة. تحتها <select> حقيقي مخفي: هو ما يُرسَل مع النموذج،
   وهو نفسه ما يصل للمستدعي في onChange — فيعمل `e.target.value` و`e.target.form`
   كالعنصر الأصلي. القيمة الجديدة تُكتب فيه **قبل** onChange، فنموذج يُرسَل من داخله
   (تغيير الدور/الباقة في لوحة الأدمن) يحمل الاختيار الجديد لا القديم.
   لوحة المفاتيح: الأسهم · Enter/مسافة · Esc. */
export function Select({ children, className = "", value: controlledValue, defaultValue, onChange,
                         disabled, ...rest }) {
  const options = [];
  Children.forEach(children, (child) => {
    if (isValidElement(child) && child.type === "option") {
      options.push({
        value: child.props.value !== undefined ? child.props.value : child.props.children,
        label: child.props.children,
        disabled: !!child.props.disabled,
      });
    }
  });

  const [isOpen, setIsOpen] = useState(false);
  const [active, setActive] = useState(-1);
  // بلا قيمة مبدئية يختار المتصفح أول خيار — فنعرض الشيء نفسه الذي سيُرسَل
  const [internalValue, setInternalValue] = useState(
    () => (defaultValue != null ? defaultValue : options[0] ? options[0].value : ""));
  const containerRef = useRef(null);
  const selectRef = useRef(null);
  const btnRef = useRef(null);
  const menuRef = useRef(null);
  const [pos, setPos] = useState(null);
  const listId = useId();

  const isControlled = controlledValue !== undefined;
  const value = isControlled ? controlledValue : internalValue;
  const selectedIdx = options.findIndex((o) => String(o.value) === String(value));
  const displayLabel = selectedIdx >= 0 ? options[selectedIdx].label : "—";

  /* القائمة تُرسم في <body> بموضع ثابت تحت الزر، طافيةً فوق الصفحة كالقائمة الأصلية:
     داخل التدفق كانت تزيح ما بجانبها، و`absolute` كانت ستُقصّ داخل البطاقات
     (overflow-hidden) والجداول (overflow-x-auto). تنقلب لأعلى لو لا مكان تحتها. */
  const place = useCallback(() => {
    const b = btnRef.current;
    if (!b) return;
    const r = b.getBoundingClientRect();
    const vh = window.innerHeight, vw = window.innerWidth, gap = 6, margin = 8;
    const below = vh - r.bottom - gap - margin, above = r.top - gap - margin;
    const want = Math.min(240, options.length * 38 + 12);
    const up = below < want && above > below;
    const w = Math.max(r.width, 160);                     // زر ضيق (جدول الأدمن) لا يضيّق الخيارات
    const left = Math.min(Math.max(margin, isRTL ? r.right - w : r.left), vw - w - margin);
    setPos({ left, width: w, up,
             top: up ? undefined : r.bottom + gap,
             bottom: up ? vh - r.top + gap : undefined,
             maxH: Math.max(96, Math.min(240, up ? above : below)) });
  }, [options.length]);

  useLayoutEffect(() => {
    if (!isOpen) { setPos(null); return; }
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);       // capture: أي حاوية تُمرَّر، لا الصفحة وحدها
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [isOpen, place]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e) => {
      const inside = (el) => el && el.contains(e.target);
      if (!inside(containerRef.current) && !inside(menuRef.current)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [isOpen]);

  useEffect(() => {
    if (isOpen && active >= 0) {
      document.getElementById(`${listId}-${active}`)?.scrollIntoView({ block: "nearest" });
    }
  }, [isOpen, active, listId]);

  const open = () => {
    if (disabled) return;
    setActive(selectedIdx >= 0 ? selectedIdx : 0);
    setIsOpen(true);
  };

  const choose = (opt) => {
    if (!opt || opt.disabled) return;
    setIsOpen(false);
    const el = selectRef.current;
    if (!el || String(opt.value) === String(value)) return;   // كالأصلي: لا change لنفس القيمة
    el.value = String(opt.value);
    if (!isControlled) setInternalValue(opt.value);
    if (onChange) onChange({ target: el, currentTarget: el, preventDefault() {}, stopPropagation() {} });
  };

  const move = (d) => setActive((a) => {
    let i = a;
    for (let k = 0; k < options.length; k++) {
      i = (i + d + options.length) % options.length;
      if (!options[i].disabled) return i;
    }
    return a;
  });

  const onKeyDown = (e) => {
    const k = e.key;
    if (!isOpen) {
      if (k === "ArrowDown" || k === "ArrowUp" || k === "Enter" || k === " ") { e.preventDefault(); open(); }
      return;
    }
    if (k === "Escape") { e.preventDefault(); setIsOpen(false); }
    else if (k === "Tab") setIsOpen(false);
    else if (k === "ArrowDown" || k === "ArrowUp") { e.preventDefault(); move(k === "ArrowDown" ? 1 : -1); }
    else if (k === "Enter" || k === " ") { e.preventDefault(); choose(options[active]); }
  };

  return (
    <div ref={containerRef} className="relative">
      {/* الزر قبل <select>: أول عنصر قابل للتسمية داخل <label> الحقل هو ما يسمّيه،
          فيقرأ قارئ الشاشة اسم الحقل، والنقر على العنوان يفتح القائمة.
          (نقرات الخيارات تُلغى افتراضياً فلا يعيد الـlabel فتحها.) */}
      <button
        ref={btnRef} type="button" disabled={disabled} role="combobox" aria-haspopup="listbox"
        aria-expanded={isOpen} aria-controls={listId}
        aria-activedescendant={isOpen && active >= 0 ? `${listId}-${active}` : undefined}
        onClick={() => (isOpen ? setIsOpen(false) : open())}
        onKeyDown={onKeyDown}
        onKeyUp={(e) => { if (e.key === " ") e.preventDefault(); }}
        className={`${INPUT} flex cursor-pointer select-none items-center justify-between gap-2 text-start ` +
                   `disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
      >
        <span className="truncate">{displayLabel}</span>
        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none"
             stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
             className={`shrink-0 text-ink-3 transition-transform duration-300 ${isOpen ? "rotate-180" : ""}`}>
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </button>

      <select ref={selectRef} {...rest} disabled={disabled} value={value} onChange={() => {}}
              tabIndex={-1} aria-hidden="true" className="sr-only">
        {children}
      </select>

      {createPortal(
      <AnimatePresence>
        {isOpen && pos && (
          <motion.div
            ref={menuRef} id={listId} role="listbox"
            // الضغط داخل القائمة لا يسحب التركيز من الزر (الأسهم تبقى تعمل)
            onMouseDown={(e) => e.preventDefault()}
            initial={{ opacity: 0, y: pos.up ? 8 : -8, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: pos.up ? 8 : -8, scale: 0.98 }}
            transition={{ duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
            style={{ position: "fixed", left: pos.left, width: pos.width, top: pos.top,
                     bottom: pos.bottom, maxHeight: pos.maxH }}
            className="z-[1000] overflow-y-auto overscroll-contain rounded-xl bg-[rgb(17_18_32/0.97)] p-1.5
                       backdrop-blur-xl shadow-[0_18px_40px_-12px_rgb(0_0_0/0.75),inset_0_0_0_1px_rgb(255_255_255/0.1)]
                       [scrollbar-width:thin] [scrollbar-color:rgb(255_255_255/0.18)_transparent]"
          >
            {options.map((opt, i) => (
              <div
                key={i} id={`${listId}-${i}`} role="option" aria-selected={i === selectedIdx}
                aria-disabled={opt.disabled || undefined}
                onMouseEnter={() => setActive(i)}
                onClick={(e) => { e.preventDefault(); choose(opt); }}
                className={`rounded-lg px-3 py-2 text-[13.5px] transition-colors ${
                  opt.disabled ? "cursor-not-allowed opacity-50 text-ink-3"
                  : i === selectedIdx
                    ? "cursor-pointer bg-[linear-gradient(120deg,rgba(124,108,246,0.15),rgba(34,211,238,0.05))] text-au-cyan font-bold"
                  : i === active ? "cursor-pointer bg-white/[0.06] text-ink"
                  : "cursor-pointer text-ink-2 hover:bg-white/[0.04] hover:text-ink"
                }`}
              >
                {opt.label}
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>,
      document.body)}
    </div>
  );
}

/* -------------------------------------------------------------- شارة/حبّة */
export function Pill({ tone = "on", children, dot }) {
  const tones = {
    on:   "bg-au-teal/15 text-au-teal",
    off:  "bg-red-400/15 text-red-300",
    warn: "bg-yellow-400/15 text-yellow-300",
    mute: "bg-white/5 text-ink-3",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11.5px] font-extrabold ${tones[tone]}`}>
      {dot && <i className="block size-1.5 rounded-full bg-current blip" />}
      {children}
    </span>
  );
}

/* ---------------------------------------------------------------- إحصاءة */
export function Stat({ icon, value, label, decimals = 0 }) {
  return (
    <Card className="!p-5">
      <Icon name={icon} size={20} className="text-au-cyan" />
      <div className="mt-2.5 text-[26px] font-extrabold leading-none tracking-tight text-ink">
        <Counter value={Number(value) || 0} decimals={decimals} />
      </div>
      <div className="mt-1.5 text-[13px] text-ink-3">{label}</div>
    </Card>
  );
}

export function Counter({ value, decimals = 0 }) {
  const ref = useRef(null);
  const inView = useInView(ref, { once: true, amount: 0.4 });
  const reduce = useReducedMotion();
  const [n, setN] = useState(reduce ? value : 0);
  useEffect(() => {
    if (!inView || reduce) {
      const s = setTimeout(() => setN(value), reduce ? 0 : 1600);
      return () => clearTimeout(s);
    }
    const c = animate(0, value, { duration: 1.2, ease: [0.16, 1, 0.3, 1],
                                  onUpdate: setN, onComplete: () => setN(value) });
    // rAF يتوقف في تبويب مخفي فيتجمّد العدّاد على رقم جزئي — وهو رقم خاطئ
    // يقرأه المستخدم كإحصائية. setTimeout يُبطّأ في الخلفية لكنه يعمل.
    const s = setTimeout(() => setN(value), 1600);
    return () => { c.stop(); clearTimeout(s); };
  }, [inView, value, reduce]);
  return <span ref={ref} className="tnum">{decimals ? n.toFixed(decimals) : num(Math.round(n))}</span>;
}

/* ---------------------------------------------------------------- جدول */
export function Table({ head, children }) {
  return (
    <div className="-mx-2 overflow-x-auto px-2">
      <table className="w-full border-collapse text-[14px]">
        <thead>
          <tr>
            {head.map((h, i) => (
              <th key={i} className="whitespace-nowrap px-3 py-3 text-start text-[11.5px] font-extrabold
                                     uppercase tracking-wider text-ink-3
                                     shadow-[inset_0_-1px_0_rgb(255_255_255/0.08)]">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
export const Tr = ({ children }) => (
  <tr className="transition-colors duration-200 hover:bg-white/[0.035]">{children}</tr>
);
export const Td = ({ children, className = "" }) => (
  <td className={`px-3 py-3.5 align-middle text-ink-2 shadow-[inset_0_-1px_0_rgb(255_255_255/0.05)] ${className}`}>
    {children}
  </td>
);

/* ------------------------------------------------------------ حالة فارغة */
export function Empty({ icon, title, text, action }) {
  return (
    <div className="py-12 text-center">
      <span className="mx-auto mb-4 grid size-16 place-items-center rounded-2xl text-au-cyan
                       bg-[linear-gradient(150deg,rgb(124_108_246/0.25),rgb(34_211_238/0.1))]
                       shadow-[inset_0_0_0_1px_rgb(255_255_255/0.09)]">
        <Icon name={icon} size={28} />
      </span>
      <h3 className="m-0 mb-2 text-[17px] font-extrabold text-ink">{title}</h3>
      {text && <p className="mx-auto mb-5 max-w-[420px] text-[14px] leading-relaxed text-ink-3">{text}</p>}
      {action}
    </div>
  );
}

/* ------------------------------------------------------ نموذج POST بـ CSRF
   النماذج تبقى POST حقيقية إلى Flask — لا API ولا تغيير في طبقة الأمان. */
export function Form({ action, children, confirm, ...rest }) {
  const onSubmit = (e) => {
    if (confirm && !window.confirm(confirm)) { e.preventDefault(); return; }
    if (rest.onSubmit) rest.onSubmit(e);
  };
  return (
    <form method="post" action={action} {...rest} onSubmit={onSubmit}>
      <input type="hidden" name="csrf_token" value={BY.csrf} />
      {children}
    </form>
  );
}

/* شبكة متجاوبة */
export const Grid = ({ cols = 4, children, className = "" }) => (
  <div className={`grid gap-4 ${
    cols === 2 ? "sm:grid-cols-2" : cols === 3 ? "sm:grid-cols-2 lg:grid-cols-3" :
    "sm:grid-cols-2 lg:grid-cols-4"} ${className}`}>{children}</div>
);
