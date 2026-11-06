"""Minimal OneUptime -> Hindsight webhook receiver.

Run:
    uv run python src/integrations/webhook_server.py

Then point a OneUptime Workflow (On Create Incident -> API Post JSON) at:
    http://<host>:8787/oneuptime

No extra dependencies: stdlib HTTP server + the same MemoryStore as the app.
Bind to 127.0.0.1 by default. Set ONEUPTIME_WEBHOOK_TOKEN to require
``X-OneUptime-Token``. This is a demo receiver, not an authenticated public API.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# Ensure repo root is on sys.path when executed directly
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

from src.core.agent import run_agent
from src.core.memory import MemoryStore
from src.integrations.oneuptime import incident_to_document, parse_oneuptime

load_dotenv()

HOST = os.getenv("ONEUPTIME_WEBHOOK_HOST") or "127.0.0.1"
PORT = int(os.getenv("ONEUPTIME_WEBHOOK_PORT") or "8787")
TOKEN = os.getenv("ONEUPTIME_WEBHOOK_TOKEN", "").strip()
MAX_BODY = 1_000_000

store = MemoryStore()
backend = store.connect()
store.configure_bank()
STORE_LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    server_version = "OneUptimeMemory/1.0"

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler name
        if self.path.split("?")[0] not in ("/", "/health"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        self._json(
            200,
            {
                "ok": True,
                "backend": backend,
                "bank": store.bank_id,
                "hint": "POST a OneUptime incident JSON to /oneuptime",
            },
        )

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler name
        base_path = self.path.split("?")[0].rstrip("/")
        query = self.path.split("?")[1] if "?" in self.path else ""
        if base_path not in ("/oneuptime", "/oneuptime/briefing", "/oneuptime/webhook"):
            self._json(404, {"ok": False, "error": "not found"})
            return
        if TOKEN:
            supplied = self.headers.get("X-OneUptime-Token", "")
            if not hmac.compare_digest(supplied, TOKEN):
                self._json(
                    401, {"ok": False, "error": "bad or missing X-OneUptime-Token"}
                )
                return

        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            self._json(400, {"ok": False, "error": "Content-Length required"})
            return
        if length > MAX_BODY:
            self._json(413, {"ok": False, "error": "payload too large"})
            return

        raw = self.rfile.read(length)
        try:
            raw_text = raw.decode("utf-8")
            incident = parse_oneuptime(raw_text)

            # Check if this request asks for an AI incident memory briefing
            want_briefing = (
                base_path.endswith("/briefing")
                or "brief=true" in query.lower()
                or '"brief": true' in raw_text.lower()
                or '"briefing": true' in raw_text.lower()
            )
            briefing_text = None
            memories_count = 0

            with STORE_LOCK:
                # If resolved or retain explicitly requested, retain in Hindsight
                is_resolved = incident.status.lower() in ("resolved", "closed")
                if is_resolved or not want_briefing:
                    store.retain(
                        incident_to_document(incident),
                        context=(
                            f"OneUptime incident {incident.id} "
                            f"(OneUptime ID {incident.oneuptime_id or 'unknown'}) "
                            f"on {incident.service}"
                        ),
                        timestamp=incident.date,
                        document_id=f"oneuptime-{incident.id}",
                        update_mode="replace",
                    )

                # If an active incident briefing was requested, run Hindsight memory recall
                if want_briefing:
                    briefing_text, recalled = run_agent(
                        incident.service,
                        incident.title,
                        incident.symptoms,
                        store,
                        use_memory=True,
                    )
                    memories_count = len(recalled)

        except (UnicodeDecodeError, ValueError) as exc:
            self._json(400, {"ok": False, "error": f"invalid payload: {exc}"})
            return
        except Exception as exc:  # Hindsight/network/store failure
            self._json(
                502,
                {"ok": False, "error": f"{type(exc).__name__}: {exc}"},
            )
            return

        resp_payload: dict[str, object] = {
            "ok": True,
            "incident_id": incident.id,
            "oneuptime_id": incident.oneuptime_id,
            "service": incident.service,
            "backend": store.backend,
        }
        if briefing_text:
            resp_payload["briefing"] = briefing_text
            resp_payload["recalled_memories_count"] = memories_count

        self._json(200, resp_payload)

    def log_message(self, fmt: str, *args: object) -> None:
        print(f"[oneuptime] {self.address_string()} {fmt % args}")


def main() -> None:
    print(f"OneUptime receiver: http://{HOST}:{PORT}/oneuptime")
    print(f"Memory backend: {backend} · bank: {store.bank_id}")
    if backend != "hindsight":
        print("WARNING: local fallback active; memories will not survive this process.")
    if TOKEN:
        print("Token auth enabled: send X-OneUptime-Token.")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
        store.close()


if __name__ == "__main__":
    main()
