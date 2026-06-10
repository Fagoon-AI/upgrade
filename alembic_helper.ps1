#!/usr/bin/env pwsh
<#
.SYNOPSIS
Helper script to run Alembic commands with safe environment defaults.
Avoids Settings() crashes due to missing required env vars.

.EXAMPLE
.\alembic_helper.ps1 revision --autogenerate -m "add new table"
.\alembic_helper.ps1 upgrade head
.\alembic_helper.ps1 downgrade -1
.\alembic_helper.ps1 current
#>

param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$AlembicArgs
)

# Load .env if it exists
$envFile = ".env"
if (Test-Path $envFile) {
    Write-Host "Loading .env file..." -ForegroundColor Cyan
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+?)\s*=\s*(.+?)\s*$') {
            $key = $matches[1]
            $value = $matches[2]
            if ($null -eq (Get-Item -Path env:$key -ErrorAction SilentlyContinue)) {
                Set-Item -Path env:$key -Value $value
            }
        }
    }
}

# Set safe defaults for required env vars (only if not already set)
$envDefaults = @{
    "JWT_SECRET" = "alembic-dev-secret"
    "JWT_ALGORITHM" = "HS256"
    "GOOGLE_CLIENT_ID" = "alembic-dummy"
    "GOOGLE_CLIENT_SECRET" = "alembic-dummy"
    "GOOGLE_REDIRECT_URI" = "http://localhost:3000"
    "EMAIL_HOST" = "localhost"
    "EMAIL_PORT" = "587"
    "EMAIL_USERNAME" = "alembic"
    "EMAIL_PASSWORD" = "alembic"
    "EMAIL_FROM" = "noreply@fagoon.ai"
    "GCS_BUCKET_NAME" = "alembic-dummy"
    "GEMINI_API_KEY" = "alembic-dummy"
    "VIDEO_STORAGE_PATH" = "/tmp/videos"
    "CELERY_BROKER_URL" = "redis://localhost:6379/0"
    "CELERY_RESULT_BACKEND" = "redis://localhost:6379/1"
    "SECRET_KEY" = "alembic-dev-secret"
    "FAGOON_URL" = "http://localhost:3000"
    "DEFAULT_URL" = "http://localhost:3000"
    "SERPER_API_KEY" = "alembic-dummy"
    "SERPAPI_API_KEY" = "alembic-dummy"
    "COOKIE_DOMAIN_1" = "localhost"
    "COOKIE_DOMAIN_2" = "localhost"
    "COOKIE_DOMAIN_3" = "localhost"
}

Write-Host "Setting environment defaults..." -ForegroundColor Cyan
foreach ($key in $envDefaults.Keys) {
    if ($null -eq (Get-Item -Path env:$key -ErrorAction SilentlyContinue)) {
        Set-Item -Path env:$key -Value $envDefaults[$key]
        Write-Host "  $key = $($envDefaults[$key])" -ForegroundColor DarkGray
    }
}

# Display important env vars
Write-Host "`nActive Environment:" -ForegroundColor Green
Write-Host "  DATABASE_URL = $($env:DATABASE_URL)" -ForegroundColor White
Write-Host "  JWT_SECRET = $($env:JWT_SECRET.Substring(0, [Math]::Min(20, $env:JWT_SECRET.Length)))..." -ForegroundColor White

# Run Alembic with provided arguments
Write-Host "`nRunning: alembic $($AlembicArgs -join ' ')" -ForegroundColor Yellow
& .venv\Scripts\alembic.exe @AlembicArgs

exit $LASTEXITCODE
