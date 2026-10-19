<#
.SYNOPSIS
    Edukom Enterprise LMS - Windows/PowerShell Database Backup Script
.DESCRIPTION
    Creates a timestamped snapshot of the SQLite database (dev) or invokes pg_dump (prod).
#>

param(
    [string]$BackupDir = ".\backups",
    [string]$DbPath = ".\db.sqlite3"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $BackupDir)) {
    New-Item -ItemType Directory -Path $BackupDir | Out-Null
}

$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupFile = Join-Path $BackupDir "edukom_sqlite_backup_$Timestamp.sqlite3"

Write-Host "[$((Get-Date).ToString('u'))] Initiating database backup..." -ForegroundColor Cyan

if (Test-Path $DbPath) {
    Copy-Item -Path $DbPath -Destination $BackupFile -Force
    $Hash = (Get-FileHash -Path $BackupFile -Algorithm SHA256).Hash
    "$Hash *$((Get-Item $BackupFile).Name)" | Out-File -FilePath "$BackupFile.sha256" -Encoding ascii
    Write-Host "[$((Get-Date).ToString('u'))] Backup created: $BackupFile" -ForegroundColor Green
    Write-Host "[$((Get-Date).ToString('u'))] SHA-256: $Hash" -ForegroundColor Yellow
} else {
    Write-Warning "Database file not found at $DbPath."
}
