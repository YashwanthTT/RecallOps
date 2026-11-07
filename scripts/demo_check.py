"""Small end-to-end check: seed memory, run the agent with and without it.

Run: python demo_check.py

Requires a live Hindsight instance; there is no local fallback. This is the
acceptance test from the hackathon brief, with assertions.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from src.core.agent import run_agent
    from src.core.memory import MemoryStore
    from src.core.seed_data import (
        DEMO_ALERTS,
        INCIDENTS,
        POLICIES,
        incident_to_document,
        policy_to_document,
    )
    from src.integrations.oneuptime import (
        SAMPLE_PAYLOAD,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
    )
except ImportError:
    from agent import run_agent
    from memory import MemoryStore
    from oneuptime import (
        SAMPLE_PAYLOAD,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
    )
    from seed_data import (
        DEMO_ALERTS,
        INCIDENTS,
        POLICIES,
        incident_to_document,
        policy_to_document,
    )


def _check_oneuptime() -> None:
    """The adapter must survive JSON, nested payloads, and pasted text."""
    parsed = parse_oneuptime(json.dumps(SAMPLE_PAYLOAD))
    assert parsed.id == "INC-OU9001", parsed.id
    assert parsed.service == "checkout-api", parsed.service
    assert parsed.ttr_minutes == 26, parsed.ttr_minutes
    document = oneuptime_to_document(parsed)
    assert "Incident ID: INC-OU9001" in document
    assert "What failed (made it worse):" in document

    nested = parse_oneuptime(
        {"data": {"incident": {"title": "Nested", "service": "auth-service", "number": 42}}}
    )
    assert nested.id == "INC-OU42", nested.id
    assert nested.service == "auth-service", nested.service

    pasted = parse_oneuptime(
        "Title: Pasted incident\nService: orders-db\n"
        "Root cause: WAL disk full\nResolution: Drop the inactive slot"
    )
    assert pasted.service == "orders-db", pasted.service
    assert "Drop the inactive slot" in pasted.resolution
    print("OneUptime parser assertions passed.")


def main() -> None:
    _check_oneuptime()
    store = MemoryStore()
    backend = store.connect()
    print(f"Memory backend: {backend}")
    if backend != "hindsight":
        print(f"Hindsight is required: {store.error}")
        sys.exit(1)

    store.configure_bank()
    if store.warning:
        print(f"Bank config: {store.warning}")

    for incident in INCIDENTS:
        store.retain(
            incident_to_document(incident),
            context=f"past incident {incident['id']} on {incident['service']}",
            timestamp=incident["date"],
            document_id=f"incident-{incident['id']}",
            update_mode="replace",
        )
    for policy in POLICIES:
        store.retain(
            policy_to_document(policy),
            context=f"team policy {policy['id']}",
            timestamp=policy["date"],
            document_id=f"policy-{policy['id']}",
            update_mode="replace",
        )
    print(f"Seeded {len(INCIDENTS)} incidents and {len(POLICIES)} policies.\n")

    demo = DEMO_ALERTS["checkout-api 502 spike (connection pool)"]
    without, baseline_memories = run_agent(
        demo["service"], demo["alert"], demo["logs"], store, use_memory=False
    )
    with_memory, memories = run_agent(
        demo["service"], demo["alert"], demo["logs"], store, use_memory=True
    )

    print("=" * 78)
    print("WITHOUT MEMORY")
    print("=" * 78)
    print(without)
    print()
    print("=" * 78)
    print(f"WITH HINDSIGHT MEMORY ({len(memories)} recalled)")
    print("=" * 78)
    print(with_memory)

    assert baseline_memories == [], "baseline must not query memory"
    assert "INC-2041" not in without, "baseline must not cite incident IDs"
    assert "INC-2041" in with_memory, "memory briefing must cite INC-2041"
    assert "INC-2139" in with_memory, "memory briefing must cite INC-2139"
    assert "restart" in with_memory.lower(), "memory briefing must warn about restarts"
    assert "scal" in with_memory.lower(), "memory briefing must warn about scaling"
    assert "rollback" in with_memory.lower(), "memory briefing must mention rollback"
    print("\nAll assertions passed.")
    store.close()


if __name__ == "__main__":
    main()
