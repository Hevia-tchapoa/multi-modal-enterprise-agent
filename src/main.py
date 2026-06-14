"""
FastAPI API exposing the LangGraph agent (Phase 3).

Main endpoint:
    POST /ask  { "question": "..." }  ->  { "answer": "...", "finops": {...} }

On every request, the token cost of the agent loop is computed
(via agent.compute_run_cost) and logged to standard output (FinOps).
"""

import logging
import time

from fastapi import FastAPI
from pydantic import BaseModel

from agent import build_agent_graph, compute_run_cost, extract_text_content

# --------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("finops")


# --------------------------------------------------------------------------
# App + Agent (loaded once at container startup)
# --------------------------------------------------------------------------

app = FastAPI(title="Multi-Modal Enterprise Agent", version="1.0.0")

# The graph is compiled once and reused for all requests
agent_graph = build_agent_graph()


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    finops: dict
    latency_seconds: float


@app.get("/")
def health_check():
    """Health endpoint, useful for Cloud Run."""
    return {"status": "ok", "service": "multi-modal-enterprise-agent"}


@app.get("/debug")
def debug_files():
    """
    Temporary diagnostic endpoint: list the contents of data/ and verify
    whether finances.db is present in the deployed container.
    Remove once diagnostics are complete.
    """
    import os

    cwd = os.getcwd()
    data_path = os.path.join(cwd, "..", "data")
    data_path = os.path.abspath(data_path)

    result = {"cwd": cwd, "data_path": data_path}

    if os.path.exists(data_path):
        result["data_contents"] = os.listdir(data_path)
        finances_path = os.path.join(data_path, "finances.db")
        result["finances_db_exists"] = os.path.exists(finances_path)
        if result["finances_db_exists"]:
            result["finances_db_size_bytes"] = os.path.getsize(finances_path)
    else:
        result["data_contents"] = "data/ directory not found"

    return result


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest):
    """
    Accepts a natural-language question, runs the ReAct agent
    (SQL + vector search), and returns the final answer together with
    the FinOps cost of the execution.
    """
    start_time = time.perf_counter()

    result = agent_graph.invoke({"messages": [("user", request.question)]})

    elapsed = time.perf_counter() - start_time

    final_answer = extract_text_content(result["messages"][-1].content)
    cost = compute_run_cost(result["messages"])

    # --- FinOps logging: exact cost of this agent execution ---
    logger.info(
        "FinOps | question=%r | input_tokens=%d | output_tokens=%d | "
        "total_tokens=%d | cost_usd=%.6f | latency_s=%.2f",
        request.question,
        cost["input_tokens"],
        cost["output_tokens"],
        cost["total_tokens"],
        cost["estimated_cost_usd"],
        elapsed,
    )

    return AskResponse(
        answer=final_answer,
        finops=cost,
        latency_seconds=round(elapsed, 2),
    )