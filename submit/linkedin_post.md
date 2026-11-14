# LinkedIn Social Post

> **Style:** Andrej Karpathy (Direct, technical, first-principles, candid)  
> **Character Count:** ~780 characters (Strictly under 800 character limit)  
> **Important:** Post the article/repo link in the main post, and drop the Hindsight GitHub link in the first comment!

---

### Main Post Text (Copy & Paste)

Most AI agents deployed for SRE fail because they suffer from amnesia.

When an alert fires at 2 AM, generic LLMs give textbook advice: "restart pods, scale replicas". In distributed systems, that exact command often saturates databases and turns a 4-minute blip into a 40-minute site outage.

We gave our on-call agent long-term recall using Hindsight agent memory. The key technical shift:

1. Negative memory: The agent indexes what made past outages WORSE, not just what fixed them.
2. Grounded actions: Every remediation command must match a verbatim historical post-mortem in Hindsight. Zero hallucinated flags.
3. Before vs After: On connection pool exhaustion, baseline LLM said "scale to 20 replicas". With Hindsight, it warned "Do NOT scale—last time that killed Postgres" and gave the proven rollback command in 5s.

Code: https://github.com/YashwanthTT/RecallOps

#AIAgents #AgentMemory #LLM #SRE #Hindsight

---

### First Comment (Post Immediately After Publishing)

```text
Here is the Hindsight repo if you want to check it out: https://github.com/vectorize-io/hindsight
```
