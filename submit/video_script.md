# 🎬 Short Video Script (App-Only, ~75 Seconds)

> **Target Video Length:** 60–90 seconds (~75s sweet spot)  
> **Visual Focus:** Screen recording of the **Streamlit Web App only** (`http://localhost:8501`) in full screen.  
> **No Webcam / No Terminals Needed**: You don't need any terminal windows, split screens, or webcam overlays. Everything happens directly inside the app interface.  
> **Sidebar Not Needed**: The entire walkthrough runs from the main panels and top navigation bar—no sidebar interaction required.

---

## 🎯 5 Crisp YouTube Titles

1. **Why Your AI SRE Agent Is Crashing Production (And How Memory Fixes It)**
2. **I Stopped Our AI Agent From Killing Our Database With Hindsight**
3. **Generic Runbooks Told It to Scale. Hindsight Memory Saved The Cluster.**
4. **Building an AI Incident Copilot That Learns From Past Outages**
5. **How We Gave Our On-Call Agent Long-Term Memory (Live Demo)**

---

## 🎙️ 75-Second Recording Script

### Scene 1: The Hook (0:00 – 0:15)
**[SCREEN: Browser showing full-screen Streamlit app at `http://localhost:8501`, on the "Briefing" tab. Mouse hovers near the title.]**

> *"Most AI agents for on-call triage have severe amnesia. When an alert fires at 2 AM, they give textbook advice—restart pods, scale replicas. But what if doing that previously took down your entire database? Today, let's see how Hindsight solves this."*

---

### Scene 2: 1-Click Incident Briefing & Negative Memory (0:15 – 0:45)
**[SCREEN ACTION: Under 'Simulate an alert', click the 'Run briefing →' button on the first card: `checkout-api 502 spike (connection pool)`. The side-by-side comparison renders. Scroll down smoothly to show both columns.]**

> *"With one click, let's simulate a connection pool spike on our checkout service.*
>
> *Look at the side-by-side comparison.*
>
> *On the left, a standard LLM agent says: 'Scale your pods to 20 replicas and restart all containers.'*
>
> *If an on-call engineer runs that, it saturates PostgreSQL and tips the whole cluster into hard failure.*
>
> *Now look at the right: our Hindsight-grounded copilot recalled past incident INC-2139.*
>
> *Right in bold red under **⛔ Avoid this**, it explicitly warns: 'Do NOT scale replicas—in INC-2139, scaling checkout-api saturated PostgreSQL with 480 connections. Do NOT restart pods.'*
>
> *And under **🚑 Do first**, it gave us the exact tested rollback command."*

---

### Scene 3: Cross-Incident Synthesis with Reflect (0:45 – 1:05)
**[SCREEN ACTION: Click the 'Reflect' tab in the top navigation bar. Click the pill: "Which remediation actions have repeatedly made things worse?", then click the '🧭 Reflect across bank' button. Scroll to show the synthesized findings.]**

> *"Even better: with Hindsight’s `reflect()` API, we can query our entire incident history.*
>
> *When we ask which actions have repeatedly made things worse, it synthesizes historical post-mortems across every service—surfacing dangerous anti-patterns like aggressive pod restarts and uncoordinated cache flushes before they strike again."*

---

### Scene 4: Wrap-Up & CTA (1:05 – 1:20)
**[SCREEN ACTION: Click back to the 'Briefing' tab or scroll up to show the 'Northwind Pay · Incident Memory Agent' banner.]**

> *"Negative memory is the missing piece in autonomous engineering agents. Don't let your AI repeat catastrophic production mistakes.*
>
> *Check out Hindsight and our open-source repo in the description below. Thanks for watching!"*

---

## 💡 Quick Recording Tips

1. **Window Size**: Maximize your browser window (or record at 1920×1080).
2. **Zoom**: Set browser zoom to 110% or 125% (`Cmd +` or `Ctrl +`) so text and cards look large and crisp on mobile.
3. **Sidebar**: You can leave the sidebar closed/hidden—the entire demo runs seamlessly from the main screen and top navigation bar. (If you ever want to open it, click the small `>` arrow in the top-left corner or press `[`).
4. **Duration**: Read at a steady, natural pace. The entire video will be ~70 to 80 seconds—perfect for high retention.
