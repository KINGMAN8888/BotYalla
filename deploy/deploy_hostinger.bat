@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
title BotYalla - Deploy to Hostinger

echo(
echo ==================================================
echo         BotYalla - Production Deploy to Hostinger
echo ==================================================
echo(
echo  Deployment is done directly from GitHub to the server:
echo  No file uploading, ensuring consistency between environments.
echo(
echo  Requires: Hostinger VPS (Ubuntu) with root access
echo  And that your latest code is pushed to GitHub.
echo ==================================================
echo(

set /p HOST=^> Server Address (IP): 
if "!HOST!"=="" ( echo Server address is required. & pause & exit /b 1 )

set /p SSHUSER=^> Username [root]: 
if "!SSHUSER!"=="" set "SSHUSER=root"

set /p DOMAIN=^> Domain (leave empty to deploy via IP): 

set /p MODE=^> [1] Full Deploy  [2] Update Only  : 
if "!MODE!"=="2" ( set "ARGS=--update" ) else ( set "ARGS=!DOMAIN!" )

echo(
echo --------------------------------------------------
echo   Server : !SSHUSER!@!HOST!
if "!MODE!"=="2" (
  echo   Action : Update Only ^(pull + build + restart^)
) else (
  echo   Action : Full Deploy
  if "!DOMAIN!"=="" ( echo   Domain : None ^(via IP^) ) else ( echo   Domain : !DOMAIN! )
)
echo --------------------------------------------------
echo(
set /p GO=Type y to continue: 
if /i not "!GO!"=="y" ( echo Cancelled. & pause & exit /b 0 )

where ssh >nul 2>&1
if errorlevel 1 (
  echo(
  echo [Error] The 'ssh' command is not available on this machine.
  echo         Windows 10/11 includes OpenSSH - enable it from:
  echo         Settings ^> Apps ^> Optional features ^> OpenSSH Client
  pause & exit /b 1
)

echo(
echo ^>^> Connecting... Server password will be requested.
echo(

REM Pull the latest version of the script then run it - single step, safe to repeat
ssh -o StrictHostKeyChecking=accept-new !SSHUSER!@!HOST! ^
 "set -e; command -v git >/dev/null || (apt-get update -y && apt-get install -y git); if [ -d /opt/botyalla/.git ]; then git -C /opt/botyalla fetch --all -q && git -C /opt/botyalla checkout -q origin/main -- deploy/hostinger_deploy.sh; else mkdir -p /opt/botyalla && git clone -q https://github.com/KINGMAN8888/BotYalla.git /opt/botyalla; fi; chmod +x /opt/botyalla/deploy/hostinger_deploy.sh; bash /opt/botyalla/deploy/hostinger_deploy.sh !ARGS!"

if errorlevel 1 (
  echo(
  echo [!] Deployment failed. For diagnostics, connect manually and run:
  echo     ssh !SSHUSER!@!HOST!
  echo     journalctl -u botyalla -n 50 --no-pager
) else (
  echo(
  echo ==================================================
  echo   ✅ Done. Open the site and make sure you can log in.
  echo   Logs:  ssh !SSHUSER!@!HOST! "journalctl -u botyalla -f"
  echo ==================================================
)
echo(
pause
endlocal
