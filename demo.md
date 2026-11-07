# 🎬 Incident Memory Copilot + OneUptime — Complete Video Demo Guide

> **Hackathon Pitch Video Guide & Script**  
> **Topic:** AI Agents That Learn Using Hindsight Memory  
> **Target Video Length:** 3–4 minutes  

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
 │     Hindsight Memory Copilot (Streamlit App)           │
 │   • Baseline (Without Memory): Generic bad advice      │
 │   • Hindsight Memory: Recalls INC-2139 & INC-2041      │
 │   • Do First: Exact rollback command                   │
 │   • Do NOT Do: Warns against scaling and restarting    │
 │   • Close the Loop: retain() resolution for next time  │
 └────────────────────────────────────────────────────────┘
```

---

## ⚡ 1-Minute Quick Start (Before Recording)

Open three terminal windows:

### Terminal 1: Run the Real Target Microservice
```bash
uv run python examples/real_world_app/server.py
```
*(Runs on `http://localhost:8080`. You can view its web dashboard in your browser).*

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

> **Alternative (Single Command):**  
> Simply run `./scripts/start_demo.sh` to launch all three automatically!

---

## ⏱️ Video Demo Timeline & Screen Walkthrough

| Timestamp | Visual Screen | Key Action | What to Say / Highlight |
|---|---|---|---|
| **0:00 – 0:35** | Streamlit Sidebar & Tab 1 | Click **"Seed past incidents + policies"** | The Problem: On-call engineers waste 20 minutes searching wikis during an outage. Introduce Northwind Pay history. |
| **0:35 – 1:10** | Tab 2: **OneUptime Service Monitor & Lab** | Click **"📦 Local checkout-api (:8080)"** → Click **"⚡ Probe Endpoint Now"** | Show the live microservice health check returning `🟢 HTTP 200 OK (2.4ms)`. |
| **1:10 – 1:45** | Tab 2 (Chaos Outage) | Click **"💥 Break Service (Trigger Outage)"** → Click **"⚡ Probe Endpoint Now"** | Service breaks with connection pool exhaustion! Probe returns `🔴 HTTP 503`. OneUptime declares Incident `INC-OU9001`. |
| **1:45 – 2:45** | Tab 2 (War Room) | Click **"🧠 Investigate Outage with Hindsight Copilot"** | **THE HEADLINE:** Compare side-by-side. Left column gives generic harmful advice. Right column cites **INC-2139**, warns against restarting/scaling, and provides exact rollback command. |
| **2:45 – 3:15** | Tab 2 / Microservice | Click **"🔄 Recover All Services"** → Click **"✅ Resolve Outage & Retain Post-Mortem"** | Apply rollback. Heal the service. Retain the post-mortem in Hindsight with UTC timestamp (`retain()`). |
| **3:15 – 3:45** | Tab 5: **Reflect** | Select *"Which remediation actions have repeatedly made things worse?"* → Click **Reflect** | Show Hindsight's global reasoning over all 11+ incidents and policies. |
| **3:45 – 4:00** | Tab 6: **Real-World Blueprint** | Scroll through the Docker Compose & OneUptime Workflow blueprint | Show how easy it is to drop this into real production Kubernetes / OneUptime environments. |

---

## 🎙️ Word-for-Word Video Script

### Segment 1: The Problem & The Hook (0:00 – 0:35)
`[SHOW SCREEN: Streamlit dashboard at http://localhost:8501]`

> *"Hi everyone! Welcome to our demonstration of **Incident Memory Agent** — an on-call AI copilot that learns using Hindsight memory.*
>
> *Every on-call engineer knows this pain: an alert fires at 2:00 AM. Runbooks tell you to **restart the service and scale replicas**. But in complex distributed systems, generic runbooks are dangerous. What actually saves production is **post-mortem memory** — knowing what caused this last time, what fixed it, and crucially, what made it worse.*
>
> *Let's seed our team's past 11 incidents and 4 operational policies into our Hindsight memory bank."*  
> `[CLICK: 'Seed past incidents + policies' in the sidebar]`

---

### Segment 2: Real-World OneUptime Monitoring (0:35 – 1:10)
`[SHOW SCREEN: Click Tab 2 '🛰 OneUptime Service Monitor & Lab']`

> *"Next, we've integrated **OneUptime**, the popular open-source monitoring and status page platform. OneUptime continuously checks our live microservices.*
>
> *Right here in terminal 1, we are running Northwind Pay's actual `checkout-api` microservice. Let's probe its synthetic `/health` endpoint.*
>
> `[CLICK: '📦 Local checkout-api (:8080)']`  
> `[CLICK: '⚡ Probe Endpoint Now']`
>
> *As you can see, our monitor returns **HTTP 200 OK** in 2.1 milliseconds. The service is fully operational."*

---

### Segment 3: Injecting Outage & Detection (1:10 – 1:45)
`[SHOW SCREEN: Outage Lab Section]`

> *"Now, let's simulate a real production disaster: deploy `v3.4.1` rolls out, lowers the Hikari connection pool, and adds a blocking foreign-exchange lookup. Let's break the service!"*  
> `[CLICK: '💥 Break Service (Trigger Outage)']`
>
> *Now let's probe the endpoint again:*  
> `[CLICK: '⚡ Probe Endpoint Now']`
>
> *Boom! The synthetic probe immediately fails with **HTTP 503: Service Unavailable**. OneUptime instantly declares a critical outage and raises Incident **INC-OU9001**."*

---

### Segment 4: The Headline — Memory vs No Memory (1:45 – 2:45)
`[SHOW SCREEN: War Room Section]`

> *"Now comes the magic. Let's click **'Investigate Outage with Hindsight Copilot'**."*  
> `[CLICK: '🧠 Investigate Outage with Hindsight Copilot']`
>
> *Look at this side-by-side comparison:*
>
> *On the **Left (Without Memory)**: The standard LLM with generic prompts says: 'Restart pods, scale up to 20 replicas.' If you do that, you crash the entire database.*
>
> *On the **Right (With Hindsight Memory)**: The agent consulted team history. It immediately identifies the pattern from **INC-2139** and **INC-2041**.*
>
> *Look at **Do First**: It gives the exact rollback command:*  
> `deploy rollback --service checkout-api --to v3.4.0`  
> *and tells us to check `hikaricp.connections.pending`.*
>
> *And look at **Do NOT do**: It explicitly warns: 'Do NOT scale replicas — last time that saturated Postgres to 480 connections. Do NOT restart pods — the pool re-exhausts in 3 minutes.'*
>
> *And under **Escalate**, it automatically pages Marcus Bell, the checkout lead, citing team policy POL-104."*

---

### Segment 5: Healing & Closing the Loop (2:45 – 3:15)
`[SHOW SCREEN: War Room Action Buttons]`

> *"Let's apply the rollback fix."*  
> `[CLICK: '🔄 Recover All Services']`
>
> *The checkout service is healed! Let's click **'Resolve Outage & Retain Post-Mortem in Memory'**.*  
> `[CLICK: '✅ Resolve Outage & Retain Post-Mortem in Memory']`
>
> *Hindsight immediately retains this outcome using `store.retain()`. The loop is closed: our AI agent just learned from this resolution, and the very next incident will cite this experience."*

---

### Segment 6: Deep Cross-Incident Reflection (3:15 – 3:45)
`[SHOW SCREEN: Tab 5 '🔎 Reflect']`

> *"Finally, what about institutional knowledge across shifts? In the **Reflect** tab, we don't just do top-k retrieval; we reason across the entire memory bank.*
>
> *Let's select: **'Which remediation actions have repeatedly made things worse?'** and hit **Reflect**."*  
> `[CLICK: 'Reflect']`
>
> *Hindsight synthesizes patterns across every incident in the company: highlighting connection leaks, aggressive pod restarts, and replica storms. This is the onboarding and post-mortem review nobody ever has time to write."*

---

### Segment 7: Real-World Blueprint & Conclusion (3:45 – 4:00)
`[SHOW SCREEN: Tab 6 '🔌 Real-World Integration Blueprint']`

> *"In Tab 6, we've provided the complete production blueprint: Docker Compose setups for OneUptime, Workflow webhook templates, and drop-in health endpoints for Express, FastAPI, and Kubernetes.*
>
> *With Hindsight and OneUptime, outages stop being recurring nightmares — they become team memory. Thank you!"*

---

## 🛠️ Demo Tips & Verification Checklist

- [x] Run `uv run python scripts/demo_check.py` before recording to verify all assertions pass.
- [x] Make sure Hindsight is running and `.env` has `HINDSIGHT_BASE_URL` + `HINDSIGHT_API_KEY`. `GROQ_API_KEY` is optional (deterministic writer).
- [x] Keep terminal font large (16-18pt) and browser zoom at 110%–125% for high readability on YouTube / Loom.
- [x] Have the microservice dashboard (`http://localhost:8080`) open in a split browser tab if you want to show the live database connection pool bars!
