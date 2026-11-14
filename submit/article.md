# Why our incident agent remembers bad fixes using Hindsight

At 2:14 AM on a Tuesday, an alert fires for our checkout API. The generic runbook and every standard LLM prompt tell the on-call engineer to restart the failing pods and scale the deployment to twenty replicas. If they follow that advice, they will flood the primary database with four hundred new connections, tip connection pools into complete starvation, and turn a four-minute degraded service into a forty-minute hard outage.

We built an on-call copilot that does the opposite: it remembers the exact remediation steps that previously failed, cites the specific historical post-mortems where those failures occurred, and warns the engineer away from harmful actions before giving the proven fix. To achieve this, we integrated [Hindsight agent memory](https://vectorize.io/what-is-agent-memory) into our production incident triage loop.

Here is how the architecture works, how we engineered "negative memory" into autonomous triage, and what we learned connecting real-time telemetry to institutional history.

---

## What the System Does and How It Hangs Together

Our on-call stack unites three distinct layers:

1. **Telemetry & Synthetic Probing:** Open-source monitoring via OneUptime continuously exercises synthetic health checks against microservice endpoints (such as `/health` on our core payment and checkout services). When error budgets burn or latency spikes, OneUptime packages the alert telemetry and fires an automated webhook.
2. **Institutional Memory via Hindsight:** Rather than treating each incident as a blank slate or attempting to stuff hundreds of legacy Markdown post-mortems into a stateless context window, we persist verified historical incidents, runbook resolutions, and team operational policies in a dedicated memory bank managed by [Hindsight](https://github.com/vectorize-io/hindsight).
3. **Grounding & Triage Agent:** When an alert fires, our triage agent issues semantic recall queries into Hindsight. If Hindsight returns historical precedent, the agent synthesizes a five-minute tactical briefing containing:
   - **Likely root cause** with confidence scoring.
   - **Matching past incidents** citing exact historical incident IDs.
   - **Do first** with copy-pasteable, verified shell commands.
   - **Do NOT do** listing explicit pitfalls and negative memory warnings.
   - **Escalate** identifying who to page based on organizational policies.

When the outage resolves, the engineer closes the loop. The validated resolution—alongside what failed during troubleshooting—is retained back into Hindsight with UTC timestamps, updating organizational memory for every subsequent shift.

```
 ┌─────────────────────────────────────────────────────────┐
 │               Synthetic Probes & Telemetry              │
 │          (OneUptime Monitoring / Health Checks)         │
 └────────────────────────────┬────────────────────────────┘
                              │ HTTP 503 / Latency Spikes
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │             Webhook Intake & Ingestion Layer            │
 │            (:8787 Normalized Incident Stream)           │
 └────────────────────────────┬────────────────────────────┘
                              │ Incident Context
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │             Hindsight Memory Core (Bank Engine)         │
 │   • retain()  -> Store incidents, policies & post-mortems│
 │   • recall()  -> Semantic search over past outcomes     │
 │   • reflect() -> Cross-history synthesis & patterns     │
 └────────────────────────────┬────────────────────────────┘
                              │ Grounded Memories
                              ▼
 ┌─────────────────────────────────────────────────────────┐
 │           Incident Copilot Briefing & War Room          │
 │   • Baseline vs Grounded side-by-side comparison        │
 │   • Impact Strip: Cited IDs, Pitfalls Caught, Saved Time│
 │   • "⛔ Avoid this" Negative Memory warnings            │
 │   • Exact rollback commands (Human-in-the-loop)         │
 └─────────────────────────────────────────────────────────┘
```

---

## The Technical Through-Line: Engineering Negative Memory

Most AI agent memory implementations suffer from positive confirmation bias: they retrieve what worked in the past. In distributed systems SRE, knowing what worked is only half the battle. Knowing what *made things worse* is what prevents multi-million-dollar outages.

When engineers write post-mortems, the most valuable section is rarely the final fix; it is the log of dead ends, harmful assumptions, and destructive remediation attempts. For instance, in an outage caused by database connection pool exhaustion, pod restarts temporarily mask the failure while threads queue up, and scaling horizontal replicas multiplies total database connections until PostgreSQL hits `max_connections`.

To capture this, we structured our memory schemas and prompt boundaries around explicit negative memory retention. When an incident closes, we isolate the `what_failed` parameter:

```python
def outcome_document(
    service: str,
    title: str,
    root_cause: str,
    fixed: str,
    failed: str,
    ttr_minutes: int,
    resolver: str,
    severity: str = "Sev 2",
) -> tuple[str, str]:
    now = datetime.now(timezone.utc)
    incident_id = f"INC-{now:%y%m%d%H%M%S}"
    failed_items = [part.strip() for part in failed.replace("\n", ";").split(";") if part.strip()]
    failed_block = "\n".join(f"- {item}" for item in failed_items) if failed_items else "- None recorded."
    fixed_one_line = " ".join(fixed.split())
    
    document = (
        f"Incident ID: {incident_id}\n"
        f"Date: {now.isoformat().replace('+00:00', 'Z')}\n"
        f"Service: {service}\n"
        f"Severity: {severity}\n"
        f"Title: {title}\n"
        f"Symptoms: Reported through operational intake by {resolver}.\n"
        f"Root cause: {root_cause}\n"
        f"Resolution:\n1. {fixed_one_line}\n"
        f"What failed (made it worse):\n{failed_block}\n"
        f"TTR: {ttr_minutes} minutes\n"
        f"Responder: {resolver}"
    )
    return incident_id, document
```

By explicitly isolating `What failed (made it worse)` inside the structured document payload, Hindsight indexes not just the vectors representing symptoms and fixes, but the semantic space surrounding detrimental interventions.

---

## Code-Backed Implementation

### 1. Robust Retain and Recall with Hindsight

In our core memory integration, we wrapped the client using the official [Hindsight docs](https://hindsight.vectorize.io/) specifications. We configure bank directives so the memory store understands its persona as a site-reliability knowledge base, and we use idempotent document IDs to ensure re-seeding or post-incident updates never create duplicate hallucinations:

```python
class MemoryStore:
    def __init__(self, base_url: str = "http://localhost:8888", bank_id: str = "incident-response-agent"):
        self.base_url = base_url
        self.bank_id = bank_id
        self._client = None

    def retain(
        self,
        content: str,
        context: str = "",
        timestamp: str | None = None,
        document_id: str | None = None,
        update_mode: str = "replace",
    ) -> None:
        if not self._client:
            raise RuntimeError("Memory backend is not connected.")
        
        self._client.retain(
            bank_id=self.bank_id,
            content=content,
            context=context,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            document_id=document_id,
            update_mode=update_mode,
        )

    def recall(self, query: str, limit: int = 5) -> list[Memory]:
        if not self._client:
            raise RuntimeError("Memory backend is not connected.")
        
        results = self._client.recall(bank_id=self.bank_id, query=query, limit=limit)
        return [Memory(text=item.text, score=getattr(item, "score", 0.0)) for item in results]
```

### 2. Enforcing Strict Behavioral Guardrails in the Prompt

LLMs are prone to hallucinating plausible-sounding Kubernetes commands (`kubectl scale --replicas=50`). In high-pressure incidents, an engineer might run an hallucinated command without double-checking.

Our agent prompt enforces a strict contract: commands can only be suggested if they appear verbatim inside retrieved memories. If memory does not possess a verified command, the agent must describe the check textually and omit the code block:

```text
You are Incident Memory Agent, an on-call incident-response copilot.

Your job: turn a production alert plus retrieved memories of past incidents
and team policies into a briefing that helps an on-call engineer act in the next 5 minutes.

Rules:
- If RETRIEVED MEMORY is empty: output a generic runbook and plainly state no incident history was available. Do not cite any incident ID.
- Never invent an incident ID, command, policy, responder, or metric. Use only the alert and retrieved memory.
- Every command in **Do first** must appear verbatim in RETRIEVED MEMORY.
- Never recommend an action that RETRIEVED MEMORY says made things worse.
- Output section **Do NOT do** listing actions that made past incidents worse, each citing its incident ID and consequence.
```

### 3. Fail-Loud Architecture: Never Fake Memory

A subtle design decision we made early on was to drop in-process mock fallbacks. If the Hindsight service is unavailable, the copilot refuses to run memory-grounded queries and warns the operator that memory is offline.

Faking memory with ungrounded keyword matching gives on-call engineers false confidence during an emergency. If institutional memory is unavailable, the agent must fail loudly and transparently.

---

## Real-World Behavior: The Incident Walkthrough

To validate the architecture, let us look at a real scenario running on our `checkout-api` microservice.

### The Injected Outage
A new release (`v3.4.1`) rolls out to production. The developers decreased the HikariCP connection pool size from 40 to 12 and added a synchronous foreign exchange lookup inside an active database transaction.

Under normal load, latency degrades. Then, connection pool timeouts cascade:
```text
2026-11-06T18:41:02Z checkout-api HikariPool-1 - Connection is not available, request timed out after 30000ms
2026-11-06T18:41:15Z deploy-bot INFO v3.4.1 rolled out 6m before alert
```
OneUptime's synthetic probes detect HTTP 503 errors and open incident `INC-OU9001`.

### Without Hindsight Memory (The Generic LLM Baseline)
When given the alert telemetry with no retrieved memory, standard LLM completions offer standard runbook boilerplate:
- **Likely root cause:** High incoming request volume causing thread pool starvation.
- **Do first:**
  1. Scale deployment replicas from 4 to 20: `kubectl scale deployment checkout-api --replicas=20`.
  2. Perform a rolling restart of all checkout pods: `kubectl rollout restart deployment checkout-api`.
- **Do NOT do:** No documented harmful actions.

### With Hindsight Memory (The Grounded Agent)
When Hindsight recall is enabled, the agent surfaces two historical incidents: `INC-2139` (a previous pool exhaustion event during Black Friday) and `INC-2041` (an FX latency cascade).

The generated briefing completely changes:
- **Likely root cause:** Hikari connection pool exhaustion caused by blocking FX calls introduced in deploy `v3.4.1`. (Confidence: high).
- **Matching past incidents:**
  - `INC-2139`: Pool exhaustion after v3.2.0 deploy caused identical 30-second timeouts.
  - `INC-2041`: Latency spike in payment processing due to synchronous downstream call.
- **Do first:**
  1. Roll back the deployment immediately:
     ```bash
     deploy rollback --service checkout-api --to v3.4.0 --reason "pool exhaustion after v3.4.1"
     ```
  2. Verify active database connections:
     ```bash
     curl -s http://localhost:8080/metrics | grep hikaricp_connections_pending
     ```
- **⛔ Do NOT do (Negative Memory):**
  - **Do NOT scale replicas up:** In `INC-2139`, scaling checkout-api to 20 replicas consumed all 480 connections on the primary PostgreSQL instance, crashing orders and auth services.
  - **Do NOT restart pods blindly:** In `INC-2139`, restarting pods re-exhausted connection pools within 180 seconds and dropped all in-flight shopping carts.
- **Escalate:** Page Marcus Bell (Checkout Team Lead) per policy `POL-104`.

The difference is night and day. The generic agent offered textbook advice that would have escalated a minor degradation into a site-wide disaster. The memory-grounded agent prevented the disaster and provided the exact rollback command.

---

## Cross-Incident Reasoning with `reflect()`

Beyond point-in-time incident response, we needed a way to synthesize systemic risks across dozens of outages. Point lookups via vector search (`recall`) struggle with meta-questions such as: *"Which remediation actions have repeatedly made things worse across all services?"*

To solve this, we leverage Hindsight's `reflect()` API. Reflect reasons across the entire document corpus rather than just returning top-$k$ snippets.

When queried with:
```python
answer = store.reflect("Which remediation actions have repeatedly made things worse across our infrastructure?")
```

Hindsight produces a structured synthesis citing historical evidence:
1. **Unchecked pod restarts during connection pool starvation (`INC-2139`, `INC-2041`):** Restarts clear the symptoms for less than three minutes while thrashing database connection handshakes.
2. **Flushing Redis caches during high auth latency (`INC-2204`):** Issuing `FLUSHALL` during an active authentication spike stripped cache layers and redirected thousands of uncached token verifications directly to PostgreSQL, triggering a total auth outage.
3. **Database restarts during peak write spikes (`INC-1988`):** Forcing an immediate restart on the primary database forced a 22-minute Write-Ahead Log (WAL) replay during which write transactions were completely locked.

This turns post-mortems from dead Google Docs into continuous architectural intelligence.

---

## 4 Lessons Learned Building with Agent Memory

### 1. Grounding Requires Exact Verbatim Constraints
If you allow an LLM to "adapt" shell commands found in memory, it will introduce subtle flag incompatibilities or invent non-existent flags. Enforce prompt rules stating that executable commands must appear verbatim in the retrieved memory payload, and flag any command requiring human approval with clear UI badges.

### 2. Time-Aware Context Prevents Stale Fixes
A resolution that worked three years ago on Kubernetes 1.18 might break a cluster running 1.30. Passing explicit ISO timestamps and semantic context into Hindsight's `timestamp` parameter ensures that newer post-mortems carry appropriate temporal weight when retrieving context for modern deployments.

### 3. Make Closing the Loop Frictionless
If adding post-mortem memory requires writing a 5-page wiki, engineers will skip it. By tying memory retention directly to the incident resolution interface (extracting fields from the OneUptime webhook and providing a 30-second post-mortem closure form), retaining new knowledge becomes a natural byproduct of resolving the ticket.

### 4. Separate Memory Banks by Domain
Do not dump API documentation, customer support tickets, and production infrastructure post-mortems into a single global vector bank. Isolating incident response into its own bank (`incident-response-agent`) maintained high semantic density and prevented irrelevant documentation from polluting high-urgency operational briefings.

---

## What’s Next

Reliable AI agents in production cannot be amnesiac. By coupling real-time synthetic monitoring with structured agent memory, we stopped repeating the same operational mistakes every on-call rotation.

If you are building autonomous SRE agents or looking to equip LLMs with persistent, structured recall, check out the [Hindsight GitHub repository](https://github.com/vectorize-io/hindsight) and explore how [Vectorize agent memory](https://vectorize.io/what-is-agent-memory) changes the way agents learn from real-world outcomes.
