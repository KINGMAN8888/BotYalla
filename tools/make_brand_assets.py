"""يولّد صور الهوية للموقع العام في static/brand/ من شعار SVG نفسه:

    og-ar.png · og-en.png          صورة المشاركة (1200×630) لفيسبوك/واتساب/تويتر/لينكدإن
    icon-512.png · icon-192.png     أيقونات التطبيق (manifest)
    apple-touch-icon.png (180)      أيقونة الشاشة الرئيسية على iOS
    favicon-32.png                  أيقونة المتصفح

الرسم بمتصفح Chromium بلا واجهة (Edge على ويندوز، أو Chrome/Chromium) — نفس
محرك العرض الذي سيراه الزائر، فالخط العربي والتدرّجات مطابقة. لا مكتبات Python.

    python tools/make_brand_assets.py            # يبحث عن المتصفح تلقائياً
    BROWSER="C:/path/msedge.exe" python tools/make_brand_assets.py
"""
import os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "static" / "brand"

CANDIDATES = [
    os.environ.get("BROWSER", ""),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    shutil.which("google-chrome") or "", shutil.which("chromium") or "",
    shutil.which("chromium-browser") or "", shutil.which("microsoft-edge") or "",
]

FONTS = ('<link href="https://fonts.googleapis.com/css2?family=Noto+Kufi+Arabic:wght@800;900'
         '&family=Inter:wght@700;800&family=Instrument+Serif:ital@1&display=block" rel="stylesheet">')

COPY = {
    "ar": {"dir": "rtl", "a": "بوت يرد ويبيع ويحجز", "b": "على تليجرام وواتساب",
           "c": "بدون برمجة · ادفع بفودافون كاش وانستاباي · ابدأ مجاناً",
           "q": "عايز أحجز ترابيزة لـ4 الساعة 9", "r": "تمام ✅ اتحجزتلك الساعة 9 — نستناك!",
           "font": "'Noto Kufi Arabic','Segoe UI',Tahoma,sans-serif"},
    "en": {"dir": "ltr", "a": "A bot that answers,", "b": "sells and books",
           "c": "Telegram & WhatsApp · No code · Local payment · Start free",
           "q": "Table for 4 at 9pm, please", "r": "Done ✅ Booked for 9pm — see you then!",
           "font": "Inter,'Segoe UI',Arial,sans-serif"},
}


def og_html(lang, logo):
    c = COPY[lang]
    accent = ("font-family:'Instrument Serif',Georgia,serif;font-style:italic;font-weight:400;"
              if lang == "en" else "")
    return f"""<!doctype html><html lang="{lang}" dir="{c['dir']}"><head><meta charset="utf-8">{FONTS}
<style>
*{{margin:0;box-sizing:border-box}}
html,body{{width:1200px;height:630px;overflow:hidden;background:#05070D}}
body{{position:relative;font-family:{c['font']};color:#F2F5FC}}
.bg{{position:absolute;inset:0;background:
  radial-gradient(60% 80% at 82% 10%,rgba(124,108,246,.55),transparent 60%),
  radial-gradient(45% 70% at 12% 100%,rgba(34,211,238,.35),transparent 62%),
  radial-gradient(35% 50% at 55% 55%,rgba(45,212,167,.14),transparent 70%)}}
.grid{{position:absolute;inset:0;background-image:linear-gradient(to right,rgba(255,255,255,.05) 1px,transparent 1px),
  linear-gradient(to bottom,rgba(255,255,255,.05) 1px,transparent 1px);background-size:56px 56px;
  -webkit-mask-image:radial-gradient(ellipse 80% 70% at 50% 30%,#000 20%,transparent 80%)}}
.wrap{{position:absolute;inset:64px 72px;display:flex;flex-direction:column}}
.logo{{height:58px;direction:ltr}} .logo svg{{height:58px;width:auto;direction:ltr}}
h1{{margin-top:auto;font-size:{76 if lang=='ar' else 80}px;line-height:{1.3 if lang=='ar' else 1.02};
    font-weight:900;letter-spacing:{0 if lang=='ar' else '-0.045em'};max-width:720px}}
h1 span{{display:block;{accent}background:linear-gradient(100deg,#7C6CF6,#22D3EE 50%,#2DD4A7);
  -webkit-background-clip:text;color:transparent}}
p{{margin-top:26px;font-size:26px;color:#AEB9D4;font-family:{'Segoe UI,Tahoma' if lang=='ar' else 'Inter'},sans-serif;font-weight:600}}
.chat{{position:absolute;{'left' if lang=='ar' else 'right'}:72px;top:150px;width:360px;padding:22px;border-radius:30px;
  background:linear-gradient(165deg,rgba(255,255,255,.08),rgba(255,255,255,.03));
  box-shadow:inset 0 0 0 1px rgba(255,255,255,.12),0 40px 80px -30px rgba(0,0,0,.9);
  font-family:'Segoe UI',Tahoma,sans-serif;font-size:19px;line-height:1.5}}
.m{{padding:12px 16px;border-radius:20px;margin-bottom:12px;max-width:88%}}
.q{{margin-{'right' if lang=='ar' else 'left'}:auto;background:linear-gradient(115deg,#7C6CF6,#22D3EE);color:#08111C;font-weight:700}}
.r{{background:rgba(255,255,255,.09)}}
</style></head><body><div class="bg"></div><div class="grid"></div>
<div class="chat"><div class="m q">{c['q']}</div><div class="m r">{c['r']}</div></div>
<div class="wrap"><div class="logo" dir="ltr">{logo}</div><h1>{c['a']}<span>{c['b']}</span></h1><p>{c['c']}</p></div>
</body></html>"""


def icon_html(size, mark):
    pad = round(size * 0.16)
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
*{{margin:0}} html,body{{width:{size}px;height:{size}px;overflow:hidden;background:#05070D}}
body{{display:grid;place-items:center;background:radial-gradient(70% 70% at 50% 25%,#1a1740,#05070D)}}
svg{{width:{size - 2 * pad}px;height:{size - 2 * pad}px}}
</style></head><body>{mark}</body></html>"""


def shoot(browser, html, out, w, h):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        src = Path(f.name)
    try:
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", f"--window-size={w},{h}",
                        "--virtual-time-budget=6000", f"--screenshot={out}", src.as_uri()],
                       check=True, capture_output=True, timeout=90)
    finally:
        src.unlink(missing_ok=True)
    if not out.exists():
        raise SystemExit(f"لم يُنتج المتصفح {out.name}")
    print(f"  {out.relative_to(ROOT)}  ({out.stat().st_size // 1024} KB)")


def main():
    # طرفية ويندوز cp1252 افتراضياً: أي حرف عربي أو سهم في print يُسقط السكربت
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    browser = next((b for b in CANDIDATES if b and Path(b).exists()), None)
    if not browser:
        sys.exit("لم أجد Edge/Chrome/Chromium — اضبط BROWSER على مسار المتصفح.")
    OUT.mkdir(parents=True, exist_ok=True)
    logo = (ROOT / "static" / "logo.svg").read_text(encoding="utf-8")
    mark = (ROOT / "static" / "mark.svg").read_text(encoding="utf-8")
    print("BotYalla brand assets →", OUT)
    for lang in ("ar", "en"):
        shoot(browser, og_html(lang, logo), OUT / f"og-{lang}.png", 1200, 630)
    for name, size in (("icon-512", 512), ("icon-192", 192), ("apple-touch-icon", 180), ("favicon-32", 32)):
        shoot(browser, icon_html(size, mark), OUT / f"{name}.png", size, size)


if __name__ == "__main__":
    main()
