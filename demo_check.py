"""Small end-to-end check: seed memory, run the agent with and without it.

Run: python demo_check.py

Uses the local fallback when Hindsight is not running. This is the acceptance
test from the hackathon brief, with assertions.
"""

from __future__ import annotations

from agent import run_agent
from memory import MemoryStore
from seed_data import (
    DEMO_ALERTS,
    INCIDENTS,
    POLICIES,
    incident_to_document,
    policy_to_document,
)


def main() -> None:
    store = MemoryStore()
    backend = store.connect()
    print(f"Memory backend: {backend}")
    if store.error:
        print(f"Fallback reason: {store.error}")

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
