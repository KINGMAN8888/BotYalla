# 🚀 دليل النشر — BotYalla

دليل خطوة بخطوة لرفع المنصة على GitHub وسيرفر حقيقي (VPS) بدومين وHTTPS.

## المتطلبات
- سيرفر **Ubuntu 22.04** (VPS) — مثلاً من Hetzner / DigitalOcean / Contabo (يبدأ من ~5$/شهر).
- **دومين** (اشتريت `botyalla.com`) موجّه لـ IP السيرفر (سجل A).
- حساب **GitHub**.

---

## الجزء 1: رفع الكود على GitHub

```bash
# داخل مجلد المشروع على جهازك
bash deploy/push_to_github.sh https://github.com/USERNAME/botyalla.git
```
> أنشئ ريبو فاضي على GitHub أولاً (بدون README). خلّي الريبو **Private** لأن الكود يحوي منطق الدفع.

⚠️ ملف `.env` **لا يُرفع** (محمي بـ `.gitignore`) — الأسرار تبقى على السيرفر فقط.

---

## الجزء 2: النشر التلقائي على السيرفر

اتصل بالسيرفر عبر SSH ثم:
```bash
# نزّل السكربت وشغّله — يعمل كل شيء تلقائياً
wget https://raw.githubusercontent.com/USERNAME/botyalla/main/deploy/deploy.sh
sudo bash deploy.sh https://github.com/USERNAME/botyalla.git botyalla.com
```

السكربت يقوم بـ:
1. تثبيت Python + Nginx + Git + (Tesseract للـ OCR اختياري).
2. إنشاء مستخدم خدمة آمن.
3. جلب الكود من GitHub.
4. بيئة افتراضية + الاعتماديات.
5. توليد `FLASK_SECRET` عشوائي قوي تلقائياً.
6. خدمة systemd (تشغيل دائم + إعادة تشغيل تلقائي).
7. إعداد Nginx.
8. تجهيز HTTPS.

### تفعيل HTTPS (مجاني)
```bash
sudo certbot --nginx -d botyalla.com -d www.botyalla.com
```

---

## الجزء 3: الإعداد الأول (بعد الرفع)
1. افتح `https://botyalla.com` → **سجّل أول حساب** (هذا الحساب = مالك المنصة/الأدمن).
2. من القائمة → **إعدادات المنصة**: بيانات الدفع مضبوطة مسبقاً؛ راجعها.
3. أنشئ **بوت تنبيهات** من [@BotFather](https://t.me/BotFather)، وضع توكنه + معرّفك (من [@userinfobot](https://t.me/userinfobot)) في «بوت تنبيهات الدفع».
4. جرّب: اشترك بباقة من حساب تجريبي، ارفع صورة → يجب أن يصلك تنبيه على تليجرام بزرّي موافقة/رفض.

---

## التحديثات المستقبلية
```bash
sudo bash /opt/botyalla/deploy/deploy.sh https://github.com/USERNAME/botyalla.git botyalla.com
```
(يسحب أحدث كود ويعيد التشغيل — بياناتك وقاعدة البيانات تبقى سليمة.)

## أوامر مفيدة
```bash
sudo systemctl status botyalla     # حالة الخدمة
sudo systemctl restart botyalla    # إعادة تشغيل
sudo journalctl -u botyalla -f     # مشاهدة اللوج الحي
```

## بديل: Docker
```bash
docker build -t botyalla .
docker run -d -p 8000:8000 --env-file .env -v $(pwd)/uploads:/app/uploads --name botyalla botyalla
```

## ملاحظة عن التوسّع
بوتات تليجرام تعمل داخل عملية Gunicorn الواحدة (حالة في الذاكرة)، لذلك `workers=1`.
عند النمو الكبير، افصل «مدير البوتات» في خدمة مستقلة — موضّح في `ARCHITECTURE.md`.
