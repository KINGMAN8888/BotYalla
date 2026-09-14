"""يولّد static/brand/email-mark.png — شعار BotYalla للإيميلات.

برامج البريد (Gmail/Outlook) لا تعرض SVG، فالشعار يُرسم هنا بـ Pillow من نفس
هندسة `static/mark.svg` حرفياً (نفس الإحداثيات والألوان)، بتنعيم ×16 ثم تصغير،
على خلفية شفافة. يُرفق بكل إيميل كصورة مضمّنة (cid:by-mark) — لا رابط خارجي
يحجبه برنامج البريد ولا اعتماد على PUBLIC_URL.

    python tools/make_email_mark.py
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "brand", "email-mark.png")

VW, VH = 60, 64            # viewBox الشعار في mark.svg
S = 16                     # تنعيم: نرسم ×16 ثم نصغّر
OUT_W = 120                # ×2 لشاشات Retina (يُعرض 44px تقريباً)


def hexrgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def gradient(w, h, c1, c2):
    """تدرّج قطري من (0,0) إلى (56,56) بوحدات الـ viewBox — كـ linearGradient#bg."""
    g = Image.new("RGBA", (w, h))
    px = g.load()
    a, b = hexrgb(c1), hexrgb(c2)
    span = 56 * S * 2
    for y in range(h):
        for x in range(w):
            t = min(1.0, max(0.0, (x + y) / span))
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(4))
    return g


def main():
    W, H = VW * S, VH * S
    p = lambda v: v * S
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    # جسم الفقاعة + الذيل بالتدرّج
    mask = Image.new("L", (W, H), 0)
    m = ImageDraw.Draw(mask)
    m.rounded_rectangle([p(4), p(6), p(56), p(52)], radius=p(15), fill=255)
    m.polygon([(p(22), p(52)), (p(30), p(52)), (p(24), p(62))], fill=255)
    img.paste(gradient(W, H, "#7C6CF6", "#22D3EE"), (0, 0), mask)

    d = ImageDraw.Draw(img)
    ink, bolt, white = hexrgb("#0B1020"), hexrgb("#FFD23F"), hexrgb("#FFFFFF")
    circ = lambda cx, cy, r, **k: d.ellipse([p(cx - r), p(cy - r), p(cx + r), p(cy + r)], **k)

    # العينان ولمعتهما
    for cx in (22, 38):
        circ(cx, 27, 4.4, fill=ink)
        circ(cx + 1.4, 25.6, 1.4, fill=white)
    # البرق (يلا = سرعة)
    bolt_pts = [(31.5, 33), (26, 41.5), (30.2, 41.5), (28.5, 47), (35, 38.5), (30.8, 38.5)]
    d.polygon([(p(x), p(y)) for x, y in bolt_pts], fill=bolt, outline=ink, width=round(0.6 * S))
    # الهوائي
    d.rounded_rectangle([p(28.6), p(9.5), p(31.4), p(15.5)], radius=p(1.4), fill=ink)
    circ(30, 8, 2.6, fill=bolt, outline=ink, width=round(0.6 * S))

    out_h = round(OUT_W * VH / VW)
    img.resize((OUT_W, out_h), Image.LANCZOS).save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT_W}x{out_h}, {os.path.getsize(OUT)} bytes)")


if __name__ == "__main__":
    main()
