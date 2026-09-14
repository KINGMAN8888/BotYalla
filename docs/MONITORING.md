# 📡 المراقبة — BotYalla

المراقبة الخارجية تعرف أن الموقع وقع **قبل** أن يخبرك عميل. لا بد أن تكون خارج السيرفر:
مراقب داخل السيرفر يقع معه.

## ما نراقبه ولماذا
| المراقب | الرابط | ينبّه حين |
|---|---|---|
| الصحة | `https://botyalla.com/healthz` | قاعدة البيانات لا تستجيب (يرجّع 503) · التطبيق متوقف · nginx أو الشهادة معطّلة |
| الرئيسية | `https://botyalla.com/` | ما يراه الزائر فعلاً لا يفتح |

`/healthz` ينفّذ استعلاماً حقيقياً على القاعدة — لا يكفي أن العملية حيّة.

## الإعداد (5 دقائق)
1. سجّل في [UptimeRobot](https://uptimerobot.com) (الخطة المجانية: 50 مراقباً، فحص كل 5 دقائق).
2. **جهات التنبيه:** My Settings ← Alert Contacts ← أضف إيميلك. ولتنبيه فوري على الموبايل:
   Integrations ← **Telegram** واتبع الربط مع بوت UptimeRobot.
3. **المفتاح:** Integrations & API ← **Main API key** ← انسخه (لا تكتبه في أي ملف).
4. **أنشئ المراقبين بأمر واحد** — من جهازك أو من السيرفر:
   ```bash
   UPTIMEROBOT_API_KEY=ضع_المفتاح_هنا python3 tools/uptimerobot_setup.py https://botyalla.com
   ```
   السكربت يتخطّى أي مراقب موجود لنفس الرابط، فإعادة تشغيله آمنة.

**بديل يدوي من الواجهة:** New Monitor ← النوع **HTTP(s)** ← الاسم `BotYalla · health (database)` ←
الرابط `https://botyalla.com/healthz` ← الفاصل 5 دقائق ← اختر جهات التنبيه ← Create. ثم كرّر للرئيسية.

## حين يصلك تنبيه
على السيرفر:
```bash
sudo systemctl status botyalla --no-pager          # هل الخدمة تعمل؟
sudo journalctl -u botyalla -n 80 --no-pager       # آخر سطور السجل — سبب التوقف غالباً هنا
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8000/healthz   # التطبيق مباشرة بلا nginx
sudo systemctl restart botyalla                    # إعادة التشغيل
sudo nginx -t && sudo systemctl reload nginx       # لو التطبيق يعمل والموقع لا يفتح
```
- `healthz` مباشرة = 200 والموقع لا يفتح ← المشكلة في nginx أو الشهادة.
- `healthz` = 503 ← القاعدة (مساحة القرص: `df -h`).
- لا رد إطلاقاً ← الخدمة متوقفة؛ السبب في `journalctl`.

## فحص إعدادات السيرفر (PUBLIC_URL وتحويل www)
```bash
sudo grep -E '^PUBLIC_URL=' /opt/botyalla/.env || echo "PUBLIC_URL غير مضبوط"
sudo tr '\0' '\n' < /proc/$(systemctl show -p MainPID --value botyalla)/environ | grep '^PUBLIC_URL='
curl -sI https://www.botyalla.com/pricing | grep -iE '^(HTTP|location)'
```
المتوقع: السطر الأول والثاني `PUBLIC_URL=https://botyalla.com` (الثاني = ما تراه الخدمة الجارية فعلاً)،
والثالث `301` مع `location: https://botyalla.com/pricing`.
