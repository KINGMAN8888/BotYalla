@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title BotYalla - Hostinger VPS Auto Deploy

echo(
echo ==================================================
echo        BotYalla - رفع تلقائي على Hostinger VPS
echo ==================================================
echo(
echo  يعمل مع Hostinger VPS (Ubuntu) وصلاحية root.
echo  لا يعمل مع الاستضافة المشتركة (Shared Hosting).
echo  يرفع ملفاتك مباشرة (مش محتاج GitHub عام).
echo ==================================================
echo(

REM ================= المدخلات =================
set /p HOST=^> عنوان السيرفر (IP):
if "!HOST!"=="" ( echo لازم عنوان السيرفر. & pause & exit /b )
set /p SSHUSER=^> اسم المستخدم (غالباً root):
if "!SSHUSER!"=="" set "SSHUSER=root"

for /f "usebackq delims=" %%p in (`powershell -NoProfile -Command "$p=Read-Host '^> كلمة مرور السيرفر' -AsSecureString; [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($p))"`) do set "PASS=%%p"

set /p DOMAIN=^> الدومين (مثال: botyalla.com — أو Enter لتجاهله):

echo(
echo --------------------------------------------------
echo  السيرفر : !SSHUSER!@!HOST!
echo  الدومين : !DOMAIN!
echo --------------------------------------------------
set /p GO=^> ابدأ الرفع؟ (y/n):
if /i not "!GO!"=="y" ( echo تم الإلغاء. & pause & exit /b )

REM جذر المشروع = المجلد الأب لمجلد deploy
set "ROOT=%~dp0.."
pushd "!ROOT!"
set "ROOT=!CD!"
popd

REM ================= تجهيز أدوات PuTTY =================
set "PLINK=%~dp0plink.exe"
set "PSCP=%~dp0pscp.exe"
if not exist "!PLINK!" (
  echo [1/4] تحميل plink.exe ...
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -Uri 'https://the.earth.li/~sgtatham/putty/latest/w64/plink.exe' -OutFile '!PLINK!'}catch{exit 1}"
)
if not exist "!PSCP!" (
  echo [1/4] تحميل pscp.exe ...
  powershell -NoProfile -Command "try{Invoke-WebRequest -UseBasicParsing -Uri 'https://the.earth.li/~sgtatham/putty/latest/w64/pscp.exe' -OutFile '!PSCP!'}catch{exit 1}"
)
if not exist "!PLINK!" ( echo تعذّر تحميل plink.exe — نزّله يدوياً من putty.org وضعه بجوار هذا الملف. & pause & exit /b )
if not exist "!PSCP!" ( echo تعذّر تحميل pscp.exe — نزّله يدوياً من putty.org وضعه بجوار هذا الملف. & pause & exit /b )

REM ================= ضغط المشروع (بدون الملفات غير الضرورية) =================
echo [2/4] تجهيز حزمة الرفع...
set "PKG=%TEMP%\botyalla_upload.tar.gz"
if exist "!PKG!" del "!PKG!"
tar -czf "!PKG!" -C "!ROOT!" --exclude=.git --exclude=__pycache__ --exclude=venv --exclude=.venv --exclude=botyalla.db --exclude=botyalla.db-journal --exclude=plink.exe --exclude=pscp.exe --exclude=uploads/pay_* .
if not exist "!PKG!" ( echo فشل ضغط المشروع (تأكد من وجود tar في ويندوز 10+). & pause & exit /b )

REM ================= الرفع عبر pscp =================
echo [3/4] رفع الملفات إلى السيرفر...
echo y | "!PSCP!" -pw "!PASS!" "!PKG!" !SSHUSER!@!HOST!:/root/botyalla_upload.tar.gz
if errorlevel 1 ( echo فشل الرفع — تأكد من العنوان/المستخدم/كلمة المرور. & pause & exit /b )

REM ================= التثبيت على السيرفر =================
echo [4/4] فك الضغط والتثبيت على السيرفر (2-4 دقائق)...
echo --------------------------------------------------
echo y | "!PLINK!" -ssh -pw "!PASS!" !SSHUSER!@!HOST! "set -e; mkdir -p /opt/botyalla; tar -xzf /root/botyalla_upload.tar.gz -C /opt/botyalla; chmod +x /opt/botyalla/deploy/server_setup.sh; bash /opt/botyalla/deploy/server_setup.sh '!DOMAIN!'; rm -f /root/botyalla_upload.tar.gz"

del "!PKG!" 2>nul
echo(
echo ==================================================
echo   تم! افتح موقعك الآن:
if not "!DOMAIN!"=="" ( echo     http://!DOMAIN! ) else ( echo     http://!HOST! )
echo(
echo   تسجيل الدخول:  admin  /  admin1234
echo   (غيّر كلمة المرور فوراً من صفحة «حسابي»)
echo(
echo   لتفعيل HTTPS (لو عندك دومين موجّه للسيرفر):
echo     ادخل السيرفر وشغّل:  sudo certbot --nginx -d !DOMAIN! -d www.!DOMAIN!
echo(
echo   للتحديث لاحقاً: عدّل ملفاتك وشغّل هذا الملف مرة أخرى.
echo ==================================================
set "PASS="
pause
