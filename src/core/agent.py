"""The incident-response agent.

``run_agent`` builds the same prompt whether or not memory is enabled. The only
difference is the recalled-memory block. Memory always comes from Hindsight; if
Hindsight is unavailable the memory-enabled run fails loudly instead of
inventing a local store. If no ``GROQ_API_KEY`` is present, or the LLM call
fails, a deterministic writer still assembles the briefing from the memories
Hindsight recalled.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

try:
    from src.core.memory import Memory, MemoryStore
except ImportError:
    from memory import Memory, MemoryStore

DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"

SYSTEM_PROMPT = """You are Incident Memory Agent, an on-call incident-response copilot for Northwind Pay (a fictional company).

Your job: turn a production alert plus retrieved memories of past incidents and team policies into a briefing that helps an on-call engineer act in the next five minutes.

Output Markdown with exactly these five bold section labels, in this order:
**Likely root cause — <high|medium|low> confidence**
One short paragraph. If the memory contains a close match, name the pattern. If not, say the cause is unknown; do not pretend.
**Matching past incidents**
Bullets: incident ID, date, title, and why it matches. Cite ONLY incident IDs that appear verbatim in RETRIEVED MEMORY. If none, write "None in memory." and say so honestly.
**Do first**
At most 4 numbered steps. Include the exact commands or flags memory provides. Safest action first.
**Do NOT do**
Bullets of actions that made past incidents worse, each with its incident ID and consequence. If memory has none, write "No documented harmful actions; proceed carefully." Never invent one.
**Escalate**
Who to page, which channel, and any time-bound policy from memory.

Rules:
- If RETRIEVED MEMORY is missing, empty, or says retrieval failed: give a generic runbook and state plainly that no incident history was available. Do not cite any incident ID.
- Never invent an incident ID, command, policy, responder, or metric. Use only the alert and retrieved memory.
- Every command in **Do first** must appear verbatim in RETRIEVED MEMORY. Do not invent, adapt, or extrapolate a command (no new kubectl scale/restart/rollout variants). If memory has no command for a step, describe the check in words and omit the command.
- Do not recommend scaling up or down unless a retrieved memory recommends that exact direction. "Scaling up made it worse" does not justify scaling down.
- Never recommend an action that RETRIEVED MEMORY says made things worse.
- Be concise. No preamble, no closing summary, no tables.
"""


@dataclass
class ParsedIncident:
    """Fields parsed out of one retained incident document."""

    id: str
    service: str = ""
    title: str = ""
    date: str = ""
    root_cause: str = ""
    steps: list[str] = field(default_factory=list)
    what_failed: list[str] = field(default_factory=list)
    ttr_minutes: str = ""
    responder: str = ""


def _field(text: str, label: str) -> str:
    match = re.search(rf"^{re.escape(label)}:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _numbered_block(text: str, label: str) -> list[str]:
    match = re.search(
        rf"^{re.escape(label)}:\s*\n((?:(?:\d+\. ).*\n?)+)",
        text,
        re.MULTILINE,
    )
    if not match:
        return []
    return [
        re.sub(r"^\d+\.\s*", "", line).strip()
        for line in match.group(1).splitlines()
        if line.strip()
    ]


def _bullet_block(text: str, label: str) -> list[str]:
    match = re.search(
        rf"^{re.escape(label)}:\s*\n((?:(?:- ).*\n?)+)",
        text,
        re.MULTILINE,
    )
    if not match:
        return []
    return [
        re.sub(r"^-\s*", "", line).strip()
        for line in match.group(1).splitlines()
        if line.strip()
    ]


def parse_incident(text: str) -> ParsedIncident | None:
    """Parse a memory document. Returns None for policies or free text."""
    incident_id = _field(text, "Incident ID")
    if not incident_id:
        # Hindsight may return an extracted fact plus the stored context.
        match = re.search(r"\b(INC-[A-Z0-9-]+)\b", text)
        incident_id = match.group(1) if match else ""
    if not re.fullmatch(r"INC-[A-Z0-9-]+", incident_id or ""):
        return None
    service = _field(text, "Service")
    if not service:
        match = re.search(rf"incident {re.escape(incident_id)} on ([\w-]+)", text)
        service = match.group(1) if match else ""
    title = _field(text, "Title") or "Recalled incident"
    return ParsedIncident(
        id=incident_id,
        service=service,
        title=title,
        date=_field(text, "Date"),
        root_cause=_field(text, "Root cause"),
        steps=_numbered_block(text, "Resolution"),
        what_failed=_bullet_block(text, "What failed (made it worse)"),
        ttr_minutes=_field(text, "TTR").replace(" minutes", ""),
        responder=_field(text, "Responder"),
    )


def _policies(memories: list[Memory]) -> list[tuple[str, str]]:
    policies: list[tuple[str, str]] = []
    for memory in memories:
        policy_id = _field(memory.text, "Policy ID")
        policy_text = _field(memory.text, "Team policy")
        if policy_id and policy_text:
            policies.append((policy_id, policy_text))
    return policies


def _dedupe_incidents(memories: list[Memory]) -> list[ParsedIncident]:
    seen: set[str] = set()
    incidents: list[ParsedIncident] = []
    for memory in memories:
        incident = parse_incident(memory.text)
        if incident and incident.id not in seen:
            seen.add(incident.id)
            incidents.append(incident)
    return incidents


def _slug(service: str) -> str:
    return re.sub(r"[^a-z0-9-]", "", service.lower()) or "service"


def _generic_briefing(service: str, reason: str) -> str:
    """Generic runbook used for the no-memory baseline and failed recall."""
    slug = _slug(service)
    return f"""**Likely root cause — low confidence**
Unknown. {reason} This is a generic runbook based only on the alert text, not on Northwind Pay history.

**Matching past incidents**
None in memory. I cannot cite an incident ID because no incident history was available.

**Do first**
1. Restart the affected pods: `kubectl rollout restart deploy/{slug}`.
2. Scale the service up: `kubectl scale deploy/{slug} --replicas=20`.
3. Check whether a deploy landed in the last hour: `kubectl rollout history deploy/{slug}`.
4. Page the {service} on-call and open `#inc-{slug}`.

**Do NOT do**
No documented harmful actions. Memory was not available, so there is no evidence about what made this worse before.

**Escalate**
Page the {service} on-call via PagerDuty and open `#inc-{slug}`. No historical escalation policy was retrieved.
"""


def _deterministic_briefing(
    service: str,
    memories: list[Memory],
    *,
    memory_requested: bool,
) -> str:
    """Build a grounded briefing from Hindsight memories without an LLM."""
    if not memory_requested:
        return _generic_briefing(
            service, "Memory was not consulted for this run (baseline mode)."
        )
    if not memories:
        return _generic_briefing(
            service,
            "Hindsight returned no relevant memories for this service and alert.",
        )

    incidents = _dedupe_incidents(memories)
    if not incidents:
        return _generic_briefing(
            service, "Memory contained policies but no matching past incidents."
        )

    top = incidents[0]
    same_service_incidents = [
        incident for incident in incidents if incident.service == top.service
    ]
    confidence = "high" if len(same_service_incidents) >= 2 else "medium"
    if not top.root_cause:
        confidence = "low"

    root = f"Closest learned pattern is **{top.id}** ({top.title}). "
    if top.root_cause:
        root += f"Its root cause was: {top.root_cause}"
    else:
        root += "The stored memory does not include a root-cause field."

    match_lines = []
    matching = (
        same_service_incidents[:4]
        if len(same_service_incidents) >= 2
        else incidents[:4]
    )
    for incident in matching:
        ttr = f" · TTR {incident.ttr_minutes}m" if incident.ttr_minutes else ""
        match_lines.append(
            f"- **{incident.id}** ({incident.date[:10]}, {incident.service}) — {incident.title}{ttr}"
        )

    do_lines = [f"{i}. {step}" for i, step in enumerate(top.steps[:4], 1)]
    if not do_lines:
        do_lines = [
            "1. Inspect the service logs and recent deploys; no step-by-step resolution was stored."
        ]

    avoid_lines = [f"- **{top.id}**: {action}" for action in top.what_failed[:4]]
    if not avoid_lines:
        avoid_lines = [
            "- No documented harmful actions for this pattern; proceed carefully."
        ]

    escalation: list[str] = []
    for policy_id, policy_text in _policies(memories):
        for sentence in re.split(r"(?<=[.!?])\s+", policy_text):
            if re.search(r"\b(page|escalat|rollback)\b", sentence, re.IGNORECASE):
                escalation.append(f"- {sentence} ({policy_id})")
    if not escalation:
        escalation = [f"- Page the {service} on-call and open `#inc-{_slug(service)}`."]
    if top.responder:
        escalation.append(
            f"- Closest past responder: **{top.responder}** ({top.id}, resolved in {top.ttr_minutes or '?'} min)."
        )

    footer = (
        f"\n\n---\n*Deterministic briefing (no LLM key or LLM error). "
        f"{len(memories)} {'memory' if len(memories) == 1 else 'memories'} recalled "
        "via Hindsight; answer grounded only in those memories.*"
    )
    return f"""**Likely root cause — {confidence} confidence**
{root}

**Matching past incidents**
{chr(10).join(match_lines)}

**Do first**
{chr(10).join(do_lines)}

**Do NOT do**
{chr(10).join(avoid_lines)}

**Escalate**
{chr(10).join(escalation)}{footer}
"""


def _memory_block(memories: list[Memory]) -> str:
    if not memories:
        return "RETRIEVED MEMORY: empty. No relevant past incidents or policies were found."
    documents = "\n\n".join(
        f"[memory {i}]\n{memory.text}" for i, memory in enumerate(memories, 1)
    )
    return f"RETRIEVED MEMORY (from Hindsight):\n\n{documents}"


def _normalize_citations(text: str) -> str:
    """Use ASCII hyphens in incident/policy IDs for copy-paste and assertions.

    Groq sometimes emits U+2011 non-breaking hyphens inside bold Markdown.
    """
    return re.sub(r"\b(INC|POL)[\u2010-\u2015\u2212]", r"\1-", text)


def _verbatim_steps(memories: list[Memory], max_incidents: int = 3) -> str:
    """Expose the stored resolution steps, including exact commands.

    Hindsight recall returns compact facts; the full command often lives in the
    source document's resolution list. Giving the LLM those steps verbatim stops
    it from inventing a plausible-looking kubectl/deploy command.
    """
    incidents = _dedupe_incidents(memories)[:max_incidents]
    if not incidents:
        return ""
    lines = ["VERBATIM RESOLUTION STEPS FROM RETRIEVED MEMORY (copy commands exactly):"]
    for incident in incidents:
        lines.append(f"\n{incident.id} — {incident.title}")
        if not incident.steps:
            lines.append("(no resolution steps stored)")
            continue
        for index, step in enumerate(incident.steps, 1):
            lines.append(f"{index}. {step}")
    return "\n".join(lines)


def run_agent(
    service: str,
    alert: str,
    logs: str,
    store: MemoryStore,
    use_memory: bool,
) -> tuple[str, list[Memory]]:
    """Produce one incident briefing.

    Args:
        service: Service name, e.g. ``checkout-api``.
        alert: Alert text.
        logs: Raw log excerpt.
        store: A connected :class:`MemoryStore`.
        use_memory: When false, memory is never queried (the baseline run).

    Returns:
        ``(markdown, memories_used)``. ``memories_used`` is empty for the
        baseline run. LLM failures degrade to a deterministic briefing; a
        Hindsight recall failure raises so the app never fakes memory.
    """
    memories: list[Memory] = []
    if use_memory:
        query = f"service: {service}\nalert: {alert}\nlogs: {logs[:3000]}"
        # Hindsight is the only memory backend; a failure here must be visible.
        # Hindsight returns several facts per incident; 10 leaves room for the
        # exact historical match after near-duplicate facts are ranked.
        memories = store.recall(query, limit=10)

        try:
            # Policies are short and often lose a top-k race to incident logs.
            # A second, policy-focused recall makes escalation rules explicit.
            policy_memories = store.recall(
                f"team policy escalation page on-call rollback for {service}; "
                f"payments error rate 5%. Alert: {alert[:200]}",
                limit=4,
            )
            seen = {memory.text for memory in memories}
            memories.extend(
                memory for memory in policy_memories if memory.text not in seen
            )
        except Exception:
            # Policy recall is a bonus; keep the incident memories we already have.
            pass

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return (
            _deterministic_briefing(
                service,
                memories,
                memory_requested=use_memory,
            ),
            memories,
        )

    user_parts = [f"SERVICE: {service}", f"ALERT: {alert}", f"LOGS:\n{logs}"]
    if use_memory:
        user_parts.append(_memory_block(memories))
        if memories:
            exact = _verbatim_steps(memories)
            if exact:
                user_parts.append(exact)
    else:
        user_parts.append(
            "RETRIEVED MEMORY: none (memory disabled for this baseline run)."
        )

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=os.getenv("GROQ_BASE_URL") or DEFAULT_BASE_URL,
        )
        response = client.chat.completions.create(
            model=os.getenv("LLM_MODEL") or DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "\n\n".join(user_parts)},
            ],
            temperature=0.2,
            max_tokens=2500,
        )
        content = (response.choices[0].message.content or "").strip()
        if not content:
            raise ValueError("LLM returned an empty response")
        return _normalize_citations(content), memories
    except Exception as exc:
        # Covers auth errors, rate limits, timeouts, and malformed tool calls.
        note = (
            f"> **LLM unavailable:** `{type(exc).__name__}: {exc}`. "
            "Showing the deterministic briefing instead. Hindsight recall still ran.\n\n"
        )
        return (
            note
            + _deterministic_briefing(
                service,
                memories,
                memory_requested=use_memory,
            ),
            memories,
        )
