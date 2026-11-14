# 🎬 Incident Memory Copilot + OneUptime — Complete Video Demo Guide

> **Hackathon Pitch Video Guide & Script**  
> **Topic:** AI Agents That Learn Using Hindsight Memory  
> **Target Video Length:** 3–4 minutes (with optional 5-minute deep-dive variant)  

---

## 🌟 Executive Summary: The Story in One Sentence

> *"When production breaks, generic runbooks tell you to **restart and scale**; our Hindsight Incident Copilot remembers that **the last two times you did that, the database died** — and instead gives you the proven rollback in 5 seconds."*

---

## 🏗️ System Architecture

```
 ┌────────────────────────────────────────────────────────┐
 │        Real-World Target Microservice (:8080)          │
 │       (Northwind Pay `checkout-api` with /health)      │
 └───────────────────────────┬────────────────────────────┘
                             │ Synthetic HTTP Checks
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │            OneUptime Monitoring Layer                  │
 │   • Detects HTTP 503 / Latency Spikes                  │
 │   • Declares Incident (INC-OU9001)                     │
 │   • Dispatches Webhook to Copilot (:8787)              │
 └───────────────────────────┬────────────────────────────┘
                             │ Alert + Telemetry
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │     Hindsight Memory Copilot (Streamlit App :8501)     │
 │   • Baseline (Without Memory): Generic harmful advice  │
 │   • Hindsight Memory: Recalls INC-2139 & INC-2041      │
 │   • Do First: Exact rollback command                   │
 │   • Do NOT Do: Warns against scaling and restarting    │
 │   • Close the Loop: retain() resolution for next time  │
 └────────────────────────────────────────────────────────┘
```

---

## ⚡ 1-Minute Quick Start (Before Recording)

Open three terminal windows (or run `./scripts/start_demo.sh` to boot everything at once):

### Terminal 1: Run the Real Target Microservice
```bash
uv run python examples/real_world_app/server.py
```
*(Runs on `http://localhost:8080`. You can also open this URL in a browser tab to view real-time DB pool metrics and visual gauges).*

### Terminal 2: Run the OneUptime Webhook Receiver
```bash
uv run python src/integrations/webhook_server.py
```
*(Listens on `http://127.0.0.1:8787` for OneUptime Workflows and synthetic alerts).*

### Terminal 3: Run the Streamlit Incident Copilot
```bash
uv run streamlit run app.py
```
*(Opens the interactive dashboard at `http://localhost:8501`).*

---

## ⏱️ Video Demo Timeline & Screen Walkthrough

| Timestamp | Visual Screen | Key Action | What to Say / Highlight |
|---|---|---|---|
| **0:00 – 0:35** | Streamlit Sidebar & Header | Click **"Seed 11 incidents + 4 policies"** | **The Hook:** Runbooks tell on-call engineers to restart and scale, causing catastrophic cascades. Introduce Northwind Pay and seed the Hindsight memory bank. |
| **0:35 – 1:10** | Tab 2: **Service monitor** | Click **"📦 Local checkout-api (:8080)"** → Click **"⚡ Probe endpoint now"** | **Live Monitoring:** Show the synthetic probe against the real local microservice returning `🟢 HTTP 200 OK (2.1ms)`. Service is healthy. |
| **1:10 – 1:45** | Tab 2: Outage Injection | Click **"💥 Break service"** → Click **"⚡ Probe endpoint now"** | **Chaos Outage:** Deploy v3.4.1 lowers DB connection pool. Probe returns `🔴 HTTP 503 (Connection pool exhausted)`. Click **"🚨 Declare incident from probe"** or inspect the active incident card. |
| **1:45 – 2:45** | Tab 2: AI War Room | Click **"🧠 Investigate with memory"** | **THE HEADLINE COMPARISON:**<br>• **Left (Without Memory):** Generic prompt says *"scale to 20 replicas, restart pods"*. Fatal.<br>• **Right (With Memory):** Cites **INC-2139**, gives exact rollback command, and explicitly warns **Do NOT scale/restart**.<br>• **Impact Strip:** Shows cited IDs (0 → 2), pitfalls caught (0 → 2), time saved (~21 min). |
| **2:45 – 3:15** | Tab 2: Self-Healing & Retain | Click **"🔄 Recover all"** → Click **"✅ Resolve & retain post-mortem"** | **Closing the Loop:** Rollback applied, service recovers to 200 OK. Click resolve to retain outcome in Hindsight (`retain()`) with UTC timestamp. |
| **3:15 – 3:45** | Tab 5: **Reflect** | Select *"Which remediation actions have repeatedly made things worse?"* → Click **"🧭 Reflect across bank"** | **Institutional Memory:** Show `reflect()` reasoning across all 11+ incidents simultaneously, surfacing company-wide anti-patterns (connection storms, bad restarts). |
| **3:45 – 4:00** | Tab 6: **Integration guide** | Expand Docker Compose & Webhook blueprints | **Production Ready:** Drop-in Docker Compose, OneUptime Workflow JSON, and `/health` templates for Express, FastAPI, Go, and Kubernetes. |

---

## 🎙️ Word-for-Word Video Script

### Segment 1: The Problem & The Hook (0:00 – 0:35)
`[SHOW SCREEN: Streamlit dashboard at http://localhost:8501]`

> *"Hi everyone! Welcome to our demonstration of **Incident Memory Agent** — an on-call AI copilot that learns using Hindsight memory.*
>
> *Every on-call engineer knows this 2:00 AM nightmare: an alert fires, and generic runbooks say: **'Restart the pods and scale up replicas'**. But in distributed systems, blind runbooks are dangerous. What actually saves production is **post-mortem memory** — knowing what caused this last time, what fixed it, and crucially, what made it worse.*
>
> *Let's seed our team's past 11 incidents and 4 operational policies into our Hindsight memory bank."*  
> `[CLICK: 'Seed 11 incidents + 4 policies' in the sidebar]`  
> `[SHOW TOAST: 'Seeded 15 memories — memory is live.']`

---

### Segment 2: Real-World OneUptime Monitoring (0:35 – 1:10)
`[SHOW SCREEN: Click Tab 'Service monitor']`

> *"Next, we've integrated **OneUptime**, the popular open-source monitoring and status page platform. OneUptime continuously checks our live microservices.*
>
> *Running right here in our background process is Northwind Pay's actual `checkout-api` microservice on port 8080. Let's probe its synthetic `/health` endpoint.*
>
> `[CLICK: '📦 Local checkout-api (:8080)']`  
> `[CLICK: '⚡ Probe endpoint now']`
>
> *As you can see, our synthetic probe immediately returns **HTTP 200 OK** in 2.1 milliseconds. All 4 microservices are operational."*

---

### Segment 3: Injecting Outage & Detection (1:10 – 1:45)
`[SHOW SCREEN: Service monitor 'Break a service' card]`

> *"Now, let's simulate a real production disaster: deploy `v3.4.1` rolls out, lowers the Hikari connection pool, and adds a blocking foreign-exchange lookup. Let's break the service!"*  
> `[CLICK: '💥 Break service']`
>
> *Now let's probe the endpoint again:*  
> `[CLICK: '⚡ Probe endpoint now']`
>
> *Boom! The synthetic probe immediately fails with **HTTP 503: Service Unavailable — Connection pool exhausted**. We click 'Declare incident from probe' and OneUptime instantly declares critical Incident **INC-OU9001**."*

---

### Segment 4: The Headline — Memory vs No Memory (1:45 – 2:45)
`[SHOW SCREEN: Active incident card in Service monitor]`

> *"Now comes the magic. Let's click **'🧠 Investigate with memory'**."*  
> `[CLICK: '🧠 Investigate with memory']`
>
> *Look at this side-by-side comparison:*
>
> *On the **Left (Without Memory)**: The standard LLM with generic prompts gives the textbook answer: 'Restart pods, scale up to 20 replicas.' If an engineer runs that, they crash the underlying Postgres database.*
>
> *On the **Right (With Hindsight Memory)**: The agent consulted team history. Look at the **Impact Strip** at the top: it cited 2 real incidents, caught 2 dangerous pitfalls, recalled 4 relevant memories, and saved an estimated 21 minutes of downtime.*
>
> *Look at **⛔ Avoid this (Negative Memory)**: It warns in bold red cards: 'Do NOT scale replicas — last time that saturated Postgres to 480 connections. Do NOT restart pods — the pool re-exhausts in 3 minutes.'*
>
> *Look at **🚑 Do first**: It gives the exact rollback command from INC-2139:*  
> `deploy rollback --service checkout-api --to v3.4.0`  
> *and tells us to check `hikaricp.connections.pending`.*
>
> *And under **Escalate**, it automatically pages Marcus Bell, the checkout lead, citing team policy POL-104."*

---

### Segment 5: Healing & Closing the Loop (2:45 – 3:15)
`[SHOW SCREEN: Service monitor action buttons]`

> *"Let's apply the rollback fix."*  
> `[CLICK: '🔄 Recover all']`
>
> *The checkout service is healed! Now let's close the loop by clicking **'✅ Resolve & retain post-mortem'**.*  
> `[CLICK: '✅ Resolve & retain post-mortem']`
>
> *Hindsight immediately retains this outcome using `store.retain()`. The loop is closed: our AI agent just learned from this resolution, and the very next incident will cite this experience."*

---

### Segment 6: Deep Cross-Incident Reflection (3:15 – 3:45)
`[SHOW SCREEN: Click Tab 'Reflect']`

> *"What about institutional knowledge across shifts? In the **Reflect** tab, we don't just do top-k retrieval; we reason across the entire memory bank.*
>
> *Let's select the suggested question: **'Which remediation actions have repeatedly made things worse?'** and click **'🧭 Reflect across bank'**."*  
> `[CLICK: '🧭 Reflect across bank']`
>
> *Hindsight synthesizes patterns across every incident in the company: highlighting connection leaks, aggressive pod restarts, and replica storms. Every insight is cited with historical incident IDs. This is the post-mortem review nobody ever has time to write."*

---

### Segment 7: Real-World Blueprint & Conclusion (3:45 – 4:00)
`[SHOW SCREEN: Click Tab 'Integration guide']`

> *"In the **Integration guide** tab, we've provided the complete production blueprint: Docker Compose setups for OneUptime, Workflow webhook templates, and drop-in health endpoints for Express, FastAPI, Go, and Kubernetes.*
>
> *With Hindsight and OneUptime, outages stop being recurring nightmares — they become team memory. Thank you!"*

---

## 🧭 Optional Tour: Tabs 1, 3, and 4 (For Extended Demos & Judges)

If judges or audience members want to explore other parts of the application, show these screens:

### Tab 1: Briefing (One-Click Scenario Cards)
- 4 pre-configured scenario cards:
  1. `checkout-api 502 spike (connection pool)`
  2. `payments-gateway mTLS failures (certificate)`
  3. `orders-db recovery conflict (replica)`
  4. `kafka-ingest consumer lag (hot partition)`
- Click **"Run briefing →"** on any card to see instant before/after comparisons without needing to trigger a live outage.
- Expand **"Recalled memories"** to inspect exact cosine similarity scores and parsed incident fields.

### Tab 3: OneUptime Intake (3-Step Pipeline)
- **Step 1 (Paste):** Paste raw OneUptime JSON or plain text. Click **"Load sample payload"** for an instant realistic example.
- **Step 2 (Review):** The parser extracts ID, service, severity, status, TTR, root cause, resolution, and negative memory (`whatFailed`).
- **Step 3 (Retain):** Click **"🔁 3 · Retain in Hindsight"** to store the document. Check the box to immediately run a before/after briefing.

### Tab 4: Close the loop (Post-Mortem Form)
- Fill in: Service, Title, Severity, TTR, Root cause, What fixed it, and **What made it worse (Negative memory) ⛔**.
- Demonstrates how any on-call engineer can teach the team's AI agent in under 30 seconds.

---

## 🛠️ Demo Verification Checklist

- [x] Run `uv run python scripts/demo_check.py` before recording to verify parser assertions pass.
- [x] Verify `.env` has valid `HINDSIGHT_BASE_URL` and `HINDSIGHT_API_KEY`.
- [x] If `GROQ_API_KEY` is omitted, the app uses its deterministic offline writer grounded in recalled memories.
- [x] Keep browser zoom at 110%–120% for crisp readability on 1080p video recordings.
- [x] Microservice live dashboard is viewable at `http://localhost:8080` in a split browser tab.
