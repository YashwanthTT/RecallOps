"""Memory layer for the Incident Memory Agent.

Primary backend: Hindsight (retain / recall / reflect).
Fallback backend: a deliberately small in-process keyword-overlap store. The
fallback exists so the demo runs with no server, and it is never hidden: the
UI and every briefing can see ``store.backend`` and ``store.error``.

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
import re
from dataclasses import dataclass
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8888"
DEFAULT_BANK_ID = "incident-response-agent"

_WORD_RE = re.compile(r"[a-z0-9][a-z0-9_.\-/]{1,}")
_STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "was", "were", "are",
    "has", "have", "had", "not", "but", "into", "after", "before", "when",
    "what", "who", "why", "how", "all", "any", "can", "did", "does", "our",
    "out", "per", "than", "then", "them", "they", "too", "via", "you", "your",
    "its", "it's", "during", "over", "under", "about", "also", "more", "most",
}


@dataclass
class Memory:
    """One recalled memory and its relevance score (higher is better)."""

    text: str
    score: float = 0.0


def _tokens(text: str) -> list[str]:
    """Lower-case word-ish tokens, with common stopwords removed."""
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


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
    return 0.0


def _is_missing_bank(exc: Exception) -> bool:
    """A 404/not-found probe means the server is up but the bank is new."""
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    message = str(exc).lower()
    return status == 404 or "not found" in message or "404" in message


class _LocalStore:
    """Small keyword-overlap fallback. Not a vector store, and says so."""

    def __init__(self) -> None:
        self.entries: list[dict[str, str]] = []

    def retain(self, content: str, context: str = "", timestamp: str | None = None) -> None:
        self.entries.append(
            {"content": content, "context": context, "timestamp": timestamp or ""}
        )

    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        query_tokens = set(_tokens(query))
        if not query_tokens or not self.entries:
            return []

        scored: list[Memory] = []
        for entry in self.entries:
            doc_tokens = set(_tokens(entry["content"] + " " + entry["context"]))
            if not doc_tokens:
                continue
            overlap = len(query_tokens & doc_tokens)
            coverage = overlap / len(query_tokens)
            precision = overlap / len(doc_tokens)
            score = 0.75 * coverage + 0.25 * precision

            # Exact technical strings matter more than individual words.
            lowered = entry["content"].lower()
            for phrase in ("hikaripool", "connection pool", "x509", "recovery", "consumer lag"):
                if phrase in query.lower() and phrase in lowered:
                    score += 0.03
            scored.append(Memory(text=entry["content"], score=round(score, 4)))

        scored.sort(key=lambda memory: memory.score, reverse=True)
        return scored[:limit]

    def reflect(self, query: str) -> str:
        """Deterministic local synthesis for the three demo questions."""
        if not self.entries:
            return (
                "No memories yet. Seed the past incidents and policies in the sidebar first, "
                "or connect a Hindsight server."
            )
        lowered = query.lower()
        if "recurring" in lowered or "pattern" in lowered:
            return self._recurring()
        if "worse" in lowered or "harm" in lowered:
            return self._harmful_actions()
        if "checkout-api" in lowered or "new on-call" in lowered:
            return self._service_brief("checkout-api")
        memories = self.recall(query, limit=4)
        lines = ["## Local fallback answer", ""]
        lines.append("Ranked by keyword overlap; connect Hindsight for a synthesised answer.")
        lines.append("")
        for memory in memories:
            title = _field(memory.text, "Title") or _field(memory.text, "Policy ID") or memory.text[:80]
            lines.append(f"- {title} (score {memory.score:.2f})")
        return "\n".join(lines)

    def _incidents(self) -> list[dict[str, str]]:
        return [
            {
                "id": _field(entry["content"], "Incident ID"),
                "service": _field(entry["content"], "Service"),
                "title": _field(entry["content"], "Title"),
                "ts": _field(entry["content"], "Date"),
                "text": entry["content"],
            }
            for entry in self.entries
            if "Incident ID:" in entry["content"]
        ]

    def _recurring(self) -> str:
        grouped: dict[str, list[dict[str, str]]] = {}
        for incident in self._incidents():
            grouped.setdefault(incident["service"], []).append(incident)
        lines = ["## Recurring failures (local fallback)", ""]
        for service, incidents in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
            ids = ", ".join(incident["id"] for incident in incidents)
            lines.append(f"- **{service}** — {len(incidents)} incidents ({ids})")
            for incident in incidents:
                lines.append(f"  - {incident['title']}")
        return "\n".join(lines)

    def _harmful_actions(self) -> str:
        lines = ["## Actions that made incidents worse (local fallback)", ""]
        for incident in self._incidents():
            failed = _block_items(incident["text"], "What failed (made it worse)")
            if failed:
                lines.append(f"**{incident['id']} / {incident['service']}**")
                for item in failed:
                    lines.append(f"- {item}")
                lines.append("")
        return "\n".join(lines).strip()

    def _service_brief(self, service: str) -> str:
        incidents = [i for i in self._incidents() if i["service"] == service]
        incidents.sort(key=lambda i: i["ts"], reverse=True)
        lines = [f"## What a new on-call engineer should know about {service} (local fallback)", ""]
        if not incidents:
            return "\n".join(lines + ["No incidents recorded for this service."])
        for incident in incidents:
            lines.append(f"### {incident['id']} — {incident['title']}")
            lines.append(f"- Date: {incident['ts']}")
            root = _field(incident["text"], "Root cause")
            if root:
                lines.append(f"- Root cause: {root}")
            failed = _block_items(incident["text"], "What failed (made it worse)")
            for item in failed:
                lines.append(f"- **Did not work:** {item}")
            lines.append("")
        return "\n".join(lines).strip()


def _field(text: str, label: str) -> str:
    """Read a single labelled line from a memory document."""
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _block_items(text: str, label: str) -> list[str]:
    """Read the bullet items under a labelled block, stopping at a blank line."""
    match = re.search(
        rf"^{re.escape(label)}:\s*\n((?:(?:- |\d+\. ).*\n?)+)",
        text,
        re.MULTILINE,
    )
    if not match:
        return []
    return [
        re.sub(r"^(?:- |\d+\. )", "", line).strip()
        for line in match.group(1).splitlines()
        if line.strip()
    ]


class MemoryStore:
    """Hindsight-backed memory with a transparent local fallback.

    Attributes:
        backend: ``"hindsight"`` when the server answered, else ``"local"``.
        error: the connection/import error string when the fallback is active.
    """

    def __init__(self, base_url: str | None = None, api_key: str | None = None, bank_id: str | None = None) -> None:
        self.base_url = base_url or os.getenv("HINDSIGHT_BASE_URL") or DEFAULT_BASE_URL
        self.api_key = api_key if api_key is not None else os.getenv("HINDSIGHT_API_KEY", "")
        self.bank_id = bank_id or os.getenv("HINDSIGHT_BANK_ID") or DEFAULT_BANK_ID
        self.backend = "local"
        self.error: str | None = None
        self._client: Any | None = None
        self._local = _LocalStore()

    def connect(self) -> str:
        """Probe Hindsight, else fall back to the local keyword store.

        The probe is a cheap recall. A 404 means the server is reachable but the
        bank has not been created yet, so that still counts as connected.
        """
        self.error = None
        try:
            from hindsight_client import Hindsight
        except Exception as exc:  # optional dependency / broken install
            self.error = f"hindsight-client import failed: {type(exc).__name__}: {exc}"
            self.backend = "local"
            return self.backend

        client: Any | None = None
        try:
            client = Hindsight(
                base_url=self.base_url,
                api_key=self.api_key or None,
                timeout=5.0,
                max_attempts=1,
            )
            client.recall(
                bank_id=self.bank_id,
                query="connectivity probe",
                budget="low",
                max_tokens=64,
            )
        except Exception as exc:
            if _is_missing_bank(exc) and client is not None:
                self._client = client
                self.backend = "hindsight"
                return self.backend
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass
            self.error = f"{type(exc).__name__}: {exc}"
            self.backend = "local"
            return self.backend

        self._client = client
        self.backend = "hindsight"
        return self.backend

    def retain(self, content: str, context: str = "", timestamp: str | None = None) -> None:
        """Store one document. Raises on Hindsight errors; the UI catches them."""
        if self.backend == "hindsight" and self._client is not None:
            self._client.retain(
                bank_id=self.bank_id,
                content=content,
                context=context or None,
                timestamp=timestamp,
            )
            return
        self._local.retain(content, context=context, timestamp=timestamp)

    def recall(self, query: str, limit: int = 6) -> list[Memory]:
        """Return the most relevant memories, best first."""
        if self.backend == "hindsight" and self._client is not None:
            response = self._client.recall(
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
        return self._local.recall(query, limit=limit)

    def reflect(self, query: str) -> str:
        """Return a synthesised answer over the bank."""
        if self.backend == "hindsight" and self._client is not None:
            response = self._client.reflect(bank_id=self.bank_id, query=query, budget="mid")
            text = getattr(response, "text", None)
            return str(text) if text else str(response)
        return self._local.reflect(query)

    @property
    def status_label(self) -> str:
        """A short, honest status string for the UI."""
        if self.backend == "hindsight":
            return f"Hindsight connected ({self.base_url}, bank {self.bank_id})"
        return "Local fallback (keyword overlap, in-process)"
