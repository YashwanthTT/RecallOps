"""Streamlit UI for the Incident Memory Agent.

Run with: streamlit run app.py
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from dotenv import load_dotenv

from agent import run_agent
from memory import MemoryStore
from seed_data import (
    DEMO_ALERTS,
    INCIDENTS,
    POLICIES,
    incident_to_document,
    policy_to_document,
)

load_dotenv()


def _load_streamlit_secrets() -> None:
    """Map Streamlit Cloud secrets into env vars for the shared modules."""
    for key in (
        "GROQ_API_KEY",
        "GROQ_BASE_URL",
        "LLM_MODEL",
        "HINDSIGHT_BASE_URL",
        "HINDSIGHT_API_KEY",
        "HINDSIGHT_BANK_ID",
    ):
        if os.getenv(key):
            continue
        try:
            value = st.secrets[key]
        except Exception:
            continue
        if value:
            os.environ[key] = str(value)


_load_streamlit_secrets()

st.set_page_config(
    page_title="Incident Memory Agent — Northwind Pay",
    page_icon="🧠",
    layout="wide",
)

REFLECT_PRESETS = [
    "Which services have recurring failures, and what keeps recurring?",
    "Which remediation actions have repeatedly made things worse?",
    "What should a new on-call engineer know about checkout-api?",
]
CUSTOM = "Custom alert"


@st.cache_resource
def get_store() -> MemoryStore:
    """Create one memory store per Streamlit process and probe the backend."""
    store = MemoryStore()
    store.connect()
    return store


def seed_memories(store: MemoryStore, progress: Any | None = None) -> tuple[int, int, list[str]]:
    """Retain every incident and policy. Returns (documents, incidents, errors)."""
    items: list[tuple[str, str, str]] = []
    for incident in INCIDENTS:
        items.append(
            (
                incident_to_document(incident),
                f"past incident {incident['id']} on {incident['service']}",
                incident["date"],
            )
        )
    for policy in POLICIES:
        items.append((policy_to_document(policy), f"team policy {policy['id']}", policy["date"]))

    errors: list[str] = []
    stored = 0
    for index, (content, context, timestamp) in enumerate(items, 1):
        try:
            store.retain(content, context=context, timestamp=timestamp)
            stored += 1
        except Exception as exc:  # one bad document must not abort the seed
            errors.append(f"{context}: {type(exc).__name__}: {exc}")
        if progress is not None:
            progress.progress(
                index / len(items),
                text=f"Retaining {index}/{len(items)} — {context}",
            )
    return stored, len(INCIDENTS), errors


def outcome_document(
    service: str,
    title: str,
    root_cause: str,
    fixed: str,
    failed: str,
    ttr_minutes: int,
    resolver: str,
) -> tuple[str, str]:
    """Render a just-closed incident as a memory document, with a fresh ID."""
    now = datetime.now(timezone.utc)
    incident_id = f"INC-{now:%y%m%d%H%M%S}"
    failed_items = [part.strip() for part in failed.replace("\n", ";").split(";") if part.strip()]
    failed_block = "\n".join(f"- {item}" for item in failed_items) if failed_items else "- None recorded."
    fixed_one_line = " ".join(fixed.split())
    document = (
        f"Incident ID: {incident_id}\n"
        f"Date: {now.isoformat().replace('+00:00', 'Z')}\n"
        f"Service: {service}\n"
        f"Title: {title}\n"
        f"Symptoms: Reported through the Close the loop form by {resolver}.\n"
        f"Root cause: {root_cause}\n"
        f"Resolution:\n1. {fixed_one_line}\n"
        f"What failed (made it worse):\n{failed_block}\n"
        f"TTR: {ttr_minutes} minutes\n"
        f"Responder: {resolver}"
    )
    return incident_id, document


store = get_store()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("🧠 Incident Memory Agent")
    st.caption("On-call copilot for Northwind Pay. Recalls what your team already survived.")

    if store.backend == "hindsight":
        st.success("Hindsight connected")
        st.caption(f"{store.base_url} · bank `{store.bank_id}`")
    else:
        st.warning("Local fallback active")
        st.caption(
            "Hindsight did not answer, so memories live in this process and are matched by "
            "keyword overlap. Nothing is hidden."
        )
        if store.error:
            st.code(store.error, language="text")

    st.divider()
    seeded_docs = st.session_state.get("seeded_docs", 0)
    seeded_incidents = st.session_state.get("seeded_incidents", 0)
    if st.button(
        "Seed past incidents + policies",
        use_container_width=True,
        type="primary",
        disabled=seeded_docs > 0,
    ):
        progress = st.progress(0.0, text="Starting…")
        stored, incident_count, errors = seed_memories(store, progress)
        st.session_state["seeded_docs"] = stored
        st.session_state["seeded_incidents"] = incident_count
        if errors:
            st.error(f"{len(errors)} document(s) failed. First error: {errors[0]}")
        else:
            st.success(f"Seeded {stored} memories ({incident_count} incidents + {len(POLICIES)} policies).")

    if seeded_docs:
        st.caption("Seeding is disabled for this session to avoid duplicate memories.")
    st.metric("Incidents seeded (session)", seeded_incidents)
    st.caption(f"{seeded_docs} documents retained this session")

    st.divider()
    st.markdown(
        "**How memory works**\n\n"
        "- `retain` stores a resolved incident or policy\n"
        "- `recall` finds the most similar past incidents\n"
        "- `reflect` synthesises an answer across the whole bank"
    )
    if not os.getenv("GROQ_API_KEY", "").strip():
        st.divider()
        st.caption("No `GROQ_API_KEY` set: briefings use the deterministic offline writer. Memory recall is still real.")

# ---------------------------------------------------------------- header
st.title("Incident Memory Agent")
st.markdown(
    "When production breaks, generic runbooks say **restart and scale**. "
    "This agent says *the last two times you did that, the incident got worse* — because it remembers."
)

tab_live, tab_close, tab_reflect = st.tabs(
    ["🚨 Live incident (before vs after)", "✅ Close the loop", "🔎 Reflect"]
)

# ---------------------------------------------------------------- tab 1
with tab_live:
    st.subheader("Simulate an alert")
    preset_names = list(DEMO_ALERTS)
    choice = st.selectbox("Preset alert", preset_names + [CUSTOM])
    is_preset = choice in DEMO_ALERTS
    preset = DEMO_ALERTS[choice] if is_preset else {"service": "", "alert": "", "logs": ""}
    key_suffix = str(preset_names.index(choice)) if is_preset else "custom"

    left, right = st.columns([1, 2])
    with left:
        service = st.text_input("Service", value=preset["service"], key=f"service_{key_suffix}")
    with right:
        alert = st.text_input("Alert", value=preset["alert"], key=f"alert_{key_suffix}")
    logs = st.text_area("Logs", value=preset["logs"], height=180, key=f"logs_{key_suffix}")

    run = st.button("Run incident briefing", type="primary", use_container_width=True)

    if run:
        if not service.strip() or not alert.strip():
            st.error("Service and alert are required.")
        else:
            try:
                with st.spinner("Running the baseline, then recalling history…"):
                    without_memory, _ = run_agent(service, alert, logs, store, use_memory=False)
                    with_memory, memories = run_agent(service, alert, logs, store, use_memory=True)
                st.session_state["last_result"] = {
                    "service": service,
                    "alert": alert,
                    "without": without_memory,
                    "with": with_memory,
                    "memories": memories,
                    "backend": store.backend,
                    "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
                }
            except Exception as exc:
                st.error(f"Briefing failed: {type(exc).__name__}: {exc}")

    result = st.session_state.get("last_result")
    if not result:
        st.info("Pick the checkout-api preset, seed memory in the sidebar, then run the briefing.")
    else:
        st.caption(
            f"{result['service']} · ran {result['at']} · memory backend: {result['backend']} · "
            f"{len(result['memories'])} memories recalled"
        )
        col_without, col_with = st.columns(2, gap="large")
        with col_without:
            st.markdown("### Without memory")
            st.caption("Same model, same prompt, no retrieval. The generic runbook.")
            st.markdown(result["without"])
        with col_with:
            st.markdown("### With Hindsight memory")
            st.caption("Same model, same prompt, plus recalled incidents and policies.")
            st.markdown(result["with"])

        with st.expander(f"Recalled memories ({len(result['memories'])})"):
            if not result["memories"]:
                st.write("No memories were recalled.")
            for index, memory in enumerate(result["memories"], 1):
                st.markdown(f"**Memory {index}** · score `{memory.score:.2f}`")
                st.markdown(memory.text)
                if index < len(result["memories"]):
                    st.divider()

# ---------------------------------------------------------------- tab 2
with tab_close:
    st.subheader("Retain a resolved incident")
    st.caption(
        "Every closed incident becomes a memory. Next time a similar alert fires, the agent recalls "
        "the fix — and the actions that failed."
    )
    services = sorted({incident["service"] for incident in INCIDENTS})
    with st.form("close_loop"):
        close_service = st.selectbox("Service", services)
        close_title = st.text_input("Title", placeholder="Checkout 502s after deploy v4.2.0")
        close_root = st.text_area("Root cause", height=80)
        close_fixed = st.text_area("What fixed it", height=80, placeholder="Rolled back to v4.1.9; restored pool size to 40.")
        close_failed = st.text_area(
            "What did NOT work",
            height=80,
            placeholder="Scaling replicas made DB connections worse; restarting pods did not help.",
        )
        close_ttr = st.number_input("TTR (minutes)", min_value=1, max_value=10000, value=30)
        close_resolver = st.text_input("Resolver", placeholder="Your name")
        submitted = st.form_submit_button("Retain outcome", type="primary")

    if submitted:
        missing = [
            label
            for label, value in (
                ("Title", close_title),
                ("Root cause", close_root),
                ("What fixed it", close_fixed),
                ("Resolver", close_resolver),
            )
            if not value.strip()
        ]
        if missing:
            st.error("Missing required fields: " + ", ".join(missing))
        else:
            incident_id, document = outcome_document(
                close_service,
                close_title.strip(),
                close_root.strip(),
                close_fixed.strip(),
                close_failed.strip(),
                int(close_ttr),
                close_resolver.strip(),
            )
            try:
                store.retain(
                    document,
                    context=f"just-resolved incident {incident_id} on {close_service}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                learned = st.session_state.setdefault("learned", [])
                learned.append(f"{incident_id} — {close_service}: {close_title.strip()}")
                st.success(
                    f"Retained {incident_id}. The next checkout briefing can now cite this resolution."
                )
            except Exception as exc:
                st.error(f"Could not retain the outcome: {type(exc).__name__}: {exc}")

    learned_items = st.session_state.get("learned", [])
    st.markdown("### Learned this session")
    if not learned_items:
        st.caption("Nothing yet. Close an incident above and it appears here.")
    for item in reversed(learned_items):
        st.markdown(f"- {item}")

# ---------------------------------------------------------------- tab 3
with tab_reflect:
    st.subheader("Ask the whole memory bank")
    st.caption(
        "`reflect` reasons across every retained incident and policy, not just the top-k matches. "
        "On the local fallback this is a deterministic synthesis instead of an LLM answer."
    )
    question_choice = st.selectbox("Question", REFLECT_PRESETS + ["Custom question"])
    if question_choice == "Custom question":
        question = st.text_input("Your question", key="custom_reflect")
    else:
        question = question_choice
        st.code(question, language="text")

    reflect_clicked = st.button("Reflect", type="primary", use_container_width=True)
    if reflect_clicked:
        if not question.strip():
            st.error("Enter a question first.")
        else:
            try:
                with st.spinner("Reasoning over the memory bank…"):
                    answer = store.reflect(question)
                st.session_state["reflect_result"] = {
                    "question": question,
                    "answer": answer,
                    "backend": store.backend,
                }
            except Exception as exc:
                st.error(f"Reflect failed: {type(exc).__name__}: {exc}")

    reflect_result = st.session_state.get("reflect_result")
    if reflect_result:
        st.caption(f"Memory backend: {reflect_result['backend']}")
        st.markdown(f"**Q:** {reflect_result['question']}")
        st.markdown(reflect_result["answer"])
    else:
        st.info("Pick a question and press Reflect.")
