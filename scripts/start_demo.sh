#!/usr/bin/env bash
# start_demo.sh — Launches the full Incident Copilot demo suite
set -e

echo "================================================================="
echo "🧠 Starting Incident Memory Copilot + OneUptime Demo Environment"
echo "================================================================="

# 1. Start the target eCommerce checkout microservice in the background
echo "1. Launching target microservice (checkout-api) on port 8080..."
uv run python examples/real_world_app/server.py &
SERVICE_PID=$!

# 2. Start the OneUptime webhook receiver on port 8787
echo "2. Launching OneUptime Webhook Receiver on port 8787..."
uv run python src/integrations/webhook_server.py &
WEBHOOK_PID=$!

# Ensure cleanup on exit
trap "echo 'Stopping background services...'; kill $SERVICE_PID $WEBHOOK_PID 2>/dev/null" EXIT

sleep 1

# 3. Launch Streamlit UI
echo "3. Opening Streamlit Incident Copilot..."
uv run streamlit run app.py
