# start_demo.ps1 — Launches the full Incident Copilot demo suite on Windows PowerShell
$ErrorActionPreference = "Stop"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "🧠 Starting Incident Memory Copilot + OneUptime Demo Environment" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

# 1. Start target microservice
Write-Host "1. Launching target microservice (checkout-api) on port 8080..." -ForegroundColor Yellow
$serviceProcess = Start-Process -FilePath "uv" -ArgumentList "run", "python", "examples/real_world_app/server.py" -PassThru -NoNewWindow

# 2. Start OneUptime webhook receiver
Write-Host "2. Launching OneUptime Webhook Receiver on port 8787..." -ForegroundColor Yellow
$webhookProcess = Start-Process -FilePath "uv" -ArgumentList "run", "python", "src/integrations/webhook_server.py" -PassThru -NoNewWindow

Start-Sleep -Seconds 2

try {
    # 3. Launch Streamlit UI
    Write-Host "3. Opening Streamlit Incident Copilot on http://localhost:8501..." -ForegroundColor Green
    & uv run streamlit run app.py
}
finally {
    Write-Host "`nStopping background services..." -ForegroundColor Magenta
    if ($serviceProcess -and -not $serviceProcess.HasExited) {
        Stop-Process -Id $serviceProcess.Id -Force -ErrorAction SilentlyContinue
    }
    if ($webhookProcess -and -not $webhookProcess.HasExited) {
        Stop-Process -Id $webhookProcess.Id -Force -ErrorAction SilentlyContinue
    }
    Write-Host "All demo background processes stopped cleanly." -ForegroundColor Green
}
