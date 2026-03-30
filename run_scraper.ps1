# run_scraper.ps1 — Full job scraper pipeline
# Run manually:  powershell -ExecutionPolicy Bypass -File run_scraper.ps1
# Registered as a daily Task Scheduler task at 7 AM

$ProjectDir = "C:\Users\RAJSAI\scraper-2.0"
$LogFile    = "$ProjectDir\logs\scraper.log"

Set-Location $ProjectDir

# Ensure logs directory exists
if (-not (Test-Path "$ProjectDir\logs")) {
    New-Item -ItemType Directory -Path "$ProjectDir\logs" | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Write-Output "[$timestamp] Starting pipeline..." | Tee-Object -FilePath $LogFile -Append

python -m src.cli pipeline 2>&1 | Tee-Object -FilePath $LogFile -Append

$exitCode = $LASTEXITCODE
$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
if ($exitCode -eq 0) {
    Write-Output "[$timestamp] Pipeline completed successfully." | Tee-Object -FilePath $LogFile -Append
} else {
    Write-Output "[$timestamp] Pipeline FAILED with exit code $exitCode." | Tee-Object -FilePath $LogFile -Append
}
