# Incident Memory Agent

An incident-response copilot that learns from your team's past outages.

When an alert fires, the agent recalls similar incidents, recommends fixes
that worked before, and warns about actions that previously made the outage
worse. Resolved incidents are retained so the next briefing gets better.

Built for the **AI Agents That Learn Using Hindsight** hackathon.

## Why it matters

Runbooks contain general advice. Post-mortems contain the details that matter:
the deploy that caused the issue, the command that fixed it, and the tempting
action that made it worse.

Incident Memory Agent turns that history into a focused briefing:

1. Likely root cause and confidence
2. Matching past incidents
3. Recommended first steps with known commands
4. Actions to avoid and their consequences
5. Escalation guidance from team policies

The app compares the same agent with and without recalled memory, making the
value of Hindsight visible.

## How this maps to the judging criteria

| Criterion | What to look at |
| --- | --- |
| **Innovation** | Negative memory: the agent remembers what made past outages *worse*, not just what fixed them. Most memory demos retrieve similar tickets; this one warns against repeating harmful remediation. |
| **Use of Hindsight** | `retain`, `recall`, and `reflect` drive the briefing, the learning loop, and cross-history questions. The app refuses to fake memory when Hindsight is down, and the live tab shows the same model with and without recall plus cited-ID and pitfall deltas. |
| **Technical implementation** | Typed Hindsight wrapper, bank mission/directives, idempotent seeding, deterministic no-LLM writer, clear error states, and a live smoke test. |
| **User experience** | One screen shows before/after, impact metrics, recalled memories, and exact commands. Presets and a close-the-loop form make the learning progression a two-click demo. |
| **Real-world impact** | Fits the on-call workflow: monitoring via OneUptime, memory via Hindsight, human approval before running any command. Separate banks per environment. |

## How it works

```text
Alert or incident
        |
        v
     recall()  --->  Memory-grounded briefing
        ^                    |
        |                    v
     retain() <---  Resolved incident
                             |
                             v
                         reflect()
```

- **`retain`** stores incidents, policies, and new resolutions.
- **`recall`** retrieves relevant history for an active incident.
- **`reflect`** finds patterns across the entire memory bank.

Hindsight is the only memory backend. There is no local fallback: if the
server is unreachable the app says so and refuses to answer from memory, rather
than presenting in-process results as recalled history.

### Where Hindsight is used

| Stage | Hindsight call | Code |
| --- | --- | --- |
| Seed history | `retain` | `app.py` → `seed_memories()` |
| Resolve an incident | `retain` | **Close the loop** tab, OneUptime intake |
| Brief an active alert | `recall` | `run_agent()` in `src/core/agent.py` |
| Answer cross-history questions | `reflect` | **Reflect** tab |
| Configure bank mission and directives | `create_bank` / `create_directive` | `MemoryStore.configure_bank()` |

The bank keeps an incident commander mission and directives that force the
agent to cite only retrieved incident IDs, lead with harmful remediation, and
admit missing history. Seeding uses stable `document_id`s with
`update_mode="replace"`, so re-running it does not duplicate incidents.

## Quick start

### 1. Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

### 2. Configure Hindsight (required) and Groq (optional)

A running Hindsight instance is required. Groq is optional; without it the app
uses a deterministic writer grounded in the memories Hindsight recalled. Add
these values to `.env`:

```dotenv
HINDSIGHT_BASE_URL=http://localhost:8888
HINDSIGHT_API_KEY=
HINDSIGHT_BANK_ID=incident-response-agent
GROQ_API_KEY=gsk_...
LLM_MODEL=openai/gpt-oss-120b
```

You can use [Hindsight Cloud](https://ui.hindsight.vectorize.io), or start
Hindsight locally with Docker:

```bash
export GROQ_API_KEY=gsk_your_groq_key
docker run -it --pull always --name hindsight --restart unless-stopped \
  --shm-size=1g --stop-timeout 75 \
  -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_PROVIDER=groq \
  -e HINDSIGHT_API_LLM_API_KEY="$GROQ_API_KEY" \
  -e HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-120b \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

### 3. Run the app

```bash
uv run streamlit run app.py
```

Open <http://localhost:8501> and click **Seed past incidents + policies**.

The sidebar reports the live Hindsight connection. If the server is
unreachable it shows the connection error and disables seeding; use **Retry
Hindsight connection** after starting the server.

## Local MCP server for OpenCode

Requires Node/npm, Python 3.11+, and uv. Install Python dependencies with
`uv sync`. No npm dependencies are needed. Copy `.env.example` to `.env` if
you have not already, and configure your Hindsight URL, API key, and bank.

```bash
npm run mcp
```

This runs a local **stdio** MCP server: it waits for an MCP client on stdin,
so no browser URL or listening port is expected. OpenCode starts its own
server process using `npm run --silent mcp` to keep stdout protocol-only.
The committed `opencode.json` config targets OpenCode v2 (tested with 2.0.25).
From this project directory, run:

```bash
opencode mcp list
opencode
```

The `recallops` server should show as connected. You do not need to leave a
separate `npm run mcp` terminal open. For OpenCode v1, move the `recallops`
entry directly under `mcp` and add `"enabled": true`.

If your existing OpenCode background service references a deleted project
directory or fails to reload, start a fresh session here with
`opencode --standalone`. This bypasses that service without modifying other
projects. A server marked `pending` has not yet established its connection.

Ask the agent: “Use RecallOps to investigate checkout-api's 502 spike.
Retrieve similar incidents and harmful fixes, inspect the available recovery
actions, and verify service health after remediation.”

Available tools: `hindsight_status`, `recall_incidents`, `incident_briefing`,
`reflect_on_history`, `probe_service`, `retain_resolution`,
`list_recovery_actions`, and `execute_recovery_action`. Memory tools reuse
the app's Hindsight bank; there is no fabricated offline memory. Groq is
optional for briefings. The server does not automatically seed demo data.

To enable actual recovery, copy `recovery-actions.example.json` to
`recovery-actions.json`, replace the placeholder cluster context, namespace,
and deployment with your real targets, and keep only commands you authorize
the agent to execute. Set `RECALLOPS_ENABLE_ACTIONS=true` in `.env` and restart
OpenCode. Commands use fixed argument arrays, no shell expansion or
agent-supplied arguments. Production credentials come from the server process
environment and existing CLI configuration. This is local execution; remote
operations require a configured CLI such as kubectl or ssh. No production
targets or credentials are bundled.

A successful command exit does not prove recovery: use `probe_service` and
your diagnostics before retaining the outcome. A timed-out command can have
partially changed the target. Configure commands to redact secrets from
output. The action file and `.env` are ignored by Git.

```bash
npm run test:mcp
```

Tests cover protocol initialization, discovery, validation, memory errors,
and the recovery execution gate with a harmless local diagnostic. Live
Hindsight integration is checked separately by `scripts/smoke_test.py`.

Run `npm run check:mcp` for actual npm-launched MCP calls to status, action
discovery, and Hindsight recall. It prints real results, including explicit
tool errors if Hindsight is unavailable. All eight tools publish typed output
schemas and both structured JSON and text results. Failed or timed-out recovery
commands return MCP tool errors. Diagnostic probes report unhealthy service
state as data so agents can inspect the status and latency.

Run `npm run check:mcp -- --full` to also verify the payment-gateway briefing,
reflection, and demo health probe. Memory failures exit nonzero. This check
does not retain test incidents or execute recovery commands. If you change
`.env` while OpenCode is running, disconnect and reconnect RecallOps via
`/mcps` so its process reloads the configuration. Briefings can use historical
evidence without a localhost URL; probing a live service requires its URL.

## Demo flow

1. Open the incident briefing tab.
2. Select the **checkout-api 502 spike** preset and run it.
3. Compare generic advice with the Hindsight briefing.
4. Open **Close the loop**, resolve an incident, and retain its post-mortem.
5. Run the briefing again to see the new incident recalled.
6. Use **Reflect** to ask questions across the complete incident history.
7. Open the OneUptime tab to probe a service or simulate an outage.

The included demo data models fictional **Northwind Pay**: 11 incidents, four
policies, and several alert scenarios.

## OneUptime integration

OneUptime provides monitoring and incident management; Hindsight provides
long-term incident memory. The webhook receiver connects them:

```bash
uv run python src/integrations/webhook_server.py
```

It listens on `http://127.0.0.1:8787/oneuptime` by default.

- `POST /oneuptime` parses alerts and retains resolved post-mortems.
- `POST /oneuptime/briefing` returns an AI briefing for an incident.
- Set `ONEUPTIME_WEBHOOK_HOST` and `ONEUPTIME_WEBHOOK_PORT` to customize it.

The local target service used by the demo can be started with:

```bash
uv run python examples/real_world_app/server.py
```

Or launch the complete local demo environment:

```bash
./scripts/start_demo.sh
```

## Verification

Run the acceptance check against a running Hindsight instance:

```bash
uv run python scripts/demo_check.py
```

It seeds the demo bank, then verifies that the memory-enabled briefing cites
the expected incidents and recommends rollback while warning against harmful
scaling and restarts. It exits non-zero when Hindsight is unreachable.

For a shorter connectivity check:

```bash
export HINDSIGHT_BASE_URL=https://your-cloud-url
export HINDSIGHT_API_KEY=your-hindsight-key
export GROQ_API_KEY=gsk_your_groq_key
uv run python scripts/smoke_test.py
```

It checks probe, retain, recall, reflect, and an optional Groq completion, and
fails when Hindsight is unreachable.

## Project structure

```text
├── app.py                         Streamlit application
├── src/core/
│   ├── agent.py                   Briefing and prompt logic
│   ├── memory.py                  Hindsight client (only memory backend)
│   └── seed_data.py               Demo incidents and policies
├── src/integrations/
│   ├── oneuptime.py               Incident adapter and service probes
│   └── webhook_server.py          OneUptime webhook receiver
├── examples/real_world_app/       Demo checkout service
├── scripts/
│   ├── demo_check.py              Acceptance test
│   ├── smoke_test.py              Live backend check
│   └── start_demo.sh              One-command demo launcher
├── demo.md                        Video walkthrough
└── .env.example                   Configuration template
```

## Scope and guardrails

This is a hackathon demo, not an autonomous production pager. It has no
authentication, queue, or automatic secret/PII redaction. Use separate
Hindsight banks per environment, redact sensitive data before retaining it,
and keep human approval before executing any recommended command.

All incident data, people, services, and policies in the demo are fictional.
