# سكربت PowerShell لرفع المشروع على GitHub (Windows)
param(
    [string]$RepoUrl = "https://github.com/KINGMAN8888/BotYalla.git"
)

$ErrorActionPreference = "Stop"

Set-Location -Path "$PSScriptRoot\.."

Write-Host "📦 فحص حالة Git..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    git init -b main
}

git add .
try {
    git commit -m "BotYalla — initial release"
} catch {
    Write-Host "لا توجد تعديلات جديدة للـ commit" -ForegroundColor Yellow
}

git remote remove origin 2>$null
git remote add origin $RepoUrl

Write-Host "🚀 جاري الرفع إلى $RepoUrl ..." -ForegroundColor Cyan
git push -u origin main

Write-Host "✅ تم الرفع بنجاح على $RepoUrl" -ForegroundColor Green
