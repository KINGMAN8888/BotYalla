# تشغيل BotYalla في الإنتاج

دليل عملي للنشر والتشغيل والصيانة. السيرفر المستهدف: **Hostinger VPS (Ubuntu)** بصلاحية root.

---

## 1) النشر

### من ويندوز (الأسهل)

```
deploy\deploy_hostinger.bat
```

يسألك عن عنوان السيرفر والدومين، ثم يتصل ويشغّل كل شيء.

### من السيرفر مباشرة

```bash
ssh root@<SERVER_IP>

apt-get update -y && apt-get install -y git
git clone https://github.com/KINGMAN8888/BotYalla.git /opt/botyalla
bash /opt/botyalla/deploy/hostinger_deploy.sh                  # عبر IP
bash /opt/botyalla/deploy/hostinger_deploy.sh botyalla.com     # مع دومين
```

السكربت **آمن للتكرار**: تشغيله مرتين لا يكسر شيئاً ولا يعيد توليد الأسرار.

### التحديث بعد أي تعديل

```bash
bash /opt/botyalla/deploy/hostinger_deploy.sh --update
```

يسحب من GitHub، يبني الواجهة، ويعيد تشغيل الخدمة. **ادفع كودك إلى GitHub أولاً.**

---

## 2) أول تشغيل — خطوات إلزامية

1. **احفظ كلمة مرور الأدمن.** تُولَّد عشوائية وتظهر **مرة واحدة** في نهاية النشر. لا توجد كلمة افتراضية.
2. **غيّرها فوراً** من صفحة «حسابي».
3. **اضبط بيانات الدفع** من «إعدادات المنصة»: فودافون كاش · انستاباي · الحساب البنكي.
4. **فعّل بوت المنصة**: ضع توكن البوت و`admin_chat_id` — بدونهما لن تصلك تنبيهات الدفع على تليجرام (تبقى ظاهرة في لوحة المدفوعات).
5. **اضبط الأسعار** من «الأسعار والخصومات».

---

## 3) الدومين و HTTPS

هذا **ليس تحسيناً اختيارياً** — بدونه:

- الموقع يعمل على `http://` فقط، فتمرّ كلمات المرور وصور الإيصالات بلا تشفير.
- `COOKIE_SECURE` يبقى `0` (يضبطه السكربت تلقائياً)، لأن كوكي `Secure` لا يُرسَل على http فيفشل الدخول صامتاً.

الخطوات:

```bash
# 1) وجّه الدومين (سجل A) إلى عنوان السيرفر
# 2) أعد النشر بالدومين
bash /opt/botyalla/deploy/hostinger_deploy.sh example.com
# 3) شهادة مجانية
certbot --nginx -d example.com -d www.example.com
# 4) فعّل HSTS: أزل التعليق عن سطر Strict-Transport-Security
nano /etc/nginx/sites-available/botyalla && nginx -t && systemctl reload nginx
```

السكربت يرفع `COOKIE_SECURE` إلى `1` تلقائياً عند تمرير دومين.

---

## 4) التشغيل اليومي

| المهمة | الأمر |
|---|---|
| الحالة | `systemctl status botyalla` |
| السجلات الحيّة | `journalctl -u botyalla -f` |
| آخر الأخطاء | `journalctl -u botyalla -p err -n 50` |
| إعادة التشغيل | `systemctl restart botyalla` |
| فحص صحّي | `curl -s localhost:8000/healthz` |
| نسخة احتياطية فورية | `/opt/botyalla/deploy/backup.sh` |

`/healthz` يتحقّق أن **قاعدة البيانات تستجيب**، لا أن العملية حيّة فقط — استخدمه في أي مراقبة خارجية (UptimeRobot وغيره).

---

## 5) النسخ الاحتياطي

يعمل تلقائياً كل يوم 3 صباحاً عبر cron ويحتفظ بـ 14 يوماً في `/var/backups/botyalla`:
قاعدة البيانات (بـ `sqlite3 .backup` لا `cp`، فالنسخة متّسقة أثناء الكتابة) · مجلد الإيصالات · ملف `.env`.

**النسخة على نفس القرص.** عطل قرص واحد يأخذها معه. انسخها خارج السيرفر دورياً:

```bash
# من جهازك
scp -r root@<SERVER_IP>:/var/backups/botyalla ./backups/
```

الاستعادة موثّقة داخل `deploy/backup.sh`.

---

## 6) حدود معمارية يجب معرفتها

**عامل واحد فقط في gunicorn.** بوتات تليجرام تعمل داخل العملية بحالة في الذاكرة، فتشغيل أكثر من worker يعني تشغيل كل بوت مرتين وتضارباً على `getUpdates`. مضبوط في `gunicorn_conf.py` — **لا تزده.**

هذا يعني أن التوسّع الرأسي (رام/معالج أكبر) هو المسار المتاح. التوسّع الأفقي يتطلّب فصل مدير البوتات في خدمة مستقلة.

**SQLite في وضع WAL** مع `busy_timeout=15s`. كافٍ لآلاف المستخدمين. مؤشرات الانتقال إلى PostgreSQL: ظهور `database is locked` في السجلات، أو تجاوز حجم القاعدة بضعة جيجابايت.

**Polling لا Webhooks.** أبسط للإطلاق، لكنه يستهلك اتصالاً دائماً لكل بوت.

---

## 7) بعد أي نشر — تحقّق

```bash
curl -s https://<domain>/healthz          # {"ok": true}
systemctl is-active botyalla nginx        # active active
```

ثم في المتصفح: افتح صفحة الهبوط · سجّل الدخول · افتح لوحة التحكم · جرّب رفع إيصال دفع تجريبي واعتماده.

---

## 8) الأمان — ما هو مُفعّل

- جلسات: `HttpOnly` + `SameSite=Lax` + `Secure` عند HTTPS
- CSRF على كل POST · لا مسار يغيّر الحالة عبر GET
- الأدوار تُقرأ من القاعدة كل طلب — الحظر والتخفيض يسريان فوراً
- المبالغ تُحسب في الخادم دائماً · لا تفعيل اشتراك بلا موافقة أدمن
- صور الإيصالات لا تُقدَّم من `static/` — عبر مسار محمي بالأدوار فقط
- `.env` بصلاحيات 600 · systemd مُصلَّب (`ProtectSystem=strict`, `NoNewPrivileges`)
- `ufw` (SSH + HTTP/HTTPS فقط) و`fail2ban`
- حدّ معدّل على `/login` في nginx + محدِّد داخل التطبيق

**يبقى عليك:** مفتاح SSH بدل كلمة المرور، وتعطيل `PermitRootLogin` بكلمة مرور:

```bash
ssh-copy-id root@<SERVER_IP>
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl restart ssh
```
