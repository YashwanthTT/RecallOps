"""Streamlit UI for the Incident Memory Agent.

Run with: streamlit run app.py
"""

from __future__ import annotations

import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import streamlit as st
from dotenv import load_dotenv

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
        SIMULATED_SCENARIOS,
        OneUptimeClient,
        OneUptimeIncident,
        ProbeResult,
        create_incident_from_probe,
        create_incident_from_scenario,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
        probe_endpoint,
    )
except ImportError:
    from agent import run_agent
    from memory import MemoryStore
    from oneuptime import (
        SAMPLE_PAYLOAD,
        SIMULATED_SCENARIOS,
        OneUptimeClient,
        OneUptimeIncident,
        ProbeResult,
        create_incident_from_probe,
        create_incident_from_scenario,
        incident_to_document as oneuptime_to_document,
        parse_oneuptime,
        probe_endpoint,
    )
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
    items: list[tuple[str, str, str, str]] = []
    for incident in INCIDENTS:
        items.append(
            (
                incident_to_document(incident),
                f"past incident {incident['id']} on {incident['service']}",
                incident["date"],
                f"incident-{incident['id']}",
            )
        )
    for policy in POLICIES:
        items.append(
            (
                policy_to_document(policy),
                f"team policy {policy['id']}",
                policy["date"],
                f"policy-{policy['id']}",
            )
        )

    errors: list[str] = []
    stored = 0
    store.configure_bank()
    for index, (content, context, timestamp, document_id) in enumerate(items, 1):
        try:
            store.retain(
                content,
                context=context,
                timestamp=timestamp,
                document_id=document_id,
                update_mode="replace",
            )
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

tab_live, tab_monitor, tab_oneuptime, tab_close, tab_reflect, tab_blueprint = st.tabs(
    [
        "🚨 Live incident (before vs after)",
        "🛰 OneUptime Service Monitor & Lab",
        "📥 OneUptime intake & review",
        "✅ Close the loop",
        "🔎 Reflect",
        "🔌 Real-World Integration Blueprint",
    ]
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

# ---------------------------------------------------------------- tab: OneUptime Monitor & Lab
with tab_monitor:
    st.subheader("🛰 OneUptime Service Monitor & Outage Lab")
    st.markdown(
        "OneUptime acts as the **monitoring layer** (synthetic checks, pinging APIs, declaring outages). "
        "Your **Hindsight agent** acts as the **memory layer** next to it (recalling past fixes and warning against actions that made things worse)."
    )

    # Top Service Status Bar
    active_outage: OneUptimeIncident | None = st.session_state.get("active_outage")

    st.markdown("### Service Health Dashboard (OneUptime Monitors)")
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)

    def get_svc_state(svc_name: str, default_p95: str) -> tuple[str, str]:
        if active_outage and active_outage.service == svc_name:
            return "🔴 CRITICAL OUTAGE", "Outage Active (5xx)"
        return "🟢 OPERATIONAL", f"p95: {default_p95}"

    s1_status, s1_metric = get_svc_state("checkout-api", "185ms")
    s2_status, s2_metric = get_svc_state("payment-gateway", "320ms")
    s3_status, s3_metric = get_svc_state("auth-service", "42ms")
    s4_status, s4_metric = get_svc_state("orders-db", "12ms")

    with col_m1:
        st.metric("checkout-api", s1_status, s1_metric)
        st.caption("HTTP /v1/checkout · Port 8080")
    with col_m2:
        st.metric("payment-gateway", s2_status, s2_metric)
        st.caption("HTTP /charges · Port 8443")
    with col_m3:
        st.metric("auth-service", s3_status, s3_metric)
        st.caption("HTTP /v1/validate · Port 8081")
    with col_m4:
        st.metric("orders-db", s4_status, s4_metric)
        st.caption("TCP Port 5432 · Connection Pool")

    st.divider()

    col_break, col_probe = st.columns(2, gap="large")

    with col_break:
        st.markdown("#### 💥 1. Break a Service on Purpose (Chaos Lab)")
        st.caption("Trigger an outage to see OneUptime open an incident and feed Hindsight:")
        scenario_keys = list(SIMULATED_SCENARIOS.keys())
        scenario_labels = {
            "checkout-pool-exhaustion": "checkout-api: Pool Exhaustion after v3.4.1 (502/504 spike)",
            "payment-gateway-timeout": "payment-gateway: Acquirer Timeout & Circuit Breaker Trip (504)",
            "auth-cache-eviction": "auth-service: Redis Token Cache Eviction Storm (500 spike)",
            "orders-db-disk-pressure": "orders-db: Postgres IOPS Saturation & Connection Pool Full",
        }
        chosen_scenario = st.selectbox(
            "Select outage scenario",
            scenario_keys,
            format_func=lambda k: scenario_labels.get(k, k),
            key="monitor_scenario_select",
        )

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("💥 Break Service (Trigger Outage)", type="primary", use_container_width=True, key="btn_trigger_outage"):
                st.session_state["active_outage"] = create_incident_from_scenario(chosen_scenario)
                st.session_state["outage_briefing"] = None
                st.rerun()
        with col_b2:
            if st.button("🔄 Recover All Services", use_container_width=True, key="btn_recover_services"):
                st.session_state["active_outage"] = None
                st.session_state["outage_briefing"] = None
                st.rerun()

    with col_probe:
        st.markdown("#### ⚡ 2. Probe ANY Real-World URL")
        st.caption("OneUptime HTTP Synthetic Monitor — test any real external API, website, or localhost microservice:")

        # Presets for instant video demo
        col_preset1, col_preset2 = st.columns(2)
        with col_preset1:
            if st.button("📦 Local checkout-api (:8080)", use_container_width=True, key="btn_preset_local"):
                st.session_state["monitor_probe_url"] = "http://localhost:8080/health"
                st.session_state["monitor_probe_svc"] = "checkout-api"
                st.rerun()
        with col_preset2:
            if st.button("🌐 Public HTTPBin API", use_container_width=True, key="btn_preset_httpbin"):
                st.session_state["monitor_probe_url"] = "https://httpbin.org/status/200"
                st.session_state["monitor_probe_svc"] = "public-api"
                st.rerun()

        default_url = st.session_state.get("monitor_probe_url", "http://localhost:8080/health")
        default_svc = st.session_state.get("monitor_probe_svc", "checkout-api")

        probe_url = st.text_input("Target URL to monitor", value=default_url, placeholder="https://api.yourcompany.com/health", key="monitor_probe_url_input")
        probe_svc = st.text_input("Service Label", value=default_svc, key="monitor_probe_svc_input")

        if st.button("⚡ Probe Endpoint Now", use_container_width=True, key="btn_probe_now"):
            with st.spinner(f"Probing {probe_url}…"):
                probe_res = probe_endpoint(probe_url, timeout=4.0, service=probe_svc)
                st.session_state["last_probe"] = probe_res

        last_probe: ProbeResult | None = st.session_state.get("last_probe")
        if last_probe:
            if last_probe.healthy:
                st.success(f"🟢 **{last_probe.url}** is Operational! Status: HTTP {last_probe.status_code} · Latency: {last_probe.latency_ms} ms")
            else:
                st.error(f"🔴 **{last_probe.url}** is DOWN! Status: HTTP {last_probe.status_code} · {last_probe.error}")
                if st.button("🚨 Declare OneUptime Incident from Probe Failure", type="primary", key="btn_declare_probe_inc"):
                    st.session_state["active_outage"] = create_incident_from_probe(last_probe)
                    st.session_state["outage_briefing"] = None
                    st.rerun()

    # Active Outage War Room
    if active_outage:
        st.divider()
        st.error(f"🚨 **ACTIVE ONEUPTIME INCIDENT:** `{active_outage.id}` — {active_outage.title}")
        st.caption(f"Service: `{active_outage.service}` · Severity: `{active_outage.severity}` · Status: `{active_outage.status}`")

        with st.expander("Telemetry & Error Logs Captured by OneUptime", expanded=True):
            st.code(active_outage.symptoms, language="text")

        col_act1, col_act2 = st.columns(2)
        with col_act1:
            run_copilot = st.button("🧠 Investigate Outage with Hindsight Copilot", type="primary", use_container_width=True, key="btn_copilot_investigate")
        with col_act2:
            resolve_now = st.button("✅ Resolve Outage & Retain Post-Mortem in Memory", use_container_width=True, key="btn_resolve_outage")

        if run_copilot:
            with st.spinner("OneUptime alert dispatched to Hindsight. Recalling team memory…"):
                without_outage, _ = run_agent(
                    active_outage.service, active_outage.title, active_outage.symptoms, store, use_memory=False
                )
                with_outage, outage_memories = run_agent(
                    active_outage.service, active_outage.title, active_outage.symptoms, store, use_memory=True
                )
                st.session_state["outage_briefing"] = {
                    "without": without_outage,
                    "with": with_outage,
                    "memories": outage_memories,
                }

        outage_briefing = st.session_state.get("outage_briefing")
        if outage_briefing:
            st.markdown("### 📋 Memory-Guided Incident Briefing (Before vs After)")
            col_b_without, col_b_with = st.columns(2, gap="large")
            with col_b_without:
                st.markdown("#### Without Memory (Generic Runbook)")
                st.caption("Blind suggestions from standard alert text:")
                st.markdown(outage_briefing["without"])
            with col_b_with:
                st.markdown("#### With Hindsight Memory (Proven Actions)")
                st.caption(f"Grounded in {len(outage_briefing['memories'])} past incidents & team policies:")
                st.markdown(outage_briefing["with"])

        if resolve_now:
            try:
                store.retain(
                    oneuptime_to_document(active_outage),
                    context=f"OneUptime incident {active_outage.id} resolved on {active_outage.service}",
                    timestamp=active_outage.date,
                    document_id=f"oneuptime-{active_outage.id}",
                    update_mode="replace",
                )
                st.success(f"Incident {active_outage.id} marked RESOLVED! Root cause and lessons learned retained in Hindsight.")
                st.session_state["active_outage"] = None
                st.session_state["outage_briefing"] = None
                st.rerun()
            except Exception as exc:
                st.error(f"Failed to retain resolution: {exc}")

# ---------------------------------------------------------------- tab 1c
with tab_oneuptime:
    st.subheader("Bring a real OneUptime incident into memory")
    st.caption(
        "OneUptime has no stable public incident webhook/API documented. This tab accepts an "
        "export or a Workflows API Post payload, then retains it in the same Hindsight bank "
        "the live briefing uses. Nothing is called live."
    )
    if st.button("Load sample OneUptime payload", use_container_width=True):
        st.session_state["ou_raw"] = json.dumps(SAMPLE_PAYLOAD, indent=2)
        st.rerun()
    raw = st.text_area(
        "OneUptime incident JSON or text",
        key="ou_raw",
        height=220,
        placeholder=(
            '{"title": "Checkout 5xx", "service": "checkout-api", '
            '"rootCause": "...", "resolution": "..."}'
        ),
    )
    st.caption("Plain text with `Title:`, `Service:`, `Root cause:`, `Resolution:` lines also works.")
    if st.button("Parse incident", type="primary"):
        try:
            parsed = parse_oneuptime(raw)
            st.session_state["ou_parsed"] = parsed
            st.success(f"Parsed {parsed.id} — {parsed.service}: {parsed.title}")
        except Exception as exc:
            st.error(f"Could not parse that payload: {type(exc).__name__}: {exc}")

    parsed = st.session_state.get("ou_parsed")
    if parsed:
        st.markdown("### Review before retaining")
        st.caption(f"Normalized ID `{parsed.id}` · OneUptime ID `{parsed.oneuptime_id or 'unknown'}`")
        with st.form(f"oneuptime_form_{parsed.id}"):
            field_left, field_right = st.columns(2)
            with field_left:
                ou_title = st.text_input("Title", value=parsed.title, key=f"ou_title_{parsed.id}")
                ou_service = st.text_input("Service", value=parsed.service, key=f"ou_service_{parsed.id}")
                ou_severity = st.text_input("Severity", value=parsed.severity, key=f"ou_severity_{parsed.id}")
                ou_status = st.text_input("Status", value=parsed.status, key=f"ou_status_{parsed.id}")
            with field_right:
                ou_ttr = st.number_input(
                    "TTR (minutes)",
                    min_value=0,
                    max_value=100000,
                    value=int(parsed.ttr_minutes),
                    step=1,
                    key=f"ou_ttr_{parsed.id}",
                )
                ou_responder = st.text_input(
                    "Responder", value=parsed.responder, key=f"ou_responder_{parsed.id}"
                )
                ou_url = st.text_input("OneUptime URL", value=parsed.url, key=f"ou_url_{parsed.id}")
            ou_root = st.text_area(
                "Root cause", value=parsed.root_cause, height=80, key=f"ou_root_{parsed.id}"
            )
            ou_resolution = st.text_area(
                "Resolution / remediation",
                value=parsed.resolution,
                height=100,
                key=f"ou_resolution_{parsed.id}",
            )
            ou_failed = st.text_area(
                "What failed (made it worse)",
                value=parsed.what_failed,
                height=80,
                key=f"ou_failed_{parsed.id}",
            )
            ou_symptoms = st.text_area(
                "Symptoms / logs",
                value=parsed.symptoms,
                height=150,
                key=f"ou_symptoms_{parsed.id}",
            )
            run_after = st.checkbox(
                "Run a before/after briefing after retaining",
                value=True,
                key=f"ou_run_after_{parsed.id}",
            )
            submitted = st.form_submit_button("Retain in Hindsight", type="primary")

        if submitted:
            missing = [
                label
                for label, value in (
                    ("Title", ou_title),
                    ("Service", ou_service),
                    ("Root cause", ou_root),
                    ("Resolution", ou_resolution),
                )
                if not value.strip()
            ]
            if missing:
                st.error("Missing required fields: " + ", ".join(missing))
            else:
                final = replace(
                    parsed,
                    title=ou_title.strip(),
                    service=ou_service.strip(),
                    severity=ou_severity.strip(),
                    status=ou_status.strip(),
                    root_cause=ou_root.strip(),
                    resolution=ou_resolution.strip(),
                    what_failed=ou_failed.strip(),
                    symptoms=ou_symptoms.strip(),
                    ttr_minutes=int(ou_ttr),
                    responder=ou_responder.strip(),
                    url=ou_url.strip(),
                )
                try:
                    store.retain(
                        oneuptime_to_document(final),
                        context=(
                            f"OneUptime incident {final.id} "
                            f"(OneUptime ID {final.oneuptime_id or 'unknown'}) on {final.service}"
                        ),
                        timestamp=final.date,
                        document_id=f"oneuptime-{final.id}",
                        update_mode="replace",
                    )
                    learned = st.session_state.setdefault("learned", [])
                    learned.append(f"{final.id} — {final.service}: {final.title}")
                    st.success(
                        f"Retained {final.id}. A future {final.service} alert can now cite it."
                    )
                    if run_after:
                        with st.spinner("Running the baseline, then recalling the new memory…"):
                            without, _ = run_agent(
                                final.service,
                                final.title,
                                final.symptoms,
                                store,
                                use_memory=False,
                            )
                            with_memory, memories = run_agent(
                                final.service,
                                final.title,
                                final.symptoms,
                                store,
                                use_memory=True,
                            )
                        st.session_state["last_result"] = {
                            "service": final.service,
                            "alert": final.title,
                            "without": without,
                            "with": with_memory,
                            "memories": memories,
                            "backend": store.backend,
                            "at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ"),
                        }
                        st.markdown("### With Hindsight memory")
                        st.caption(
                            f"{len(memories)} memories recalled · backend: {store.backend}. "
                            "The Live incident tab now shows the full before/after."
                        )
                        st.markdown(with_memory)
                except Exception as exc:
                    st.error(f"Could not retain the OneUptime incident: {type(exc).__name__}: {exc}")

    with st.expander("Receive incidents from OneUptime Workflows (webhook)"):
        st.markdown(
            "Start the receiver in a separate terminal, then use **Workflows → On Create Incident "
            "→ API Post (JSON)** in OneUptime and point it at the URL below."
        )
        st.code("uv run python src/integrations/webhook_server.py", language="bash")
        st.code(
            "curl -sS -X POST http://127.0.0.1:8787/oneuptime \\\n"
            "  -H 'Content-Type: application/json' \\\n"
            "  --data @incident.json",
            language="bash",
        )
        st.markdown(
            "Accepted keys include `title`, `description`, `service`, `severity`, `status`, "
            "`rootCause`, `resolution`, `whatFailed`, `assignedTo`, `createdAt`, `resolvedAt`, "
            "`ttr`, `logs`, and `url`. Nested `incident`/`data` payloads are unwrapped."
        )
        st.caption(
            "The receiver binds to 127.0.0.1 by default and requires no token unless "
            "`ONEUPTIME_WEBHOOK_TOKEN` is set. Put it behind HTTPS and authentication before "
            "exposing it beyond your machine."
        )

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

# ---------------------------------------------------------------- tab 5: Real-World Integration Blueprint
with tab_blueprint:
    st.subheader("🔌 Real-World Integration Blueprint")
    st.markdown(
        "Here is the complete guide to integrating your **Hindsight Memory Agent** with **OneUptime** "
        "and your real-world production web applications."
    )

    st.markdown("### 1. How to Run OneUptime Locally or on a Server")
    st.markdown(
        "OneUptime is an open-source observability, incident management, and status page platform. "
        "You can run it on Linux or macOS using Docker Compose:"
    )
    st.code(
        "# Clone the OneUptime repository\n"
        "git clone --depth 1 --single-branch --branch release https://github.com/OneUptime/oneuptime.git\n"
        "cd oneuptime\n\n"
        "# Create your configuration file\n"
        "cp config.example.env config.env\n\n"
        "# Start OneUptime (pulls images and boots services)\n"
        "npm start\n"
        "# Alternatively: docker compose -f docker-compose.yml up -d",
        language="bash",
    )
    st.caption("Once running, visit `http://localhost`. Create an admin account and add your project.")

    st.divider()

    st.markdown("### 2. Configure OneUptime Workflows to Alert Hindsight")
    st.markdown(
        "OneUptime Workflows trigger whenever an incident occurs. Point OneUptime to your Hindsight receiver:"
    )
    st.markdown(
        "1. Open OneUptime UI → **Workflows** → **New Workflow** (name it `Hindsight AI Triage`).\n"
        "2. Add Trigger: **On Incident Created**.\n"
        "3. Add Action Component: **API Post (JSON)**.\n"
        "4. Set URL to: `http://<your-agent-ip>:8787/oneuptime/briefing`\n"
        "5. Fill the JSON request body:"
    )
    st.code(
        json.dumps(
            {
                "id": "{{incident.id}}",
                "number": "{{incident.incidentNumber}}",
                "title": "{{incident.title}}",
                "description": "{{incident.description}}",
                "service": "{{incident.service.name}}",
                "severity": "{{incident.incidentSeverity.name}}",
                "status": "{{incident.currentIncidentState.name}}",
                "createdAt": "{{incident.createdAt}}",
                "logs": "{{incident.logs}}",
                "brief": True,
            },
            indent=2,
        ),
        language="json",
    )

    st.divider()

    st.markdown("### 3. Instrument Real-World Applications with Health Endpoints")
    st.markdown("Add a `/health` endpoint to your application so OneUptime can monitor it via synthetic HTTP probes:")

    code_tabs = st.tabs(["Node.js (Express)", "Python (FastAPI)", "Go (net/http)", "Kubernetes Probes"])
    with code_tabs[0]:
        st.code(
            "// Express.js health endpoint\n"
            "const express = require('express');\n"
            "const app = express();\n\n"
            "app.get('/health', async (req, res) => {\n"
            "  try {\n"
            "    const dbOk = await checkDatabasePool();\n"
            "    if (!dbOk) {\n"
            "      return res.status(503).json({ status: 'DEGRADED', reason: 'DB pool exhausted' });\n"
            "    }\n"
            "    res.status(200).json({ status: 'UP', timestamp: new Date().toISOString() });\n"
            "  } catch (err) {\n"
            "    res.status(500).json({ status: 'DOWN', error: err.message });\n"
            "  }\n"
            "});\n"
            "app.listen(8080);",
            language="javascript",
        )
    with code_tabs[1]:
        st.code(
            "# FastAPI health endpoint\n"
            "from fastapi import FastAPI, Response, status\n"
            "import datetime\n\n"
            "app = FastAPI()\n\n"
            "@app.get('/health')\n"
            "def health_check(response: Response):\n"
            "    db_healthy = check_db_connection_pool()\n"
            "    if not db_healthy:\n"
            "        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE\n"
            "        return {'status': 'DOWN', 'error': 'Hikari pool timeout'}\n"
            "    return {'status': 'UP', 'time': datetime.datetime.utcnow().isoformat()}",
            language="python",
        )
    with code_tabs[2]:
        st.code(
            "// Go HTTP health endpoint\n"
            "package main\n\n"
            "import (\n"
            "    \"net/http\"\n"
            ")\n\n"
            "func healthHandler(w http.ResponseWriter, r *http.Request) {\n"
            "    if err := checkHealth(); err != nil {\n"
            "        http.Error(w, `{\"status\":\"DOWN\"}`, http.StatusServiceUnavailable)\n"
            "        return\n"
            "    }\n"
            "    w.Header().Set(\"Content-Type\", \"application/json\")\n"
            "    w.WriteHeader(http.StatusOK)\n"
            "    w.Write([]byte(`{\"status\":\"UP\"}`))\n"
            "}",
            language="go",
        )
    with code_tabs[3]:
        st.code(
            "# Kubernetes liveness & readiness probe configuration\n"
            "apiVersion: apps/v1\n"
            "kind: Deployment\n"
            "metadata:\n"
            "  name: checkout-api\n"
            "spec:\n"
            "  template:\n"
            "    spec:\n"
            "      containers:\n"
            "      - name: checkout-api\n"
            "        image: myregistry/checkout-api:v3.4.1\n"
            "        ports:\n"
            "        - containerPort: 8080\n"
            "        livenessProbe:\n"
            "          httpGet:\n"
            "            path: /health\n"
            "            port: 8080\n"
            "          initialDelaySeconds: 15\n"
            "          periodSeconds: 10\n"
            "        readinessProbe:\n"
            "          httpGet:\n"
            "            path: /health\n"
            "            port: 8080\n"
            "          initialDelaySeconds: 5\n"
            "          periodSeconds: 5",
            language="yaml",
        )

    st.divider()

    st.markdown("### 4. The Complete Production Lifecycle (How It Fits)")
    st.markdown(
        "1. **Monitor & Detect:** OneUptime synthetic probes continuously ping `/health`.\n"
        "2. **Outage Detected:** The service returns 5xx or latency spikes → OneUptime opens an Incident.\n"
        "3. **Trigger Hindsight:** OneUptime Workflow dispatches JSON alert to Hindsight Webhook.\n"
        "4. **AI Incident Briefing:** Hindsight calls `recall()`, finding matching historical incidents and team policies.\n"
        "5. **Triage in 5 Minutes:** On-call engineer gets the exact fix (e.g. rollback command) and explicit warnings on actions that made it worse before.\n"
        "6. **Post-Mortem & Retain:** Engineer resolves the incident; the resolution and lessons learned are retained (`retain()`), updating team memory for the next outage."
    )
