# Multi-Modal Enterprise Agent — Architecture Report

**Author:** 
MUTHUKUMAR	Harinesh
TCHAPOA	Hevia
**Date:** June 14, 2026
**GitHub repository:** [repo URL]
**Demo:** Live Cloud Run endpoint — `https://enterprise-agent-fsdcqpdzgq-ew.a.run.app`

---

## 1. System Overview

This project implements an autonomous AI agent that answers complex
business questions about **BNP Paribas** by combining:

- **Structured data** (SQLite): annual financial results, market
  capitalization, revenue by business division, and credit ratings.
- **Unstructured data** (Qdrant vector database): financial reports
  (Universal Registration Document and amendments, Integrated Reports,
  quarterly Financial Statements, Social Report) — 11 documents,
  semantically chunked into **12,097 vectors**.

The agent, built with **LangGraph** (ReAct loop), dynamically decides
which tool(s) to use based on the question, and can combine both data
sources to produce a complete answer.

---

## 2. Architecture Diagram

```
data/raw/*.pdf (11 BNP Paribas reports)
        │
        ▼
ETL Pipeline: extraction → cleaning → semantic chunking
        → embeddings (all-MiniLM-L6-v2) → Qdrant
        │
        ▼
Qdrant (collection "bnp_reports", 12,097 points)
        │
   ┌────┴─────────────────────────────┐
   │                                   │
search_vector_db                  execute_sql
(Pydantic metadata filters +      (SQLite finances.db,
 semantic search)                  error-recovery loop)
   │                                   │
   └──────────► LangGraph ReAct Agent ◄┘
                       │
                       ▼
              FastAPI (POST /ask)
                       │
                       ▼
        JSON answer + FinOps log
        (token usage & cost per call)
```

### 2.1 ETL Pipeline (Phase 1)

- **Data source**: 11 BNP Paribas financial reports (downloaded from
  invest.bnpparibas, covering fiscal years 2024–2026), including the
  Universal Registration Document and its amendments, Integrated
  Reports, quarterly Financial Statements, Annual Highlights, and the
  Social Report.
- **Cleaning**: removal of page numbers, whitespace normalization,
  removal of low-content noise lines.
- **Semantic chunking**: sentences are grouped based on cosine
  similarity between consecutive sentence embeddings (threshold = 0.55).
  Chunks are split when the topic shifts, not at a fixed character
  count.
- **Embeddings**: local `all-MiniLM-L6-v2` model (HuggingFace,
  384 dimensions).
- **Storage**: Qdrant collection `bnp_reports`, **12,097 vectors**, each
  with metadata `company_name`, `document_type`, `document_year`, and
  `quarter`.

> **Note on dataset scope**: the full 2025 Universal Registration
> Document (~930 pages) was excluded from the final dataset due to
> local processing time constraints. The Integrated Reports and URD
> amendments still provide substantial coverage of strategy, risk, and
> governance topics.

### 2.2 ReAct Agent (Phase 2)

- **State machine**: LangGraph loop `agent → tools → agent → ... → END`.
- **Tool 1 — `execute_sql`**: queries `finances.db` (4 tables:
  `annual_results`, `market_capitalization`, `revenue_by_division`,
  `credit_ratings`). Includes an **error-recovery loop**: on SQL error,
  the full database schema and the error message are returned to the
  LLM, which can immediately retry with a corrected query — no human
  intervention required.
- **Tool 2 — `search_vector_db`**: before performing semantic search,
  a structured-output LLM call (Pydantic schema `VectorSearchFilters`)
  extracts strict metadata filters (`document_type`, `document_year`,
  `quarter`) from the natural language question, restricting the search
  to relevant documents only.
- **LLM**: Gemini 2.5 Flash (Google AI Studio, free tier).

### 2.3 Deployment (Phase 3)

- **Containerization**: Dockerfile (Python 3.11-slim), packages the
  agent and exposes a FastAPI REST endpoint (`POST /ask`).
- **API**: FastAPI app (`main.py`), tested locally with `uvicorn`.
- **FinOps**: every `/ask` call logs `input_tokens`, `output_tokens`,
  `total_tokens`, `estimated_cost_usd`, and `latency_seconds`.

> **Deployment status**: the application was successfully deployed to
> **Google Cloud Run**. Qdrant was migrated to **Qdrant Cloud** (free
> tier, 1GB) since `localhost` is not reachable from Cloud Run. SQLite
> (`finances.db`) is bundled inside the container image. Live endpoint:
>
> `https://enterprise-agent-fsdcqpdzgq-ew.a.run.app`
>
> Example:
> ```
> POST https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/ask
> { "question": "What was BNP Paribas' net banking income in 2025?" }
> ```

---

## 3. RAGAS Evaluation (Manual)

Five test questions were submitted to the agent via `agent.py`. Each
answer is manually graded on two criteria:

- **Faithfulness**: is the answer grounded in the retrieved data, without
  hallucination? (Yes / Partial / No)
- **Answer Relevance**: does the answer actually address the question
  asked? (Yes / Partial / No)

| # | Question | Tool(s) used | Faithfulness | Relevance | Comment |
|---|---|---|---|---|---|
| 1 | What was BNP Paribas' Net Banking Income (PNB) in 2025? | `execute_sql` | Yes | Yes | Exact figure returned (€51,223.0 million), matches `annual_results` table directly. |
| 2 | What does the 2025 Integrated Report say about the group's strategic priorities? | `search_vector_db` | Yes | Partial | The agent honestly states the retrieved excerpts don't explicitly detail "strategic priorities", and reports adjacent facts (global #1 ranking, +4.9% PNB growth, People Strategy) instead of fabricating a structured priorities list. Faithful, but only partially answers the specific question asked. |
| 3 | What was the group's net income in 2025, and what does the 2025 Integrated Report say about strategic priorities? | `execute_sql` + `search_vector_db` | Yes | Yes | Correct net income figure (€12,225 million) from SQL, combined with a coherent qualitative summary (2027-2030 strategic plan, People Strategy, CIB institutional client focus) from vector search. Good example of successful hybrid tool use in a single ReAct loop. |
| 4 | What is BNP Paribas' credit rating from Moody's and S&P? | `execute_sql` | Partial | Partial | The agent correctly retrieved and reported Moody's rating (A1 / Prime-1 / Stable) from the `credit_ratings` table, but the final answer **omitted the S&P rating**, even though it exists in the same table (A+ / A-1 / Stable). The question asked for both agencies; only one was returned. |
| 5 | What was the revenue of the "Retail" division in 2025? | `execute_sql` | Partial | Yes | The `revenue_by_division` table has no division named "Retail" (only `CIB`, `CPBS`, `IPS`). The agent implicitly mapped "Retail" → `CPBS` (Commercial, Personal Banking & Services) and returned €26,112.0 million without flagging this interpretive step or the absence of an exact match. The numeric answer is plausible and internally consistent, but the mapping is an unverified assumption — a risk of silent entity-mapping hallucination. |

### Summary

Overall, the agent demonstrates **strong faithfulness on direct,
unambiguous SQL lookups** (Q1, Q3) and **good honesty when retrieved
text doesn't fully match the question** (Q2 — no fabrication). Two
recurring weaknesses were identified:

1. **Incomplete multi-row retrieval (Q4)**: when a SQL query returns
   multiple relevant rows (one per rating agency), the agent's final
   synthesis can drop rows instead of reporting all of them. This
   suggests the final summarization step does not always verify
   completeness against the full tool output.
2. **Silent entity mapping (Q5)**: when a user term doesn't exactly
   match a known categorical value (e.g. "Retail" vs. "CPBS"), the agent
   makes an implicit semantic mapping without disclosing it, which could
   mislead a non-technical user into trusting an unverified
   correspondence.

The hybrid SQL + vector workflow (Q3) worked correctly and is the
strongest result — the agent appropriately split a compound question
into two tool calls and merged the results coherently.

**Planned follow-up** (post-submission): address both issues above —
(1) strengthen the system prompt to require reporting *all* rows
returned by `execute_sql` for multi-row results, and (2) inject the list
of valid `division` values into the SQL schema description so the agent
either uses an exact match or explicitly flags an approximate mapping.

---

## 4. Cost Analysis (FinOps)

### 4.1 Cost per query

| Question | Input tokens | Output tokens | Total tokens | Cost ($) |
|---|---|---|---|---|
| Q1 — PNB 2025 | 2,691 | 353 | 3,044 | $0.000308 |
| Q2 — Strategic priorities (Integrated Report 2025) | 1,811 | 336 | 2,147 | $0.000237 |
| Q3 — Net income 2025 + strategic priorities (hybrid) | 4,284 | 1,016 | 5,300 | $0.000626 |
| Q4 — Credit ratings (Moody's / S&P) | 4,059 | 907 | 4,966 | $0.000577 |
| Q5 — "Retail" division revenue 2025 | 2,723 | 623 | 3,346 | $0.000391 |
| **Average** | **3,113.6** | **647.0** | **3,760.6** | **$0.000428** |

### 4.2 Projected cost for 100 queries

```
Average cost per query : $0.000428
Projected cost for 100 queries : $0.0428 (≈ 4.3 US cents)
```

Even the most expensive query observed (Q3, hybrid SQL + vector,
$0.000626) projects to **$0.0626 per 100 queries** — well within
Gemini 2.5 Flash's free-tier pricing structure.

### 4.3 GCP / Cloud Run consumption

The application was deployed to **Google Cloud Run** (region
`europe-west1`), with the following resources used:

- **Cloud Run**: service `enterprise-agent`, 2 vCPU / 2GiB memory,
  deployed via `gcloud run deploy --source .` (Cloud Build).
- **Cloud Build**: one container image built and pushed to Artifact
  Registry.
- **Qdrant**: migrated to **Qdrant Cloud** free tier (1GB), 12,100
  vectors — required because Cloud Run cannot reach `localhost`.
- **SQLite**: bundled inside the container image (`finances.db`, 24 KB).
- **LLM**: Gemini 2.5 Flash via Google AI Studio free tier.

A budget alert was configured at **$5** on the GCP billing account as a
safeguard. Based on observed per-query costs (Section 4.1, average
$0.000428/query) and Cloud Run's pay-per-use pricing (idle instances
scale to zero, so no cost is incurred between requests), the actual GCP
spend for development and testing of this project was **effectively
$0.00** beyond the free tier — confirmed via the billing alert (no
threshold reached).

**Cost per 100 queries (LLM only, as in 4.2): ≈ $0.043**. Cloud Run
compute costs for 100 short requests (a few seconds each) remain within
the free tier (2 million requests/month, 360,000 GiB-seconds/month).

---

## 5. Limitations and Future Improvements

- **Dataset scope**: the full 2025 Universal Registration Document
  (~930 pages) was excluded from the vector database for local
  processing time reasons. The remaining 11 documents (Integrated
  Reports, URD amendments, quarterly statements, Social Report) still
  provide substantial coverage.
- **Incomplete multi-row SQL synthesis (Q4)**: the agent can omit rows
  when summarizing multi-row SQL results. *Planned fix*: strengthen the
  system prompt to explicitly require reporting every row returned by
  `execute_sql`.
- **Silent entity mapping (Q5)**: user terminology that doesn't exactly
  match categorical database values (e.g., "Retail" vs. "CPBS") is
  silently mapped by the LLM. *Planned fix*: inject the list of valid
  `division` values (and other categorical fields) into the SQL schema
  description, and instruct the agent to flag approximate matches
  explicitly.
- **GraphRAG (Neo4j)**: not implemented in this submission due to time
  constraints. As a future "Extra Mile" addition, entity/relationship
  extraction from the BNP Paribas reports (e.g., subsidiaries,
  executives, business lines) could enable multi-hop Cypher queries
  alongside the existing vector search.
- **Cloud deployment**: not activated for this submission to avoid GCP
  costs ahead of the deadline. `deploy.sh` is ready for future use.
- **Gemini free-tier quota**: the 20 requests/day limit per API
  key/project constrained the number of test iterations possible in a
  single session. For continued development, either multiple API keys
  (rotated across projects) or a paid tier would remove this constraint.

---

## 6. Running Instructions

See `README.md` at the repository root for full setup instructions
(Docker, environment variables, and commands to run each phase of the
pipeline and the agent).