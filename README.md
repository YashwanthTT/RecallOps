# Incident Memory Agent

An on-call incident-response copilot that remembers what your team already survived.

When a production alert fires, generic AI says *"restart the pods and scale up."* This agent recalls the last time **checkout-api** did exactly that and made the outage worse, then briefs the on-call engineer with the fix that actually worked.

> Built for the **AI Agents That Learn Using Hindsight** hackathon. Every resolved incident is retained, so the agent improves with use.

---

## The problem

On-call engineers lose the first 10–20 minutes of every incident re-reading dashboards, old tickets, and Slack threads. The expensive knowledge is not in the runbook — it is in the **post-mortem**: which deploy caused it, which command fixed it, and which plausible action made it worse last time.

Northwind Pay (fictional) has 11 past incidents, 4 team policies, and the same two failure patterns repeating across services. Incident Memory Agent turns that history into a five-second briefing.

## What the agent produces

Every briefing has the same five sections:

1. **Likely root cause** — with a confidence level
2. **Matching past incidents** — only IDs actually present in recalled memory
3. **Do first** — at most four steps, with exact commands from past resolutions
4. **Do NOT do** — actions that previously made the incident worse, with the incident ID and consequence
5. **Escalate** — who to page, which channel, and time-bound team policy

The before/after is the point. The same model and the same system prompt run twice. The **only** difference is the recalled-memory block.

| Without memory (baseline) | With Hindsight memory |
|---|---|
| Root cause unknown | Matches **INC-2139** and **INC-2041** |
| Restart pods | Roll back `v3.4.1` to `v3.4.0` first |
| Scale replicas | Check `hikaricp.connections.pending` |
| No warning | **Do NOT** scale or restart: both previously made it worse |
| Generic on-call page | Page Marcus Bell; payments lead within 10 minutes if payments error rate >5% |

---

## How Hindsight is used

Memory is not a feature bolted onto the chat. It is the product.

| Hindsight operation | Where | What it does |
|---|---|---|
| `retain` | `seed_data.py` → sidebar **Seed**, and **Close the loop** tab | Stores 11 incidents + 4 policies, and every incident the user resolves, with a timestamp and context |
| `recall` | `agent.run_agent()` when `use_memory=True` | Retrieves up to ten memory units, then a second policy-focused recall so escalation rules are not crowded out by long log documents |
| `reflect` | **Reflect** tab | Answers cross-incident questions ("what keeps recurring?", "what repeatedly made things worse?") over the whole bank |

The Python client is `hindsight-client`:

```python
from hindsight_client import Hindsight

client = Hindsight(base_url="http://localhost:8888")
client.retain(bank_id=BANK, content=document, context="past incident INC-2139",
              timestamp="2026-09-08T03:31:00Z")

results = client.recall(bank_id=BANK, query="checkout-api 502 HikariPool")
for memory in results.results:
    print(memory.text)

answer = client.reflect(bank_id=BANK, query="Which services have recurring failures?")
print(answer.text)
```

`MemoryStore` wraps the client and adds a transparent fallback. If Hindsight cannot be reached, the sidebar turns yellow, shows the exact error, and the app uses an in-process keyword-overlap store. The fallback is labelled in every briefing and in the UI — it is never passed off as Hindsight.

### Memory lifecycle

```
Past incident / closed incident
        │
        ▼
     retain()  ──►  Hindsight bank (incident-response-agent)
        ▲                     │
        │                     ▼
  Close the loop        recall() ──► agent briefing
                              │
                              ▼
                          reflect() ──► cross-incident answers
```

---

## Run it

### 1. Install

Dependencies are managed with [uv](https://docs.astral.sh/uv/):

```bash
uv sync                       # creates .venv from uv.lock
cp .env.example .env
```

Python 3.11+ is required (uv fetches a suitable interpreter automatically). Add or update a dependency with `uv add <package>`; it updates `pyproject.toml` and `uv.lock` together.

### 2. Start Hindsight (choose one)

**Local Docker** (verified command from the Hindsight installation docs):

```bash
export GROQ_API_KEY=gsk_your_groq_key

docker run -it --pull always --name hindsight --restart unless-stopped \
  --shm-size=1g --stop-timeout 75 \
  -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_PROVIDER=groq \
  -e HINDSIGHT_API_LLM_API_KEY=$GROQ_API_KEY \
  -e HINDSIGHT_API_LLM_MODEL=openai/gpt-oss-120b \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

- API: `http://localhost:8888`
- Control Plane UI: `http://localhost:9999`

**Hindsight Cloud**:

1. Sign up at <https://ui.hindsight.vectorize.io>.
2. Add promo code `MEMHACK99` in **Billing** after registering.
3. Copy your Cloud **API URL** and **API key** from the console.
4. Set them in `.env`:

```dotenv
HINDSIGHT_BASE_URL=https://your-cloud-api-url
HINDSIGHT_API_KEY=your-key
HINDSIGHT_BANK_ID=incident-response-agent
HINDSIGHT_TIMEOUT=120
```

The bank is created on the first `retain` if it does not exist. Seeding uses deterministic document IDs with `update_mode="replace"`, so clicking **Seed** again updates the demo data instead of duplicating it. The first seed also applies the bank's `reflect_mission` and three on-call directives (cite only retrieved IDs, lead with harmful remediation, admit missing history).

**No Hindsight server?** Skip this step. The app starts in local fallback mode and all three tabs still work.

### 3. Start the app

```bash
uv run streamlit run app.py
```

Open <http://localhost:8501>, then click **Seed past incidents + policies** in the sidebar.

### 4. LLM key (optional)

```dotenv
GROQ_API_KEY=gsk_...
LLM_MODEL=openai/gpt-oss-120b
```

Without a Groq key, the app uses a deterministic offline writer that is grounded in the recalled memories. The before/after comparison still works; only the prose is less flexible. If the LLM errors, rate-limits, or returns an empty/function-call-invalid response, the error is shown and the offline briefing is rendered instead.

---

## Live verification (real Hindsight + Groq)

The offline checks are not enough to prove the live path. `smoke_test.py` deliberately **fails** if Hindsight is unreachable instead of falling back.

```bash
export HINDSIGHT_BASE_URL=https://your-cloud-url    # or http://localhost:8888
export HINDSIGHT_API_KEY=your-hindsight-key         # blank for local Docker
export GROQ_API_KEY=gsk_your_groq_key               # optional; skipped if absent
uv run python smoke_test.py
```

It runs, in order:

1. `connect()` probe recall (fails, does not fall back);
2. `retain()` a synthetic document into `<bank>-smoke`;
3. `recall()` and asserts the unique token comes back;
4. `reflect()` and asserts a non-empty answer;
5. one real Groq chat completion, if `GROQ_API_KEY` is set.

Expected last line: `PASS: ...` for each step. A non-zero exit code means the live path is broken.

Then run the full acceptance test against the real backend:

```bash
uv run python demo_check.py          # seeds the configured bank and asserts INC-2041 / INC-2139
uv run streamlit run app.py          # Seed → checkout preset → Run
```

### Run it from GitHub Actions

`.github/workflows/live-smoke.yml` is a manual workflow. Add these repository secrets under **Settings → Secrets and variables → Actions**:

| Secret | Required | Value |
|---|---|---|
| `HINDSIGHT_BASE_URL` | yes | Cloud API URL or `http://localhost:8888` |
| `HINDSIGHT_API_KEY` | Cloud only | Hindsight key |
| `HINDSIGHT_BANK_ID` | no | defaults to `incident-response-agent`; smoke uses `-smoke` suffix |
| `GROQ_API_KEY` | no | real LLM call is skipped without it |
| `LLM_MODEL` | no | defaults to `openai/gpt-oss-120b` |

Then **Actions → live-smoke → Run workflow**. GitHub-hosted runners cannot reach a Docker container on your laptop, so use Hindsight Cloud there.

### Use a different GitHub repo / deployment

The app reads configuration from `.env` locally and from Streamlit Cloud secrets when deployed. For Streamlit Community Cloud, add this in **App settings → Secrets**:

```toml
GROQ_API_KEY = "gsk_..."
HINDSIGHT_BASE_URL = "https://your-cloud-url"
HINDSIGHT_API_KEY = "your-hindsight-key"
HINDSIGHT_BANK_ID = "incident-response-agent"
HINDSIGHT_TIMEOUT = 120
```

If the other repo is just where the code lives:

```bash
git remote add origin git@github.com:you/incident-memory-agent.git
git push -u origin main
```

If the other repo already runs this application, it only needs those same environment variables/secrets and a redeploy. If it runs a *different* app, it will not share this app's behavior just by pointing at the same Hindsight bank — it must call the same `retain` / `recall` / `reflect` operations.

---

## 3-minute demo script

| Time | Action | What to say |
|---|---|---|
| 0:00 | Open the app | "On-call engineers lose 10–20 minutes per incident re-reading history. The runbook is generic; the post-mortem is not." |
| 0:15 | Sidebar → **Seed past incidents + policies** | "15 memories: 11 incidents across 8 services, plus 4 team policies. Each one has real log lines, exact commands, and what made it worse." |
| 0:35 | Tab 1 → preset **checkout-api 502 spike** → **Run** | "Same model, same prompt, run twice. Left: no memory. Right: Hindsight." |
| 0:50 | Point at the left column | "Restart pods. Scale replicas. Check for a deploy. This is the generic advice that has hurt Northwind Pay twice." |
| 1:00 | Point at the right column | "It cites **INC-2139** and **INC-2041**, both checkout pool incidents. It says roll back first, then check `hikaricp.connections.pending`. And it explicitly says do **not** scale or restart — scaling pushed Postgres to 480/500 connections and restarts re-exhausted the pool in under three minutes." |
| 1:30 | Open **Recalled memories** | "This is not the model hallucinating. These are the retained documents, with scores." |
| 1:50 | Tab 2 → close a new incident: service checkout-api, title "502s after v4.2.0 deploy", root cause "HikariPool connection pool exhausted after deploy v4.2.0 lowered pool max to 10", fixed "rollback to v4.1.9 and restore pool to 40", did NOT work "scaling replicas saturated Postgres; restarting pods made it worse" → **Retain** | "Incidents do not stay in a wiki. The outcome is retained with the current UTC timestamp." |
| 2:20 | Back to Tab 1 → **Run** again | "The new incident is now in memory and appears under Matching past incidents. The agent learned during the demo." |
| 2:40 | Tab 3 → **What should a new on-call engineer know about checkout-api?** → **Reflect** | "Reflect reasons across the whole bank, not just top-k. This is the onboarding doc nobody has time to write." |
| 2:55 | Show the Hindsight Control Plane at `:9999` | "Every retain, recall and reflect is visible in the bank." |

---

## Acceptance test

```bash
uv run python demo_check.py
```

Seeds the local fallback store (or Hindsight, if running) and runs the checkout-api 502 preset with `use_memory=False` and `True`. It asserts:

- the baseline never cites an incident ID;
- the memory run cites **INC-2041** and **INC-2139**;
- it mentions rollback, restart, and scaling;
- all compile checks pass.

Verified output is in the "Verification status" section below.

---

## File map

| File | Purpose |
|---|---|
| `memory.py` | `MemoryStore` + `Memory`: Hindsight `retain`/`recall`/`reflect`, connection probe, visible local fallback |
| `seed_data.py` | 11 fictional Northwind Pay incidents, 4 policies, 4 demo alerts, document renderers |
| `agent.py` | `run_agent()`, system prompt, memory block, offline deterministic briefing, LLM error handling |
| `app.py` | Streamlit UI: sidebar status/seed, before-vs-after, close the loop, reflect |
| `demo_check.py` | End-to-end acceptance check with assertions |
| `smoke_test.py` | Live-only Hindsight + Groq connectivity check; fails instead of falling back |
| `.github/workflows/live-smoke.yml` | Manual CI job for the live check using repository secrets |
| `pyproject.toml` / `uv.lock` | Dependencies and the locked resolution |
| `.env.example` | Environment template, no secrets |
| `README.md` | This document |

---

## Design notes and edge cases

- **Same prompt, one difference.** `SYSTEM_PROMPT` is a module constant. `use_memory=False` does not call `recall` at all, which makes the baseline an honest A/B test.
- **No invented incident IDs.** The prompt only allows IDs that appear verbatim in the memory block; the offline writer only reads parsed IDs from recalled documents.
- **Recall failure never kills the briefing.** The agent continues without memory, states that recall failed, and the UI still renders both columns.
- **LLM failure never kills the briefing.** Auth errors, rate limits, timeouts, empty responses, and malformed tool-call-style responses are caught, shown as a short error, then replaced with the grounded offline briefing.
- **No secrets in code.** `GROQ_API_KEY`, `HINDSIGHT_API_KEY`, and URLs come from `.env`.
- **UI errors are messages, not stack traces.** Every external call in `app.py` is wrapped; the user sees `TypeName: message`.
- **Timestamps are preserved.** Seeded incidents retain their original ISO date; closed incidents use the current UTC timestamp. Hindsight can reason temporally.
- **The fallback is loud.** `store.backend` and `store.error` drive a green/yellow sidebar; every offline briefing footer names the backend.
- **Deduplication.** Recalled documents are deduplicated by ID so the same incident cannot be cited twice.
- **Policies are recalled separately.** Long log documents often beat short policy text in top-k retrieval, so a second policy-focused recall keeps escalation rules in the briefing.

## Where this fits in the real world

- **Incident channel copilot.** A PagerDuty/Slack bot posts the alert and logs, calls the same `run_agent`, and replies with the memory-grounded briefing before the on-call has opened a runbook.
- **Shift handoff.** `reflect("What broke repeatedly this week, and which fixes made it worse?")` turns raw incident history into a handoff note for the next responder.
- **Change review.** Before a deploy, ask the bank about the service and the change (pool size, cert rotation, index, feature flag). The answer is evidence from prior incidents, not a generic checklist.
- **Post-incident learning.** The close-the-loop form retains the root cause, exact fix, harmful actions, and TTR. The next similar alert cites that new memory, which is the improvement loop.
- **Runbook drift.** When a stored step stops working, the newer resolved incident contradicts it; retrieval surfaces the recent outcome instead of an obsolete wiki page.

Guardrails for production: redact secrets/PII before `retain`, use one bank per environment/team, scope API keys, log who retained what, and keep a human approval step. The agent recommends commands; it should not execute them.

### What we borrowed from official sources

- [Hindsight self-driving agents — Incident Response Commander](https://github.com/vectorize-io/self-driving-agents/blob/main/engineering/ops/incident-response-commander.md): severity/comms discipline and blameless post-incident capture.
- [Hindsight bank directives](https://docs.hindsight.vectorize.io/cloud/memory-banks) and [mental models](https://docs.hindsight.vectorize.io/cloud/mental-models): bank-level behavior and pre-computed reflections.
- Hindsight's retain/recall/reflect design: store outcomes, retrieve by situation, and reason across the whole bank rather than only the top-k.

Adopted here: deterministic document IDs for idempotent seeding, a `reflect_mission` plus directives, a longer timeout for agentic `reflect`, and prompt rules that forbid new commands or scaling advice not present in memory.

## What is intentionally small

This is a hackathon demo, not a production pager. There is no auth, no live Prometheus/PagerDuty integration, no queue, and the local fallback is in-process keyword overlap rather than embeddings. The scope is one workflow done well: alert in, memory-grounded briefing out, closed incident retained.

---

## Verification status

**Ran locally on 2026-11-06 (macOS, Python 3.13.11, `hindsight-client` 1.2.0, `streamlit` 1.67.0, `openai` 3.46.0):**

- `uv run python -m py_compile memory.py seed_data.py agent.py app.py demo_check.py smoke_test.py` — passed.
- `uv run python demo_check.py` in fallback mode (no Hindsight server, no Groq key) — passed all assertions. The memory run recalled 8 documents, cited INC-2139 and INC-2041, recommended rollback, and warned about scaling/restarting.
- Streamlit app smoke-tested with Streamlit's `AppTest`: seed (15 documents), run both briefings, close an incident, and reflect all completed without exceptions.
- `smoke_test.py` with no server exits `1` and reports the connection error, as designed; it does not silently fall back.
- The GitHub Actions workflow YAML parses correctly.

**Live Hindsight Cloud + Groq (same date, `HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io`):**

- `python smoke_test.py` — passed all five steps: Hindsight probe, retain, recall (token returned), reflect (338 characters), and a real Groq completion (`openai/gpt-oss-120b` replied `OK`).
- `python demo_check.py` — passed all assertions against the live bank. It seeded 11 incidents and 4 policies, recalled 13 memory units, cited **INC-2139**, **INC-2041**, and **INC-2124**, recommended rollback, and warned about scaling and restarting. This is the same command staff can rerun; it is idempotent.
- `reflect` on the live bank answered a cross-incident question about scaling/restarting with **INC-2124** and the 960/1000 Postgres connection consequence.
- Streamlit `AppTest` connected to the live bank without exceptions and rendered the sidebar metrics.
- Repeated seeding was verified with `document_id` lookups: `incident-INC-2139` stayed at 2 memory units after multiple seed runs (replace, not append).
- The first live run exposed two real issues that are now fixed: `reflect` needed a 120-second timeout, and Groq `gpt-oss-120b` needs more than 10 output tokens because reasoning tokens count toward `max_tokens`.

**Still not tested:**

- PagerDuty/Slack/Statuspage integrations, multi-user auth, and browser-level UI interaction (only Streamlit `AppTest`).
- A production-scale bank (thousands of incidents) and its latency/cost profile.
- Automatic redaction of secrets/PII before `retain`; that is an integration responsibility, not implemented here.

All incident data, people, services, and policies are fictional.
