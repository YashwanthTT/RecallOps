"""OneUptime -> Hindsight incident adapter.

OneUptime has no stable public incident webhook/API documented, so this module
accepts the two paths that do work:

* JSON pasted from an export or from a Workflows **API Post (JSON)** block;
* plain text copied from an incident page.

The parser is deliberately forgiving: keys are case/spacing-insensitive,
common nested shapes such as ``{"incident": {...}}`` are unwrapped, and lists
or dicts are rendered as text.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

SAMPLE_PAYLOAD: dict[str, Any] = {
    "id": "8f14e45f-ceea-467f-a1b2-0d3c1b9a7e21",
    "number": 9001,
    "title": "Checkout API 5xx spike after v3.4.1 (OneUptime monitor)",
    "description": (
        "OneUptime monitor fired: checkout-api 5xx rate 18% for 8 minutes, "
        "p95 latency 9.4s, checkout success rate down 41%."
    ),
    "service": "checkout-api",
    "severity": "Critical",
    "status": "Resolved",
    "createdAt": "2026-11-06T18:40:00Z",
    "resolvedAt": "2026-11-06T19:06:00Z",
    "rootCause": (
        "v3.4.1 lowered Hikari maximumPoolSize to 12 and added a synchronous "
        "FX-rate lookup inside the payment transaction."
    ),
    "resolution": (
        "Rolled back with `deploy rollback --service checkout-api --to v3.4.0 "
        '--reason "pool exhaustion after v3.4.1"` and restored DB_POOL_MAX=40.'
    ),
    "whatFailed": (
        "Scaling checkout-api to 20 replicas exhausted Postgres connections; "
        "restarting all pods re-exhausted the pool in under 3 minutes."
    ),
    "assignedTo": "Priya Nair",
    "logs": (
        "2026-11-06T18:41:02Z checkout-api HikariPool-1 - Connection is not available, "
        "request timed out after 30000ms\n"
        "2026-11-06T18:41:15Z deploy-bot INFO v3.4.1 rolled out 6m before alert"
    ),
    "url": "http://localhost/incidents/8f14e45f-ceea-467f-a1b2-0d3c1b9a7e21",
}


@dataclass
class OneUptimeIncident:
    """Normalized incident that can be rendered as a Hindsight document."""

    id: str
    oneuptime_id: str = ""
    date: str = ""
    service: str = "oneuptime"
    title: str = "OneUptime incident"
    severity: str = ""
    status: str = ""
    symptoms: str = ""
    root_cause: str = "Not recorded in OneUptime."
    resolution: str = "Not recorded in OneUptime."
    what_failed: str = "Not recorded in OneUptime."
    ttr_minutes: int = 0
    responder: str = "Unassigned"
    url: str = ""

    def to_document(self) -> str:
        """Render the same fields the agent already knows how to parse."""
        return (
            f"Incident ID: {self.id}\n"
            f"Date: {self.date}\n"
            f"Service: {self.service}\n"
            f"Title: {self.title}\n"
            f"OneUptime ID: {self.oneuptime_id or 'unknown'}\n"
            f"Severity: {self.severity or 'unknown'}\n"
            f"Status: {self.status or 'unknown'}\n"
            f"Symptoms:\n{self.symptoms or 'No description or logs supplied.'}\n"
            f"Root cause: {self.root_cause or 'Not recorded in OneUptime.'}\n"
            f"Resolution:\n{_numbered(self.resolution)}\n"
            f"What failed (made it worse):\n{_bullets(self.what_failed)}\n"
            f"TTR: {self.ttr_minutes} minutes\n"
            f"Responder: {self.responder or 'Unassigned'}\n"
            f"Source: OneUptime\n"
            f"URL: {self.url or 'not provided'}"
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _norm(key: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(key).lower())


def _text(value: Any) -> str:
    """Render one payload value as plain text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float, bool)):
        return str(value)
    if isinstance(value, list):
        return "\n".join(part for part in (_text(item) for item in value) if part)
    if isinstance(value, dict):
        for key in ("name", "title", "description", "text", "value", "summary"):
            if key in value:
                return _text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten common wrappers while keeping specific nested fields."""
    merged: dict[str, Any] = {}
    wrappers = {
        "incident",
        "data",
        "payload",
        "body",
        "record",
        "result",
        "requestbody",
        "request",
        "event",
    }

    def merge(source: dict[str, Any]) -> None:
        for key, value in source.items():
            if isinstance(value, dict) and _norm(key) in wrappers:
                merge(value)
            else:
                merged.setdefault(key, value)

    merge(payload)
    return merged


def _first(payload: dict[str, Any], *keys: str) -> Any:
    """Case/spacing-insensitive first non-empty value."""
    flat = {_norm(key): value for key, value in payload.items()}
    for key in keys:
        value = flat.get(_norm(key))
        if value not in (None, "", [], {}):
            return value
    return None


def _parse_dt(value: Any) -> datetime | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:19], fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _incident_id(raw_id: str, number: str, created: datetime) -> str:
    digits = re.sub(r"\D", "", number) or re.sub(r"\D", "", raw_id)
    if digits:
        return f"INC-OU{digits}"
    token = re.sub(r"[^A-Za-z0-9]", "", raw_id).upper()[:12]
    if token:
        return f"INC-OU{token}"
    return f"INC-OU{created:%y%m%d%H%M%S}"


def _numbered(value: str) -> str:
    lines = [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        for line in str(value or "").splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        return "1. Not recorded in OneUptime."
    return "\n".join(f"{index}. {line}" for index, line in enumerate(lines, 1))


def _bullets(value: str) -> str:
    lines = [
        re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", line).strip()
        for line in str(value or "").splitlines()
    ]
    lines = [line for line in lines if line]
    if not lines:
        return "- Not recorded in OneUptime."
    return "\n".join(f"- {line}" for line in lines)


def _parse_text(text: str) -> dict[str, Any]:
    """Parse ``Key: value`` text copied from an incident page."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S)
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    data: dict[str, Any] = {}
    current: str | None = None
    for line in cleaned.splitlines():
        match = re.match(r"^\s*([A-Za-z][A-Za-z0-9 _/-]{1,40}):\s*(.*)$", line)
        if match:
            current = match.group(1).strip()
            data[current] = match.group(2).strip()
        elif current and line.strip():
            data[current] = f"{data[current]}\n{line.strip()}".strip()
    if not data and cleaned:
        data["description"] = cleaned
    return data


def parse_oneuptime(payload: str | dict[str, Any]) -> OneUptimeIncident:
    """Normalize a OneUptime JSON payload or pasted incident text.

    Raises:
        ValueError: the payload is empty or not an object.
    """
    if isinstance(payload, str):
        data = _parse_text(payload)
    elif isinstance(payload, dict):
        data = payload
    else:
        raise ValueError("OneUptime payload must be a JSON object or text")

    if not isinstance(data, dict) or not data:
        raise ValueError("OneUptime payload is empty")
    data = _unwrap(data)

    raw_id = _text(
        _first(
            data,
            "number",
            "incidentNumber",
            "incidentNo",
            "id",
            "incidentId",
            "uuid",
            "_id",
        )
    )
    number = _text(_first(data, "number", "incidentNumber", "incidentNo"))

    created = (
        _parse_dt(
            _first(
                data,
                "createdAt",
                "created_at",
                "declaredAt",
                "startedAt",
                "detectedAt",
                "timestamp",
            )
        )
        or _now()
    )
    resolved = _parse_dt(
        _first(data, "resolvedAt", "resolved_at", "closedAt", "endedAt", "recoveredAt")
    )

    description = _text(
        _first(
            data, "description", "details", "message", "alertDescription", "symptoms"
        )
    )
    logs = _text(
        _first(data, "logs", "timeline", "events", "activity", "notes", "comments")
    )
    symptoms = "\n\n".join(part for part in (description, logs) if part)
    title = _text(
        _first(
            data, "title", "name", "incidentTitle", "summary", "subject", "alertName"
        )
    )
    if not title:
        title = (symptoms.splitlines()[0] if symptoms else "OneUptime incident")[:120]

    service = _text(
        _first(
            data,
            "service",
            "serviceName",
            "monitor",
            "monitorName",
            "affectedService",
            "resource",
            "component",
        )
    )
    if not service:
        labels = _first(data, "labels", "tags")
        if isinstance(labels, dict):
            service = _text(
                _first(labels, "service", "serviceName", "app", "component")
            )
        elif isinstance(labels, list):
            for label in labels:
                match = re.match(r"service[:=](.+)", str(label), re.IGNORECASE)
                if match:
                    service = match.group(1).strip()
                    break

    explicit_ttr = re.sub(
        r"\D", "", _text(_first(data, "ttr", "timeToResolve", "durationMinutes"))
    )
    if explicit_ttr:
        ttr = int(explicit_ttr)
    elif resolved and resolved >= created:
        ttr = max(0, round((resolved - created).total_seconds() / 60))
    else:
        ttr = 0

    return OneUptimeIncident(
        id=_incident_id(raw_id, number, created),
        oneuptime_id=raw_id,
        date=_iso(created),
        service=service or "oneuptime",
        title=title,
        severity=_text(
            _first(data, "severity", "priority", "impact", "incidentSeverity")
        ),
        status=_text(_first(data, "status", "state", "currentState", "incidentState")),
        symptoms=symptoms,
        root_cause=_text(
            _first(data, "rootCause", "root_cause", "cause", "postmortemRootCause")
        )
        or "Not recorded in OneUptime.",
        resolution=_text(
            _first(
                data,
                "resolution",
                "resolutionNotes",
                "remediation",
                "remediationNotes",
                "whatFixed",
                "fix",
                "postmortem",
                "postMortem",
            )
        )
        or "Not recorded in OneUptime.",
        what_failed=_text(
            _first(
                data,
                "whatFailed",
                "whatWentWrong",
                "whatDidNotWork",
                "failedActions",
                "lessonsLearned",
            )
        )
        or "Not recorded in OneUptime.",
        ttr_minutes=ttr,
        responder=_text(
            _first(
                data,
                "assignedTo",
                "assignedToUser",
                "assignee",
                "owner",
                "resolvedBy",
                "responder",
            )
        )
        or "Unassigned",
        url=_text(_first(data, "url", "incidentUrl", "link", "permalink")),
    )


def incident_to_document(incident: OneUptimeIncident) -> str:
    """Render a normalized incident for ``MemoryStore.retain``."""
    return incident.to_document()


@dataclass
class ProbeResult:
    """Result of an HTTP/TCP monitor probe."""

    url: str
    status_code: int
    latency_ms: float
    healthy: bool
    error: str = ""
    checked_at: str = ""
    service: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def probe_endpoint(url: str, timeout: float = 4.0, service: str = "") -> ProbeResult:
    """Probes any real-world URL or localhost endpoint (OneUptime monitor style)."""
    now_str = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    target_url = url.strip()
    if not target_url.startswith(("http://", "https://")):
        target_url = f"https://{target_url}"

    start = time.perf_counter()
    req = urllib.request.Request(
        target_url,
        headers={
            "User-Agent": "OneUptime-Hindsight-Probe/1.0 (+https://github.com/oneuptime/oneuptime)",
            "Accept": "*/*",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            latency = (time.perf_counter() - start) * 1000
            code = resp.getcode()
            headers = dict(resp.headers.items()) if hasattr(resp, "headers") else {}
            healthy = 200 <= code < 400
            return ProbeResult(
                url=target_url,
                status_code=code,
                latency_ms=round(latency, 1),
                healthy=healthy,
                checked_at=now_str,
                service=service or "web-service",
                headers=headers,
            )
    except urllib.error.HTTPError as exc:
        latency = (time.perf_counter() - start) * 1000
        return ProbeResult(
            url=target_url,
            status_code=exc.code,
            latency_ms=round(latency, 1),
            healthy=False,
            error=f"HTTP {exc.code}: {exc.reason}",
            checked_at=now_str,
            service=service or "web-service",
        )
    except Exception as exc:
        latency = (time.perf_counter() - start) * 1000
        return ProbeResult(
            url=target_url,
            status_code=0,
            latency_ms=round(latency, 1),
            healthy=False,
            error=f"{type(exc).__name__}: {exc}",
            checked_at=now_str,
            service=service or "web-service",
        )


def create_incident_from_probe(
    probe: ProbeResult, title: str = "", extra_details: str = ""
) -> OneUptimeIncident:
    """Convert a failed monitor probe into a full OneUptime incident."""
    now = datetime.now(timezone.utc)
    ts = now.strftime("%y%m%d%H%M%S")
    inc_title = (
        title
        or f"{probe.service or 'Endpoint'} probe failed ({probe.error or f'HTTP {probe.status_code}'})"
    )
    symptoms = (
        f"OneUptime monitor alert for {probe.url}:\n"
        f"Status code: {probe.status_code}\n"
        f"Latency: {probe.latency_ms} ms\n"
        f"Error: {probe.error or 'None'}\n"
        f"Checked at: {probe.checked_at}\n"
    )
    if extra_details:
        symptoms += f"\nTelemetry details:\n{extra_details}"

    return OneUptimeIncident(
        id=f"INC-OU{ts}",
        oneuptime_id=f"mon-{ts}",
        date=probe.checked_at or now.isoformat().replace("+00:00", "Z"),
        service=probe.service or "web-service",
        title=inc_title,
        severity=(
            "Critical" if probe.status_code >= 500 or probe.status_code == 0 else "High"
        ),
        status="Investigating",
        symptoms=symptoms,
        root_cause="Under investigation by on-call responder and Hindsight copilot.",
        resolution="Pending resolution.",
        what_failed="Outage just detected; avoid knee-jerk restarts or blind scaling without consulting history.",
        ttr_minutes=0,
        responder="On-Call Engineer",
        url=probe.url,
    )


SIMULATED_SCENARIOS: dict[str, dict[str, Any]] = {
    "checkout-pool-exhaustion": {
        "id": "ou-inc-9001",
        "number": 9001,
        "title": "Checkout API 5xx spike after v3.4.1 (OneUptime monitor)",
        "service": "checkout-api",
        "severity": "Critical",
        "status": "Active Outage",
        "description": "OneUptime HTTP Monitor fired on /api/v1/checkout: 5xx rate 18% for 8 minutes, p95 latency 9.4s, checkout success rate down 41%.",
        "logs": "2026-11-06T18:41:02Z checkout-api HikariPool-1 - Connection is not available, request timed out after 30000ms\n2026-11-06T18:41:15Z deploy-bot INFO v3.4.1 rolled out 6m before alert",
        "rootCause": "v3.4.1 lowered Hikari maximumPoolSize to 12 and added a synchronous FX-rate lookup inside the payment transaction.",
        "resolution": 'Rolled back with `deploy rollback --service checkout-api --to v3.4.0 --reason "pool exhaustion after v3.4.1"` and restored DB_POOL_MAX=40.',
        "whatFailed": "Scaling checkout-api to 20 replicas exhausted Postgres connections; restarting all pods re-exhausted the pool in under 3 minutes.",
        "assignedTo": "Marcus Bell",
        "url": "http://localhost/incidents/ou-inc-9001",
    },
    "payment-gateway-timeout": {
        "id": "ou-inc-9002",
        "number": 9002,
        "title": "Payment Gateway 504 Gateway Timeout during Acquirer Outage",
        "service": "payment-gateway",
        "severity": "Critical",
        "status": "Active Outage",
        "description": "OneUptime synthetic probe failed: payment-gateway POST /charges returned 504. External acquirer latency exceeded 15000ms threshold.",
        "logs": "2026-11-06T19:12:01Z payment-gw [WARN] Acquirer client socket timeout 15000ms\n2026-11-06T19:12:05Z payment-gw [ERROR] CircuitBreaker 'AcquirerPrimary' state OPEN",
        "rootCause": "Upstream acquirer outage caused thread starvation when timeouts were set to 15s instead of 2.5s with fallback.",
        "resolution": "Enabled secondary payment rail via feature flag `ff_acquirer_secondary_rail=true` and lowered client timeout to 2500ms.",
        "whatFailed": "Retrying payments immediately flooded the primary acquirer and tripped circuit breakers across all workers.",
        "assignedTo": "Anika Rao",
        "url": "http://localhost/incidents/ou-inc-9002",
    },
    "auth-cache-eviction": {
        "id": "ou-inc-9003",
        "number": 9003,
        "title": "Auth Service 500 spike from Redis Token Eviction Storm",
        "service": "auth-service",
        "severity": "High",
        "status": "Active Outage",
        "description": "OneUptime endpoint monitor: auth-service /v1/validate token validation latency climbed to 850ms, 401/500 rate 12%.",
        "logs": "2026-11-06T19:30:10Z auth-service [ERROR] RedisCommandTimeoutException: Command timed out after 3000ms\n2026-11-06T19:30:14Z redis [WARN] maxmemory-policy allkeys-lru triggered heavy eviction",
        "rootCause": "Unbounded session metadata caching without TTL pushed Redis memory over 95%, causing thundering herd on Postgres auth table.",
        "resolution": "Applied session TTL policy, cleared stale refresh tokens, and warm-booted Redis replica before switching traffic.",
        "whatFailed": "Flushing Redis cache completely (`FLUSHALL`) caused 100% of incoming requests to hit Postgres directly, taking down the entire auth DB.",
        "assignedTo": "Elena Rostova",
        "url": "http://localhost/incidents/ou-inc-9003",
    },
    "orders-db-disk-pressure": {
        "id": "ou-inc-9004",
        "number": 9004,
        "title": "Orders DB IOPS saturation and connection queue spike",
        "service": "orders-db",
        "severity": "Critical",
        "status": "Active Outage",
        "description": "OneUptime TCP probe: orders-db port 5432 query latency > 5000ms. Disk write queue length > 45.",
        "logs": "2026-11-06T19:45:00Z postgres [LOG] checkpoints are occurring too frequently (9 seconds apart)\n2026-11-06T19:45:15Z postgres [FATAL] remaining connection slots are reserved for non-replication superuser connections",
        "rootCause": "Missing index on orders(customer_id, created_at) caused full table scans during a marketing campaign, saturating IOPS.",
        "resolution": "Created concurrent index `idx_orders_customer_created` and terminated long-running reporting queries.",
        "whatFailed": "Restarting Postgres during peak load caused a 22-minute WAL recovery period during which no orders could be placed.",
        "assignedTo": "Wei Zhang",
        "url": "http://localhost/incidents/ou-inc-9004",
    },
}


def create_incident_from_scenario(scenario_key: str) -> OneUptimeIncident:
    """Generate an authentic OneUptimeIncident from a predefined outage scenario."""
    payload = SIMULATED_SCENARIOS.get(scenario_key)
    if not payload:
        raise ValueError(f"Unknown outage scenario: {scenario_key}")
    return parse_oneuptime(payload)


class OneUptimeClient:
    """Client for connecting to a real running OneUptime server."""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        project_id: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("ONEUPTIME_URL") or "http://localhost"
        ).rstrip("/")
        self.api_key = api_key or os.getenv("ONEUPTIME_API_KEY", "")
        self.project_id = project_id or os.getenv("ONEUPTIME_PROJECT_ID", "")
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.api_key:
            headers["ApiKey"] = self.api_key
        if self.project_id:
            headers["TenantId"] = self.project_id
        return headers

    def test_connection(self) -> tuple[bool, str]:
        """Probes OneUptime health/status endpoint."""
        url = f"{self.base_url}/status"
        try:
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if 200 <= resp.getcode() < 300:
                    return (
                        True,
                        f"Connected to OneUptime at {self.base_url} (HTTP {resp.getcode()})",
                    )
                return False, f"OneUptime returned HTTP {resp.getcode()}"
        except Exception as exc:
            return False, f"Could not reach OneUptime at {self.base_url}: {exc}"

    def fetch_incidents(self, limit: int = 10) -> list[dict[str, Any]]:
        """Fetch real incidents from OneUptime API."""
        url = f"{self.base_url}/api/incident?limit={limit}"
        try:
            req = urllib.request.Request(url, headers=self._headers(), method="GET")
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if isinstance(data, list):
                    return data
                if (
                    isinstance(data, dict)
                    and "data" in data
                    and isinstance(data["data"], list)
                ):
                    return data["data"]
                return []
        except Exception:
            return []

    def post_internal_note(self, incident_id: str, note: str) -> bool:
        """Post a Hindsight memory briefing as an internal note onto a OneUptime incident."""
        url = f"{self.base_url}/api/incident-internal-note"
        payload = {
            "incidentId": incident_id,
            "note": note,
        }
        try:
            body = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, data=body, headers=self._headers(), method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return 200 <= resp.getcode() < 300
        except Exception:
            return False
