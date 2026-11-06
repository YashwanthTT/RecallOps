# Northwind Pay — Real-World Target Service (`checkout-api`)

This microservice represents a real production payment service used in Northwind Pay. It demonstrates how **OneUptime** detects live outages and how the **Hindsight Copilot** recalls team memory to fix them.

## Endpoints

- `GET /health` — Synthetic health check monitored by OneUptime.
  - Normal: returns `HTTP 200 {"status": "UP", "version": "v3.4.1"}`.
  - Outage: returns `HTTP 503 {"status": "DOWN", "error": "HikariPool-1 connection timeout"}`.
- `POST /api/v1/checkout` — Payment processing endpoint.
- `GET /metrics` — Prometheus metrics (`hikaricp_connections_active`, `pending`).
- `POST /chaos/break` — Injects the `v3.4.1` bug (lowers pool size to 12, causes exhaustion).
- `POST /chaos/heal` — Rolls back to `v3.4.0` (restores pool size to 40, healthy state).
- `GET /` — Interactive web status dashboard with Chaos buttons.

## Running the Service

```bash
uv run python examples/real_world_app/server.py
```
Open [http://localhost:8080](http://localhost:8080) in your browser.
