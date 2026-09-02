@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title BotYalla - نشر على Hostinger

echo(
echo ==================================================
echo         BotYalla — نشر الإنتاج على Hostinger
echo ==================================================
echo(
echo  النشر يتم من GitHub مباشرة على السيرفر:
echo  لا رفع ملفات، ولا فرق بين جهازك والسيرفر.
echo(
echo  يتطلب: Hostinger VPS (Ubuntu) بصلاحية root
echo  وأن يكون آخر كودك مدفوعاً إلى GitHub.
echo ==================================================
echo(

set /p HOST=^> عنوان السيرفر (IP):
if "!HOST!"=="" ( echo لازم عنوان السيرفر. & pause & exit /b 1 )

set /p SSHUSER=^> اسم المستخدم [root]:
if "!SSHUSER!"=="" set "SSHUSER=root"

set /p DOMAIN=^> الدومين (اتركه فارغاً للنشر عبر IP):

set /p MODE=^> [1] نشر كامل  [2] تحديث فقط  :
if "!MODE!"=="2" ( set "ARGS=--update" ) else ( set "ARGS=!DOMAIN!" )

echo(
echo --------------------------------------------------
echo   السيرفر : !SSHUSER!@!HOST!
if "!MODE!"=="2" (
  echo   العملية : تحديث ^(سحب + بناء + إعادة تشغيل^)
) else (
  echo   العملية : نشر كامل
  if "!DOMAIN!"=="" ( echo   الدومين : بدون ^(عبر IP^) ) else ( echo   الدومين : !DOMAIN! )
)
echo --------------------------------------------------
echo(
set /p GO=اكتب y للمتابعة:
if /i not "!GO!"=="y" ( echo تم الإلغاء. & pause & exit /b 0 )

where ssh >nul 2>&1
if errorlevel 1 (
  echo(
  echo [خطأ] الأمر ssh غير متاح على هذا الجهاز.
  echo       ويندوز 10/11 فيه OpenSSH — فعّله من:
  echo       Settings ^> Apps ^> Optional features ^> OpenSSH Client
  pause & exit /b 1
)

echo(
echo ^>^> جاري الاتصال... ستُطلب كلمة مرور السيرفر.
echo(

REM سحب أحدث نسخة من السكربت ثم تشغيله — خطوة واحدة، آمنة للتكرار
ssh -o StrictHostKeyChecking=accept-new !SSHUSER!@!HOST! ^
 "set -e; command -v git >/dev/null || (apt-get update -y && apt-get install -y git); if [ -d /opt/botyalla/.git ]; then git -C /opt/botyalla fetch --all -q && git -C /opt/botyalla checkout -q origin/main -- deploy/hostinger_deploy.sh; else mkdir -p /opt/botyalla && git clone -q https://github.com/KINGMAN8888/BotYalla.git /opt/botyalla; fi; chmod +x /opt/botyalla/deploy/hostinger_deploy.sh; bash /opt/botyalla/deploy/hostinger_deploy.sh !ARGS!"

if errorlevel 1 (
  echo(
  echo [!] فشل النشر. للتشخيص اتصل يدوياً وشغّل:
  echo     ssh !SSHUSER!@!HOST!
  echo     journalctl -u botyalla -n 50 --no-pager
) else (
  echo(
  echo ==================================================
  echo   ✅ تم. افتح الموقع وتأكّد من الدخول.
  echo   السجلات:  ssh !SSHUSER!@!HOST! "journalctl -u botyalla -f"
  echo ==================================================
)
echo(
pause
endlocal
