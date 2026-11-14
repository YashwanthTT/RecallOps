"""Real-World Target Microservice: Northwind Pay checkout-api.

This is an authentic standalone microservice you can run locally and monitor
with OneUptime and the Hindsight Copilot.

Endpoints:
    GET  /health              - Synthetic health check (OneUptime probe target)
    POST /api/v1/checkout     - Process payment / checkout order
    GET  /metrics             - Prometheus-style connection pool metrics
    POST /chaos/break         - Inject v3.4.1 bug (Hikari pool exhaustion)
    POST /chaos/heal          - Apply rollback fix to v3.4.0 (DB_POOL_MAX=40)
    GET  /                    - Real-time HTML status dashboard with chaos controls

Run:
    uv run python examples/real_world_app/server.py
    # Runs on http://localhost:8080
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

HOST = os.getenv("CHECKOUT_API_HOST", "0.0.0.0")
PORT = int(os.getenv("CHECKOUT_API_PORT", "8080"))


class CheckoutServiceState:
    """In-memory service telemetry and chaos state."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.version = "v3.4.1"
        self.pool_max = 40
        self.pool_active = 4
        self.pool_pending = 0
        self.is_broken = False
        self.broken_reason = ""
        self.total_checkouts = 1420
        self.failed_checkouts = 2
        self.start_time = time.time()

    def break_service(self, reason: str = "Hikari connection pool exhaustion after v3.4.1 deploy") -> None:
        with self.lock:
            self.is_broken = True
            self.version = "v3.4.1 (FAULTY)"
            self.pool_max = 12
            self.pool_active = 12
            self.pool_pending = 48
            self.broken_reason = reason

    def heal_service(self) -> None:
        with self.lock:
            self.is_broken = False
            self.version = "v3.4.0 (ROLLED BACK)"
            self.pool_max = 40
            self.pool_active = 5
            self.pool_pending = 0
            self.broken_reason = ""

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "service": "checkout-api",
                "version": self.version,
                "healthy": not self.is_broken,
                "uptime_seconds": round(time.time() - self.start_time, 1),
                "db_pool": {
                    "max_connections": self.pool_max,
                    "active_connections": self.pool_active,
                    "pending_threads": self.pool_pending,
                },
                "total_checkouts": self.total_checkouts,
                "failed_checkouts": self.failed_checkouts,
                "broken_reason": self.broken_reason,
            }


state = CheckoutServiceState()


class CheckoutHandler(BaseHTTPRequestHandler):
    server_version = "Northwind-CheckoutAPI/3.4"

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def _html(self, status: int, html_str: str) -> None:
        body = html_str.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]

        if path == "/health":
            snap = state.snapshot()
            if not snap["healthy"]:
                self._json(
                    503,
                    {
                        "status": "DOWN",
                        "service": "checkout-api",
                        "version": snap["version"],
                        "error": (
                            "HikariPool-1 - Connection is not available, "
                            "request timed out after 30000ms"
                        ),
                        "db_pool": snap["db_pool"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            else:
                self._json(
                    200,
                    {
                        "status": "UP",
                        "service": "checkout-api",
                        "version": snap["version"],
                        "db_pool": snap["db_pool"],
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            return

        if path == "/metrics":
            snap = state.snapshot()
            metrics = [
                f"# HELP hikaricp_connections_active Active database connections",
                f"hikaricp_connections_active{{pool=\"HikariPool-1\"}} {snap['db_pool']['active_connections']}",
                f"# HELP hikaricp_connections_pending Blocked threads waiting for DB connection",
                f"hikaricp_connections_pending{{pool=\"HikariPool-1\"}} {snap['db_pool']['pending_threads']}",
                f"# HELP hikaricp_connections_max Maximum allowed pool size",
                f"hikaricp_connections_max{{pool=\"HikariPool-1\"}} {snap['db_pool']['max_connections']}",
                f"# HELP checkout_requests_total Total checkouts handled",
                f"checkout_requests_total {snap['total_checkouts']}",
            ]
            body = "\n".join(metrics) + "\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            return

        if path == "/chaos/break":
            state.break_service()
            self._json(200, {"ok": True, "action": "break", "state": state.snapshot()})
            return

        if path == "/chaos/heal":
            state.heal_service()
            self._json(200, {"ok": True, "action": "heal", "state": state.snapshot()})
            return

        # Dashboard UI
        snap = state.snapshot()
        status_color = "#e53e3e" if not snap["healthy"] else "#38a169"
        status_badge = "🔴 DOWN (OUTAGE ACTIVE)" if not snap["healthy"] else "🟢 OPERATIONAL"

        html = f"""<!DOCTYPE html>
<html>
<head>
  <title>Northwind Pay — Checkout API</title>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #0f172a; color: #f8fafc; padding: 40px; margin: 0; }}
    .card {{ background: #1e293b; border-radius: 12px; padding: 24px; max-width: 650px; margin: 0 auto; box-shadow: 0 10px 25px rgba(0,0,0,0.5); border: 1px solid #334155; }}
    .badge {{ display: inline-block; padding: 6px 14px; border-radius: 9999px; font-weight: 700; font-size: 14px; background: {status_color}; color: white; }}
    .metric-row {{ display: flex; justify-content: space-between; margin: 16px 0; border-bottom: 1px solid #334155; padding-bottom: 10px; }}
    .btn {{ display: inline-block; padding: 10px 18px; border-radius: 8px; font-weight: 600; text-decoration: none; cursor: pointer; border: none; margin-right: 10px; font-size: 14px; }}
    .btn-break {{ background: #dc2626; color: white; }}
    .btn-heal {{ background: #16a34a; color: white; }}
    .btn-check {{ background: #2563eb; color: white; }}
    code {{ background: #0f172a; padding: 3px 6px; border-radius: 4px; color: #38bdf8; font-size: 13px; }}
  </style>
</head>
<body>
  <div class="card">
    <h2>💳 Northwind Pay — checkout-api</h2>
    <p>Real-World Target Microservice monitored by <strong>OneUptime</strong> and triaged by <strong>Hindsight Copilot</strong>.</p>
    <div style="margin: 20px 0;">
      <span class="badge">{status_badge}</span>
      <span style="margin-left: 15px; color: #94a3b8;">Version: <code>{snap["version"]}</code></span>
    </div>
    
    <div class="metric-row">
      <span>Synthetic Health Check:</span>
      <code>GET /health</code>
    </div>
    <div class="metric-row">
      <span>Database Pool (Hikari):</span>
      <span>{snap["db_pool"]["active_connections"]} / {snap["db_pool"]["max_connections"]} active (Pending: {snap["db_pool"]["pending_threads"]})</span>
    </div>
    <div class="metric-row">
      <span>Total Checkouts Handled:</span>
      <span>{snap["total_checkouts"]}</span>
    </div>

    {"<div style='background: #450a0a; border: 1px solid #991b1b; padding: 12px; border-radius: 8px; margin: 16px 0;'><strong style='color: #fca5a5;'>Outage Details:</strong><br><span style='font-size: 13px; color: #fecaca;'>" + snap["broken_reason"] + "</span></div>" if not snap["healthy"] else ""}

    <h3 style="margin-top: 24px;">Chaos Controls (For Live Demo Video):</h3>
    <form action="/chaos/break" method="POST" style="display:inline;">
      <button type="submit" class="btn btn-break">💥 Break Service (Trigger Outage)</button>
    </form>
    <form action="/chaos/heal" method="POST" style="display:inline;">
      <button type="submit" class="btn btn-heal">🔄 Rollback to v3.4.0 (Heal Service)</button>
    </form>
    <a href="/health" target="_blank" class="btn btn-check">🔍 Probe /health</a>
  </div>
</body>
</html>"""
        self._html(200, html)

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?")[0]

        if path == "/chaos/break":
            state.break_service()
            self._redirect_to_dashboard()
            return

        if path == "/chaos/heal":
            state.heal_service()
            self._redirect_to_dashboard()
            return

        if path == "/api/v1/checkout":
            snap = state.snapshot()
            if not snap["healthy"]:
                state.failed_checkouts += 1
                self._json(
                    504,
                    {
                        "error": "Gateway Timeout",
                        "message": "Database connection pool exhausted. FX lookup timed out.",
                        "service": "checkout-api",
                    },
                )
            else:
                state.total_checkouts += 1
                self._json(
                    201,
                    {
                        "status": "APPROVED",
                        "order_id": f"ORD-{int(time.time()*1000)}",
                        "service": "checkout-api",
                    },
                )
            return

        self._json(404, {"error": "Not found"})

    def _redirect_to_dashboard(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        # Keep stdout clean and readable for demo
        pass


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), CheckoutHandler)
    print("=" * 70)
    print(f"🚀 Northwind Pay — checkout-api running on http://localhost:{PORT}")
    print(f"   • Health check:  http://localhost:{PORT}/health")
    print(f"   • Chaos trigger: http://localhost:{PORT}/chaos/break")
    print(f"   • Chaos heal:    http://localhost:{PORT}/chaos/heal")
    print("=" * 70)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping checkout-api.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
