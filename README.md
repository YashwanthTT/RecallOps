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

Hindsight is the primary backend. If it is unavailable, the app clearly
switches to a local keyword-overlap fallback; it never presents fallback
results as Hindsight results.

## Quick start

### 1. Install

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env
```

### 2. Configure the optional services

The app works without external services using its local fallback and offline
writer. For the full demo, add these values to `.env`:

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

Run the local acceptance check:

```bash
uv run python scripts/demo_check.py
```

It verifies that the memory-enabled briefing cites the expected incidents and
recommends rollback while warning against harmful scaling and restarts.

To verify a live Hindsight connection instead of using fallback mode:

```bash
export HINDSIGHT_BASE_URL=https://your-cloud-url
export HINDSIGHT_API_KEY=your-hindsight-key
export GROQ_API_KEY=gsk_your_groq_key
uv run python scripts/smoke_test.py
```

The smoke test fails when Hindsight is unreachable. It checks probe, retain,
recall, reflect, and an optional Groq completion.

## Project structure

```text
├── app.py                         Streamlit application
├── src/core/
│   ├── agent.py                   Briefing and prompt logic
│   ├── memory.py                  Hindsight client and local fallback
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
