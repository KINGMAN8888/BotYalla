@echo off
setlocal enabledelayedexpansion
title BotYalla - Ultimate Backup Sync

echo ========================================================
echo       BotYalla - Remote Backup ^& Local Sync Tool
echo ========================================================
echo.
echo This script will:
echo 1. Trigger a fresh backup on your remote server.
echo 2. Sync the backup automatically to Google Drive.
echo 3. Download a copy of the latest backup to this computer.
echo.

:: Configuration
set SERVER=root@botyalla.com
set REMOTE_DIR=/var/backups/botyalla
set LOCAL_DIR=.\local_backups

if not exist "%LOCAL_DIR%" (
    mkdir "%LOCAL_DIR%"
)

echo [*] Step 1/3: Triggering backup on the server and Google Drive...
:: We export RCLONE_REMOTE explicitly just in case the .env loading fails
ssh %SERVER% "export RCLONE_REMOTE='gdrive:botyalla_backups' && /opt/botyalla/deploy/backup.sh"

if %errorlevel% neq 0 (
    echo.
    echo [!] ERROR: The remote backup script failed.
    pause
    exit /b %errorlevel%
)

:: Step 2 & 3: Compressing latest files and downloading at once to minimize password prompts
echo [*] Step 2/3: Compressing the latest backup files on the server...
ssh %SERVER% "cd %REMOTE_DIR% && ls -t | grep -v '/$' | head -n 4 | tar -czf latest_backup.tar.gz -T -"

echo.
echo [*] Step 3/3: Downloading the backup archive to %LOCAL_DIR%...
scp -q %SERVER%:%REMOTE_DIR%/latest_backup.tar.gz "%LOCAL_DIR%/"

:: Extract the archive locally and delete the temp file
tar -xzf "%LOCAL_DIR%\latest_backup.tar.gz" -C "%LOCAL_DIR%"
del "%LOCAL_DIR%\latest_backup.tar.gz"
ssh %SERVER% "rm -f %REMOTE_DIR%/latest_backup.tar.gz"

echo.
echo ========================================================
echo [SUCCESS] Backup process completed successfully!
echo           Your local files are safely stored in:
echo           %cd%\%LOCAL_DIR%
echo ========================================================
echo.
pause
