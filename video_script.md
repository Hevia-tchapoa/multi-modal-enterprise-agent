# Video Demo Script — Multi-Modal Enterprise Agent

> Target length: ~3 minutes.
> Live endpoint: https://enterprise-agent-fsdcqpdzgq-ew.a.run.app
>
> ⚠️ Each `/ask` call consumes Gemini quota (20 req/day per API key,
> ~2-4 calls per question via the ReAct loop). Record in **one take**
> if possible, and don't re-run questions unnecessarily before
> recording.

---

## Before recording — preparation checklist

- [ ] Open a browser tab with the **Qdrant Cloud dashboard**
      (cluster `bb2f3cda-...`, collection `bnp_reports`, 12,100 points)
- [ ] Open a browser tab with **Cloud Run console** showing the
      `enterprise-agent` service (green checkmark, URL visible)
- [ ] Open a terminal (PowerShell) at the project root, font size large
      enough to read on screen
- [ ] Have `REPORT.md` open in VS Code, scrolled to Section 3 (RAGAS
      table) and Section 4 (Cost table)
- [ ] Decide in advance: do ONE live `/ask` call during recording (to
      show it really works), and PRESENT the other 4 results from
      `REPORT.md` as already-collected evidence (don't re-run them live)

---

## Step 1 — Intro (15s)

**Say:**
> "Hi, I'm Fabiola. This is my Multi-Modal Enterprise Agent — an AI
> analyst that answers business questions about BNP Paribas by
> combining SQL queries on structured financial data with semantic
> search over financial reports."

**Show:** project structure in VS Code (`src/`, `data/`, `README.md`,
`REPORT.md`) — a few seconds, no need to open files yet.

---

## Step 2 — Architecture overview (30s)

**Say:**
> "The system has two data sources: a SQLite database with structured
> financials — net income, market cap, revenue by division, and credit
> ratings — and a Qdrant Cloud vector database containing twelve
> thousand one hundred chunks from eleven BNP Paribas reports, each
> tagged with metadata like document type, year, and quarter."

**Show:** switch to the Qdrant Cloud dashboard tab — point at the
`bnp_reports` collection and the **12,100 points** count.

**Say:**
> "A LangGraph ReAct agent decides, for each question, whether to query
> SQL, search the vector database, or both — and the whole thing is
> deployed on Google Cloud Run."

**Show:** switch to the Cloud Run console tab — point at the service
URL and the green "healthy" status.

---

## Step 3 — Live demo: simple SQL question (30s)

**Run (PowerShell), live on screen:**
```powershell
$body = @{ question = "What was BNP Paribas net banking income in 2025?" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

**Say while it runs (≈3s latency):**
> "Here the agent recognizes this is a numerical question, writes a SQL
> query against the annual_results table, and queries our live Cloud
> Run deployment."

**Say on the result:**
> "And there it is — €51,223 million, the exact 2025 figure, returned
> with the token usage and cost for this call."

*(Point at the `finops` field in the JSON response: tokens + cost)*

---

## Step 4 — Walk through additional results from REPORT.md (45s)

> Don't re-run these live — present them as already-validated results
> to save quota and time.

**Switch to `REPORT.md`, Section 3 (RAGAS table).**

**Say:**
> "I ran five test questions against the agent and graded each one for
> faithfulness and relevance. For example, this hybrid question asked
> for the 2025 net income AND the strategic priorities from the
> Integrated Report — the agent correctly called both tools in a single
> ReAct loop: execute_sql for the figure, search_vector_db for the
> qualitative context, and merged both into one coherent answer."

*(Point at row Q3 in the table: €12,225 million + strategic plan
2027-2030, People Strategy, CIB focus)*

**Say (honest limitations — shows engineering maturity):**
> "I also found two real limitations. For Q4, asking for both Moody's
> and S&P ratings, the agent retrieved both rows from SQL but only
> reported Moody's in its final answer — an incomplete synthesis issue.
> And for Q5, I asked about the 'Retail' division, which doesn't exist
> in my schema — only CIB, CPBS, and IPS. The agent silently mapped
> 'Retail' to CPBS without flagging that this was an interpretation, not
> an exact match. Both are documented in the report as planned fixes:
> strengthening the prompt to report all SQL rows, and injecting valid
> category values into the schema description."

---

## Step 5 — Error recovery loop (30s)

> If you have quota left for ONE more live call, demonstrate this live.
> Otherwise, describe the mechanism using the code in `tools.py`.

**Option A — Live (if quota allows):**
```powershell
$body = @{ question = "What was the total dividends table value for division XYZ in 1999?" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

**Say:**
> "This references a table or year that doesn't exist. Behind the
> scenes, the agent receives the exact SQL error plus the full schema,
> and retries with a corrected query — no human intervention needed."

**Option B — Code walkthrough (no quota used):**

Open `src/tools.py`, scroll to the `execute_sql` function's `except
sqlite3.Error` block.

**Say:**
> "Here's the error-recovery loop: if the SQL query fails, we return the
> exact error message plus the full database schema back to the LLM.
> Because the LangGraph loop always returns from 'tools' to 'agent',
> the model sees this error and immediately retries with a corrected
> query."

---

## Step 6 — FinOps & wrap-up (20s)

**Switch to `REPORT.md`, Section 4 (Cost Analysis table).**

**Say:**
> "Every call logs token usage and cost. Across my five test questions,
> the average cost was about $0.0004 per query — projecting to roughly
> 4 cents for 100 queries. This is running live on Google Cloud Run,
> backed by Qdrant Cloud, with a $5 budget alert configured as a
> safeguard — actual GCP spend has stayed at zero beyond the free
> tier."

**Say (closing):**
> "Thanks for watching — the full code, architecture report, and RAGAS
> evaluation are in the GitHub repo, along with the live Cloud Run
> endpoint."

---

## 📝 Final recording notes

- [ ] Total target: ~2:45–3:00
- [ ] Record in 1080p (Loom or OBS)
- [ ] Test the ONE live `/ask` call (Step 3) right before recording to
      confirm it still works, then record in one take without
      re-testing again
- [ ] Keep terminal font large (16pt+) for readability
- [ ] Have the GitHub repo URL visible/mentioned at the end