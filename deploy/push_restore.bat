@echo off
setlocal enabledelayedexpansion
title BotYalla - Restore Tool

echo ========================================================
echo       BotYalla - Local to Remote Restore Tool
echo ========================================================
echo.
echo This script will safely upload a local backup from your
echo machine and restore it on the remote server.
echo.

set LOCAL_DIR=%~dp0local_backups
if not exist "%LOCAL_DIR%" set LOCAL_DIR=.\local_backups

echo Available Database Backups:
echo --------------------------------------------------------
dir /b "%LOCAL_DIR%\db_*.sqlite.gz" 2>nul
if %errorlevel% neq 0 (
    echo [!] No backups found in %LOCAL_DIR%
    echo Please run pull_backup.bat first to download a backup.
    pause
    exit /b 1
)
echo --------------------------------------------------------
echo.
set /p DB_FILE="Type the exact name of the db file to restore: "

if not exist "%LOCAL_DIR%\%DB_FILE%" (
    echo.
    echo [!] ERROR: File "%LOCAL_DIR%\%DB_FILE%" not found!
    pause
    exit /b 1
)

:: Auto-detect matching uploads file
set UPLOADS_FILE=%DB_FILE:db_=uploads_%
set UPLOADS_FILE=%UPLOADS_FILE:.sqlite.gz=.tar.gz%

set SERVER=root@botyalla.com

echo.
echo [*] Step 1/3: Uploading Database Backup to server...
scp -q "%LOCAL_DIR%\%DB_FILE%" %SERVER%:/tmp/%DB_FILE%

set RESTORE_CMD=/opt/botyalla/deploy/restore.sh /tmp/%DB_FILE%

if exist "%LOCAL_DIR%\%UPLOADS_FILE%" (
    echo [*] Step 2/3: Matching Uploads Backup found! Uploading...
    scp -q "%LOCAL_DIR%\%UPLOADS_FILE%" %SERVER%:/tmp/%UPLOADS_FILE%
    set RESTORE_CMD=/opt/botyalla/deploy/restore.sh /tmp/%DB_FILE% /tmp/%UPLOADS_FILE%
) else (
    echo [*] Step 2/3: No matching Uploads backup found. Proceeding with DB only.
)

echo.
echo [*] Step 3/3: Executing restore on the remote server...
echo --------------------------------------------------------
ssh %SERVER% "sudo APP_DIR=/opt/botyalla %RESTORE_CMD%"
echo --------------------------------------------------------

echo.
echo [*] Cleaning up temporary files on server...
ssh %SERVER% "rm -f /tmp/%DB_FILE% /tmp/%UPLOADS_FILE%"

echo.
echo ========================================================
echo [SUCCESS] Restore process completed!
echo           Please verify your bots and data.
echo ========================================================
echo.
pause
