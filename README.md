# Multi-Modal Enterprise Agent

An autonomous AI analyst that answers complex business questions about
**BNP Paribas** by combining structured financial data (SQL) and
unstructured financial reports (Vector Search / RAG).

The agent is built with **LangGraph** (ReAct loop), uses **Qdrant** as a
vector database, **SQLite** for structured data, and **Gemini 1.5 Flash**
as the LLM. It is exposed via a **FastAPI** REST endpoint and can be
containerized with Docker.

---

## 🏗️ Architecture

```
data/raw/*.pdf  ──▶  ETL Pipeline (extraction, cleaning,
                       semantic chunking, embeddings)
                              │
                              ▼
                     Qdrant (vector DB, collection "bnp_reports")
                              │
        ┌─────────────────────┴─────────────────────┐
        │                                            │
   search_vector_db                            execute_sql
   (semantic search +                          (SQLite: finances.db,
    Pydantic metadata filters)                  with error-recovery loop)
        │                                            │
        └─────────────────► LangGraph ReAct Agent ◄─┘
                                    │
                                    ▼
                          FastAPI (POST /ask)
                                    │
                                    ▼
                          JSON answer + FinOps log
                          (token usage & cost per call)
```

### Components

| Component | Technology |
|---|---|
| Vector database | Qdrant (Docker) |
| Embeddings model | `all-MiniLM-L6-v2` (HuggingFace, local) |
| Structured database | SQLite (`finances.db`) |
| Agent framework | LangGraph (ReAct state machine) |
| LLM | Gemini 1.5 Flash (Google AI Studio) |
| API | FastAPI |
| Containerization | Docker |

---

## 📂 Project Structure

```
multi-modal-enterprise-agent/
├── data/
│   ├── raw/                  # Downloaded PDF reports + metadata.json
│   └── finances.db           # SQLite database (generated)
├── src/
│   ├── scrape_bnp_reports.py # Downloads BNP Paribas financial reports
│   ├── etl_pipeline.py       # Cleaning, semantic chunking, embeddings, Qdrant insertion
│   ├── create_sqlite_db.py   # Creates finances.db with structured financial data
│   ├── tools.py              # LangGraph tools: execute_sql, search_vector_db
│   ├── agent.py              # LangGraph ReAct agent + FinOps cost calculation
│   └── main.py               # FastAPI app exposing the agent (POST /ask)
├── docker-compose.yml        # Local Qdrant instance
├── Dockerfile                # Container for the agent + FastAPI
├── requirements.txt          # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore
├── REPORT.md                  # Architecture report, RAGAS eval, cost analysis
└── README.md
```

---

## 🚀 Getting Started

### Prerequisites

- Python 3.11+
- Docker (for running Qdrant locally)
- A free Gemini API key: https://aistudio.google.com/app/apikey

### 1. Clone the repository

```bash
git clone <repo-url>
cd multi-modal-enterprise-agent
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key:

```env
GOOGLE_API_KEY=your_gemini_api_key_here
```

> For **local development**, leave `QDRANT_URL` and `QDRANT_API_KEY`
> unset — the app will connect to `http://localhost:6333` automatically.
>
> To use **Qdrant Cloud** instead (required for Cloud Run deployment,
> since `localhost` is not reachable from the container), set:
> ```env
> QDRANT_URL=https://your-cluster.cloud.qdrant.io:6333
> QDRANT_API_KEY=your_qdrant_api_key
> ```

### 4. Start Qdrant (Docker)

```bash
docker-compose up -d
```

Qdrant dashboard available at: http://localhost:6333/dashboard

### 5. Download the source documents

```bash
python src/scrape_bnp_reports.py
```

This downloads BNP Paribas financial reports (Universal Registration
Documents, Integrated Reports, quarterly Financial Statements, Social
Report) into `data/raw/`, along with a `metadata.json` file containing
structured metadata (`company_name`, `document_type`, `document_year`,
`quarter`).

### 6. Run the ETL pipeline

```bash
python src/etl_pipeline.py
```

This will:
1. Extract text from each PDF
2. Clean the text (remove page numbers, normalize whitespace)
3. Apply **semantic chunking** (groups sentences based on embedding
   similarity, not fixed-size splitting)
4. Generate embeddings using `all-MiniLM-L6-v2`
5. Insert chunks + metadata into the Qdrant collection `bnp_reports`

> 💡 **Tip**: To test on a smaller subset first, generate a reduced
> metadata file with `python src/make_test_metadata.py`, then run:
> `python src/etl_pipeline.py data/raw/metadata_test.json`

### 7. Create the SQLite database

```bash
python src/create_sqlite_db.py
```

This creates `data/finances.db` with four tables: `annual_results`,
`market_capitalization`, `revenue_by_division`, and `credit_ratings`.

### 8. Test the agent directly

```bash
python src/agent.py
```

Runs a sample question through the ReAct loop and prints the final
answer along with token usage and estimated cost (FinOps).

### 9. Run the FastAPI server

```bash
cd src
uvicorn main:app --reload --port 8080
```

### 10. Query the agent

```bash
curl -X POST http://localhost:8080/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What was BNP Paribas net income in 2025?"}'
```

Example response:

```json
{
  "answer": "BNP Paribas' net income (group share) in 2025 was €12,225 million.",
  "finops": {
    "input_tokens": 1240,
    "output_tokens": 85,
    "total_tokens": 1325,
    "estimated_cost_usd": 0.000119
  },
  "latency_seconds": 2.34
}
```

---

## 🛠️ Available Tools (Agent)

### `execute_sql`

Executes read-only SQL (`SELECT`) queries against `finances.db`.
Includes an **error-recovery loop**: if a query fails (syntax error,
unknown table/column), the database schema and the SQL error are
returned to the LLM so it can immediately retry with a corrected query —
no human intervention required.

### `search_vector_db`

Performs semantic search over BNP Paribas financial reports stored in
Qdrant. Before searching, a structured-output LLM call extracts strict
metadata filters (`document_type`, `document_year`, `quarter`) from the
natural language question using a Pydantic schema, narrowing the search
to relevant documents only.

---

## 🐳 Running with Docker

Build and run the agent container locally:

```bash
docker build -t enterprise-agent .
docker run -p 8080:8080 --env-file .env enterprise-agent
```

> Note: when running in Docker, Qdrant must be reachable from inside the
> container. Either run Qdrant via `docker-compose` on the same network,
> or point `QDRANT_URL` / `QDRANT_API_KEY` to a Qdrant Cloud instance.

---

## ☁️ Live Deployment

The agent is deployed and publicly accessible on **Google Cloud Run**:

```
https://enterprise-agent-fsdcqpdzgq-ew.a.run.app
```

### Health check

```bash
curl https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/
```

### Ask a question

```bash
curl -X POST https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What was BNP Paribas net banking income in 2025?"}'
```

PowerShell:

```powershell
$body = @{ question = "What was BNP Paribas net banking income in 2025?" } | ConvertTo-Json -Compress
Invoke-RestMethod -Uri "https://enterprise-agent-fsdcqpdzgq-ew.a.run.app/ask" -Method Post -ContentType "application/json; charset=utf-8" -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

### Redeploying

The deployed version uses **Qdrant Cloud** (free tier) instead of a
local Qdrant instance, since Cloud Run cannot reach `localhost`. To
redeploy after code changes:

```bash
gcloud run deploy enterprise-agent \
  --source . \
  --region europe-west1 \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars "GOOGLE_API_KEY=...,QDRANT_URL=...,QDRANT_API_KEY=..."
```

A `.gcloudignore` file controls which files are uploaded to Cloud
Build — make sure `data/finances.db` is **not** excluded (it is
required by the Dockerfile).

> See `REPORT.md` for the full cost analysis and FinOps details
> (Cloud Run + Gemini usage).

---

## 📊 Data Sources

All financial reports were downloaded from BNP Paribas' official
investor relations page:
https://invest.bnpparibas/recherche/rapports/documents/rapports-financiers-et-sociaux

Documents include:
- Universal Registration Document (URD) and amendments (2024–2025)
- Integrated Reports (2024, 2025)
- Quarterly Financial Statements (Q2 2025, Q4 2025)
- Annual Highlights ("L'Essentiel") (2025, 2026)
- Social Report (2024)

> Note: the full 2025 Universal Registration Document (~930 pages) was
> excluded from the final dataset for local processing time reasons. See
> `REPORT.md` for details.

---

## 📄 License

This project was built as an educational capstone project.