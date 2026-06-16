# Check if ollama is installed
$ollamaPath = Get-Command ollama -ErrorAction SilentlyContinue

if ($null -eq $ollamaPath) {
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "ERROR: Ollama is not installed!" -ForegroundColor Red
    Write-Host "Please download and install Ollama from https://ollama.com" -ForegroundColor Yellow
    Write-Host "Once installed, rerun this script to pull the local fallback model." -ForegroundColor Yellow
    Write-Host "==========================================" -ForegroundColor Red
    Exit
}

Write-Host "==========================================" -ForegroundColor Green
Write-Host "Ollama is installed. Fetching Gemma 2B model..." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green

& ollama pull gemma:2b

Write-Host "==========================================" -ForegroundColor Green
Write-Host "Success! Gemma 2B fallback model is ready." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
