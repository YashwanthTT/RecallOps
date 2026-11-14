"""Memory layer for the Incident Memory Agent.

Hindsight is the only memory backend: ``retain``, ``recall``, and ``reflect``
all go to the Hindsight server. There is no in-process fallback. If Hindsight
is unreachable the store reports ``backend == "unavailable"`` and every memory
operation raises, so the app can say so instead of pretending.

Hindsight client API (verified against the 1.2 docs and installed package):

    client.retain(bank_id=..., content=..., context=..., timestamp=...)
    res = client.recall(bank_id=..., query=...)
    for r in res.results: r.text
    out = client.reflect(bank_id=..., query=...); out.text

Note: the client's ``recall`` has no ``limit`` argument, so this wrapper slices
``res.results`` to the requested limit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8888"
DEFAULT_BANK_ID = "incident-response-agent"


@dataclass
class Memory:
    """One recalled memory and its relevance score (higher is better)."""

    text: str
    score: float = 0.0


def _numeric_scores(scores: Any) -> float:
    """Pull a single best-effort score out of Hindsight's scores object."""
    if isinstance(scores, (int, float)):
        return float(scores)
    if isinstance(scores, dict):
        values: list[float] = []
        for value in scores.values():
            if isinstance(value, (int, float)):
                values.append(float(value))
            elif isinstance(value, dict):
                values.extend(float(v) for v in value.values() if isinstance(v, (int, float)))
        return max(values, default=0.0)
    final = getattr(scores, "final", None)
    if isinstance(final, (int, float)):
        return float(final)
    if hasattr(scores, "model_dump"):
        return _numeric_scores(scores.model_dump())
    return 0.0


def _is_missing_bank(exc: Exception) -> bool:
    """A 404/not-found probe means the server is up but the bank is new."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    message = str(exc).lower()
    return status == 404 or "not found" in message or "404" in message


class MemoryStore:
    """Hindsight-backed memory. No local fallback.

    Attributes:
        backend: ``"hindsight"`` when the server answered, else ``"unavailable"``.
        error: the connection/import error string when Hindsight is unavailable.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, bank_id: str | None = None) -> None:
        self.base_url = base_url or os.getenv("HINDSIGHT_BASE_URL") or DEFAULT_BASE_URL
        self.api_key = api_key if api_key is not None else os.getenv("HINDSIGHT_API_KEY", "")
        self.bank_id = bank_id or os.getenv("HINDSIGHT_BANK_ID") or DEFAULT_BANK_ID
        self.backend = "unavailable"
        self.error: str | None = None
        self.warning: str | None = None
        self.timeout = float(os.getenv("HINDSIGHT_TIMEOUT") or "120")
        self._client: Any | None = None

    @property
    def connected(self) -> bool:
        return self.backend == "hindsight" and self._client is not None

    def connect(self) -> str:
        """Probe Hindsight. Returns ``"hindsight"`` or ``"unavailable"``.

        The probe is a cheap recall with a short timeout so a dead localhost
        fails fast. The operational client gets a long timeout because
        ``reflect`` runs an agentic loop and can take a minute on Cloud.
        """
        self.error = None
        self.close()
        try:
            from hindsight_client import Hindsight
        except Exception as exc:  # optional dependency / broken install
            self.error = f"hindsight-client import failed: {type(exc).__name__}: {exc}"
            self.backend = "unavailable"
            return self.backend

        probe: Any | None = None
        reachable = False
        try:
            probe = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key or None,
                timeout=min(8.0, self.timeout),
                max_attempts=1,
            )
            probe.recall(
                bank_id=self.bank_id,
                query="connectivity probe",
                budget="low",
                max_tokens=64,
            )
            reachable = True
        except Exception as exc:
            if _is_missing_bank(exc) and probe is not None:
                # Server is up; the bank is simply new.
                reachable = True
            else:
                self.error = f"{type(exc).__name__}: {exc}"

        if probe is not None:
            try:
                probe.close()
            except Exception:
                pass

        if not reachable:
            self.backend = "unavailable"
            return self.backend

        try:
            self._client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key or None,
                timeout=self.timeout,
                max_attempts=2,
            )
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.backend = "unavailable"
            return self.backend

        self.backend = "hindsight"
        return self.backend

    def _require(self) -> Any:
        """Return the client or fail loudly; memory has no offline mode."""
        if not self.connected:
            raise RuntimeError(
                f"Hindsight is required but unavailable at {self.base_url} "
                f"(bank {self.bank_id}): {self.error or 'not connected'}"
            )
        return self._client

    def close(self) -> None:
        """Close the underlying HTTP client, if any."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def retain(
        self,
        content: str,
        context: str = "",
        timestamp: str | None = None,
        document_id: str | None = None,
        update_mode: str | None = None,
    ) -> None:
        """Store one document in Hindsight. Raises when Hindsight is unavailable.

        ``document_id`` plus ``update_mode="replace"`` makes repeat seeding
        idempotent instead of piling up duplicate incidents in the bank.
        """
        client = self._require()
        kwargs: dict[str, Any] = {
            "bank_id": self.bank_id,
            "content": content,
            "context": context or None,
            "timestamp": timestamp,
        }
        if document_id:
            kwargs["document_id"] = document_id
        if update_mode:
            kwargs["update_mode"] = update_mode
        client.retain(**kwargs)

    def configure_bank(self) -> None:
        """Apply the bank mission and on-call directives used by ``reflect``.

        This is best-effort: an older server or a read-only key must not break
        the app, so failures are recorded in ``warning`` rather than raised.
        """
        self.warning: str | None = None
        if not self.connected:
            return
        try:
            self._client.create_bank(
                bank_id=self.bank_id,
                name="Incident Memory Agent",
                mission=(
                    "On-call incident-response memory for Northwind Pay. Store "
                    "resolved incidents, root causes, harmful remediation, and "
                    "time-bound escalation policies."
                ),
                reflect_mission=(
                    "Act as an incident commander. Use only retained incidents and "
                    "policies. Lead with actions that made past incidents worse, "
                    "cite incident IDs exactly, and never invent history."
                ),
            )
            existing = {
                getattr(item, "name", "")
                for item in (getattr(self._client.list_directives(self.bank_id), "items", []) or [])
            }
            for name, content, priority in (
                (
                    "Cite only retrieved incident IDs",
                    "Cite only incident IDs that appear in retrieved memories. Never invent an ID, command, or policy.",
                    10,
                ),
                (
                    "Lead with harmful remediation",
                    "Before recommending a fix, state the actions that made past incidents worse and the incident IDs that prove it.",
                    9,
                ),
                (
                    "Admit missing history",
                    "If no incident matches, say so plainly and give a generic runbook. Do not fabricate past incidents.",
                    8,
                ),
            ):
                if name not in existing:
                    self._client.create_directive(
                        bank_id=self.bank_id,
                        name=name,
                        content=content,
                        priority=priority,
                    )
        except Exception as exc:
            self.warning = f"Bank configuration skipped: {type(exc).__name__}: {exc}"

    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        """Return the most relevant memories from Hindsight, best first."""
        client = self._require()
        response = client.recall(
            bank_id=self.bank_id,
            query=query,
            budget="mid",
            max_tokens=4096,
        )
        results = list(getattr(response, "results", []) or [])
        memories: list[Memory] = []
        for item in results[:limit]:
            text = str(getattr(item, "text", ""))
            if not text:
                continue
            # Recalled facts can be split from the source document; keep the
            # stored context so an incident ID (e.g. INC-2139) is not lost.
            context = getattr(item, "context", None)
            if isinstance(context, str) and context and context not in text:
                text = f"{text}\nContext: {context}"
            memories.append(
                Memory(text=text, score=_numeric_scores(getattr(item, "scores", None)))
            )
        return memories

    def reflect(self, query: str) -> str:
        """Return a synthesised answer over the Hindsight bank."""
        client = self._require()
        response = client.reflect(bank_id=self.bank_id, query=query, budget="mid")
        text = getattr(response, "text", None)
        return str(text) if text else str(response)

    @property
    def status_label(self) -> str:
        """A short, honest status string for the UI."""
        if self.connected:
            return f"Hindsight connected ({self.base_url}, bank {self.bank_id})"
        return "Hindsight unavailable"
