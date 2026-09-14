#!/usr/bin/env python3
"""Markdown → PDF بتصميم احترافي مميّز، بدعم كامل للعربية (RTL).

لماذا المتصفح لا reportlab: العربية تحتاج تشكيل الحروف وربطها واتجاهاً
ثنائياً — يتقنه محرّك المتصفح وحده هنا. وCSS يعطينا تحكماً تصميمياً كاملاً.

الإثراء البصري يتم بالكشف عن الأنماط، لا بتلويث الماركداون:
  · «## N) عنوان»            → فاصل قسم برقم شبحي ضخم
  · جدول من عمودين بأرقام    → شريط بطاقات إحصائية
  · اقتباس يبدأ بإيموجي      → صندوق تنبيه مصنّف (تحذير/رؤية/نجاح/خطر)
"""
import re, asyncio
from pathlib import Path
import markdown
from playwright.async_api import async_playwright

# ===== هوية BotYalla =====
BG, INK, BODY = "#05070D", "#0F172A", "#3A4557"
CY, CYD, VIO = "#8FE9FF", "#0A6E82", "#6D5DD3"
MUT, LINE, SOFT = "#6B7280", "#E8ECF2", "#F6F9FC"
GRN, RED, AMB = "#0F7B4F", "#B3261E", "#8A6100"

CSS = f"""
@page {{ size: A4; margin: 18mm 16mm 16mm 16mm; }}
@page :first {{ margin: 0; }}
*{{box-sizing:border-box}} html,body{{margin:0;padding:0}}
body {{ font-family:'Noto Sans Arabic','Noto Naskh Arabic','Segoe UI',sans-serif;
  font-size:10.2pt; line-height:1.9; color:{BODY}; }}
body[dir=rtl]{{text-align:right}}

/* ───────── الغلاف ───────── */
.cover{{position:relative;height:297mm;width:100%;background:{BG};color:#fff;
  padding:26mm 22mm;page-break-after:always;overflow:hidden}}
.cover .orb{{position:absolute;border-radius:50%;filter:blur(0);opacity:.55}}
.orb1{{width:150mm;height:150mm;inset-inline-start:-45mm;top:-40mm;
  background:radial-gradient(circle at 35% 35%, rgba(143,233,255,.55), rgba(143,233,255,0) 62%)}}
.orb2{{width:130mm;height:130mm;inset-inline-end:-38mm;bottom:-30mm;
  background:radial-gradient(circle at 60% 40%, rgba(185,175,255,.5), rgba(185,175,255,0) 62%)}}
.orb3{{width:80mm;height:80mm;inset-inline-end:30mm;top:70mm;
  background:radial-gradient(circle at 50% 50%, rgba(143,233,255,.22), rgba(143,233,255,0) 65%)}}
/* موتيف: فقاعة محادثة */
.bubble{{position:absolute;inset-inline-end:22mm;top:26mm;width:26mm;height:20mm;
  border:1.4px solid rgba(143,233,255,.5);border-radius:6mm 6mm 6mm 1.5mm}}
.bubble i{{position:absolute;width:2.6mm;height:2.6mm;border-radius:50%;
  background:rgba(143,233,255,.85);top:8.4mm}}
.bubble i:nth-child(1){{inset-inline-start:6mm}}
.bubble i:nth-child(2){{inset-inline-start:11.5mm;opacity:.65}}
.bubble i:nth-child(3){{inset-inline-start:17mm;opacity:.4}}
.cover .mark{{position:relative;font-family:'Noto Kufi Arabic',sans-serif;font-size:12pt;
  letter-spacing:.22em;color:{CY}}}
.cover h1{{position:relative;font-family:'Noto Kufi Arabic',sans-serif;font-size:33pt;
  line-height:1.5;margin:50mm 0 0;max-width:160mm;font-weight:700;color:#fff}}
.cover .rule{{position:relative;width:42mm;height:3.5px;margin:11mm 0;
  background:linear-gradient(90deg,{CY},{VIO})}}
.cover .sub{{position:relative;font-size:14pt;color:#B6C1DA;line-height:2;max-width:150mm}}
.cover .badge{{position:relative;display:inline-block;margin-top:9mm;padding:3mm 7mm;
  border:1px solid rgba(143,233,255,.35);border-radius:999px;font-size:9.5pt;color:{CY}}}
.cover .meta{{position:absolute;bottom:24mm;font-size:9.5pt;color:#7B87A8;line-height:2.1}}

/* ───────── الفهرس ───────── */
.toc{{page-break-after:always;padding-top:4mm}}
.toc h2{{font-family:'Noto Kufi Arabic',sans-serif;font-size:20pt;color:{INK};
  margin:0 0 9mm;font-weight:700}}
.toc ol{{list-style:none;margin:0;padding:0}}
.toc li{{display:flex;align-items:baseline;gap:4mm;
  padding:3.4mm 0;border-bottom:1px solid {LINE};font-size:11pt;color:{INK}}}
.toc li b{{font-family:'Noto Kufi Arabic',sans-serif;font-size:10pt;color:{CYD};
  font-weight:700;min-width:9mm}}

/* ───────── فاصل قسم ───────── */
.sec{{position:relative;background:{INK};color:#fff;border-radius:4mm;
  padding:9mm 10mm;margin:10mm 0 6mm;overflow:hidden;page-break-after:avoid;
  page-break-inside:avoid;page-break-before:always}}
.sec.first{{page-break-before:avoid}}
.sec .ghost{{position:absolute;font-family:'Noto Kufi Arabic',sans-serif;font-size:64pt;
  font-weight:700;color:rgba(255,255,255,.07);line-height:1;top:-4mm;inset-inline-end:8mm}}
.sec h2{{position:relative;font-family:'Noto Kufi Arabic',sans-serif;font-size:17pt;
  margin:0;font-weight:700;color:#fff}}
.sec .tick{{position:relative;width:16mm;height:2.5px;background:{CY};margin-top:4mm}}

/* ───────── عناوين ───────── */
h1{{font-family:'Noto Kufi Arabic',sans-serif;font-size:18pt;color:{INK};
  margin:10mm 0 4mm;font-weight:700;page-break-after:avoid}}
h2{{font-family:'Noto Kufi Arabic',sans-serif;font-size:14pt;color:{INK};
  margin:9mm 0 3mm;font-weight:700;page-break-after:avoid}}
h3{{font-family:'Noto Kufi Arabic',sans-serif;font-size:11.5pt;color:{CYD};
  margin:7mm 0 2.5mm;font-weight:700;page-break-after:avoid}}
h4{{font-size:10.5pt;color:{INK};margin:5mm 0 2mm;font-weight:700}}
p{{margin:0 0 3.4mm}} strong{{color:{INK};font-weight:700}} em{{color:{MUT}}}
a{{color:{CYD};text-decoration:none;border-bottom:1px solid #C9E7EE}}
ul,ol{{margin:0 0 3.6mm;padding-inline-start:6.5mm}} li{{margin-bottom:1.8mm}}
code{{font-family:'DejaVu Sans Mono',monospace;font-size:8.6pt;background:{SOFT};
  padding:.5mm 1.5mm;border-radius:2px;color:{VIO};direction:ltr;
  display:inline-block;unicode-bidi:embed}}
pre{{background:{INK};border-radius:3mm;padding:5mm 6mm;direction:ltr;text-align:left;
  font-size:8.4pt;line-height:1.7;page-break-inside:avoid;color:#D7E3F4;overflow:hidden}}
pre code{{background:none;padding:0;color:#D7E3F4}}
hr{{border:none;border-top:1px solid {LINE};margin:8mm 0}}
.sec + hr, h2 + hr{{display:none}}

/* ───────── جداول ───────── */
table{{width:100%;border-collapse:separate;border-spacing:0;margin:4mm 0 6mm;
  font-size:8.9pt;page-break-inside:avoid;border:1px solid {LINE};border-radius:3mm;
  overflow:hidden}}
thead th{{background:{INK};color:#fff;font-weight:700;padding:2.8mm 3mm;
  font-family:'Noto Kufi Arabic',sans-serif;font-size:8.6pt;text-align:inherit}}
tbody td{{padding:2.6mm 3mm;border-top:1px solid {LINE};vertical-align:top;line-height:1.7}}
tbody tr:nth-child(even){{background:{SOFT}}}
table a{{border-bottom:none}}
td strong{{color:{INK}}}

/* ───────── بطاقات الأرقام ───────── */
.stats{{display:flex;gap:4mm;margin:5mm 0 7mm;page-break-inside:avoid}}
.stat{{flex:1;background:{SOFT};border:1px solid {LINE};border-radius:3.5mm;
  padding:5mm 4mm;text-align:center}}
.stat b{{display:block;font-family:'Noto Kufi Arabic',sans-serif;font-size:20pt;
  color:{CYD};font-weight:700;line-height:1.2;direction:ltr}}
.stat span{{display:block;font-size:8.4pt;color:{MUT};margin-top:2mm;line-height:1.6}}

/* ───────── صناديق التنبيه ───────── */
blockquote{{margin:5mm 0;padding:4.5mm 5mm 4.5mm 5mm;border-radius:3.5mm;
  page-break-inside:avoid;border:1px solid;font-size:9.8pt}}
blockquote p:last-child{{margin-bottom:0}}
blockquote.warn{{background:#FFFBEB;border-color:#FCD97A;color:{AMB}}}
blockquote.warn strong{{color:{AMB}}}
blockquote.danger{{background:#FEF2F2;border-color:#F7BDB8;color:{RED}}}
blockquote.danger strong{{color:{RED}}}
blockquote.ok{{background:#F0FDF5;border-color:#A7E3C4;color:{GRN}}}
blockquote.ok strong{{color:{GRN}}}
blockquote.idea{{background:#F2FBFD;border-color:#A8DDE8;color:{CYD}}}
blockquote.idea strong{{color:{CYD}}}
/* اقتباس بارز (بلا إيموجي) */
blockquote.pull{{background:{INK};border-color:{INK};color:#E6EDF8;
  font-size:12pt;line-height:2;padding:7mm 7mm}}
blockquote.pull strong{{color:{CY}}}
"""

SHELL = """<!doctype html><html lang="{lang}" dir="{dir}"><head><meta charset="utf-8">
<title>{title}</title><style>{css}</style></head><body dir="{dir}">
<section class="cover">
  <div class="orb orb1"></div><div class="orb orb2"></div><div class="orb orb3"></div>
  <div class="bubble"><i></i><i></i><i></i></div>
  <div class="mark">BOTYALLA</div>
  <h1>{ctitle}</h1><div class="rule"></div>
  <div class="sub">{csub}</div>
  <div class="badge">{cbadge}</div>
  <div class="meta">{cmeta}</div>
</section>
{toc}
<main>{body}</main></body></html>"""

NUM = re.compile(r"^[\d.,]+[%×+MKT]*$|^\+?[\d.,]+[a-zA-Zج%×]*$")


def enrich(html: str) -> str:
    """الإثراء البصري بعد تحويل الماركداون."""
    # 1) صناديق التنبيه — نوعها من أول رمز
    def bq(m):
        inner = m.group(1)
        txt = re.sub(r"<[^>]+>", "", inner)[:12]
        cls = ("warn" if "⚠" in txt else "danger" if "❌" in txt or "🔴" in txt
               else "ok" if "✅" in txt or "✓" in txt else "idea" if "💡" in txt or "ℹ" in txt
               else "pull")
        return f'<blockquote class="{cls}">{inner}</blockquote>'
    html = re.sub(r"<blockquote>(.*?)</blockquote>", bq, html, flags=re.S)

    # 2) فواصل الأقسام من «## N) عنوان»
    first = [True]
    def sec(m):
        n, title = m.group(1), m.group(2)
        cls = "sec first" if first[0] else "sec"
        first[0] = False
        return (f'<div class="{cls}"><div class="ghost">{n}</div>'
                f'<h2>{title}</h2><div class="tick"></div></div>')
    html = re.sub(r"<h2>(\d+)\)\s*(.*?)</h2>", sec, html)

    # 3) جدول عمودين قيمته الأولى رقم → شريط بطاقات
    def stats(m):
        tbl = m.group(0)
        rows = re.findall(r"<tr>\s*<td>(.*?)</td>\s*<td>(.*?)</td>\s*</tr>", tbl, re.S)
        if not (3 <= len(rows) <= 4):
            return tbl
        clean = [(re.sub(r"<[^>]+>", "", a).strip(), b) for a, b in rows]
        if not all(NUM.match(a) and len(a) <= 9 for a, _ in clean):
            return tbl
        cards = "".join(f'<div class="stat"><b>{a}</b><span>{b}</span></div>' for a, b in clean)
        return f'<div class="stats">{cards}</div>'
    html = re.sub(r"<table>.*?</table>", stats, html, flags=re.S)
    return html


def toc_of(html: str, lang: str = "ar") -> str:
    titles = re.findall(r'<div class="sec[^"]*"><div class="ghost">(\d+)</div><h2>(.*?)</h2>', html)
    if len(titles) < 4:
        return ""
    items = "".join(f"<li><b>{n.zfill(2)}</b>{re.sub(r'<[^>]+>', '', t)}</li>" for n, t in titles)
    label = "Contents" if lang == "en" else "المحتويات"
    return f'<section class="toc"><h2>{label}</h2><ol>{items}</ol></section>'


def build(md_path, out_pdf, cover):
    raw = Path(md_path).read_text(encoding="utf-8")
    raw = re.sub(r"\A(#\s+.*\n)+", "", raw)          # العنوان على الغلاف
    body = markdown.markdown(raw, extensions=["tables", "fenced_code", "attr_list", "sane_lists"])
    body = enrich(body)
    doc = SHELL.format(css=CSS, body=body, toc=toc_of(body, cover.get("lang", "ar")), **cover)
    p = Path(out_pdf).with_suffix(".html")
    p.write_text(doc, encoding="utf-8")
    return p


async def _pdf(pg, path, footer):
    await pg.pdf(path=path, format="A4", print_background=True,
                 display_header_footer=bool(footer), header_template="<div></div>",
                 footer_template=footer or "<div></div>",
                 margin={"top": "16mm", "bottom": "15mm", "left": "16mm", "right": "16mm"})


async def render(html_file, out_pdf):
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pg = await b.new_page()
        await pg.goto("file://" + str(Path(html_file).resolve()))
        await pg.wait_for_timeout(1000)
        foot = ("<div style=\"width:100%;font-size:7.4pt;color:#9AA3B2;"
                "font-family:'Noto Sans Arabic',sans-serif;padding:0 16mm;"
                "display:flex;justify-content:space-between;\">"
                "<span><span class='pageNumber'></span> / <span class='totalPages'></span></span>"
                "<span>BotYalla · youssefalsherief.tech</span></div>")
        # نسختان: بترقيم وبدونه — الغلاف يؤخذ من الثانية فلا يحمل رقم صفحة
        tmp_n, tmp_p = out_pdf + ".num", out_pdf + ".plain"
        await _pdf(pg, tmp_n, foot)
        await _pdf(pg, tmp_p, None)
        await b.close()
    from pypdf import PdfReader, PdfWriter
    num, plain = PdfReader(tmp_n), PdfReader(tmp_p)
    w = PdfWriter()
    w.add_page(plain.pages[0])                 # الغلاف بلا ترقيم
    for pg_ in num.pages[1:]:
        w.add_page(pg_)
    with open(out_pdf, "wb") as f:
        w.write(f)
    Path(tmp_n).unlink(); Path(tmp_p).unlink()


if __name__ == "__main__":
    JOBS = [
        ("LAUNCH_AUDIT_AR.md", "BotYalla_Launch_Audit_AR.pdf", dict(
            lang="ar", dir="rtl", title="BotYalla — مراجعة الإطلاق",
            ctitle="مراجعة الإطلاق<br>الشاملة",
            csub="الموقع المنشور · الكود كاملاً · مستندات المشروع<br>خطة الـ72 ساعة · خطة التسويق والاقتصاديات",
            cbadge="14 سبتمبر 2026 · كل رقم مُتحقَّق منه مباشرةً",
            cmeta="يوسف الشريف<br>botyalla.com<br>info@botyalla.com")),
        ("LAUNCH_AUDIT_EN.md", "BotYalla_Launch_Audit_EN.pdf", dict(
            lang="en", dir="ltr", title="BotYalla — Launch Audit",
            ctitle="Full Launch<br>Audit",
            csub="The deployed site · the complete codebase · project documents<br>The 72-hour plan · marketing plan and unit economics",
            cbadge="14 September 2026 · every figure verified directly",
            cmeta="Youssef Alsherief<br>botyalla.com<br>info@botyalla.com")),
    ]
    for md, pdf, cov in JOBS:
        asyncio.run(render(build(md, pdf, cov), pdf))
        print("✓", pdf)
