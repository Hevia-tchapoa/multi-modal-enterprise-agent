"""
ReAct agent (Phase 2) built with LangGraph.

Architecture:
    [agent] --(tool_calls?)--> [tools] --> [agent] --> ... --> END
       |
       +--(no tool_calls)--> END

The agent loops between reasoning (LLM) and tool execution until it produces
 a final answer without any additional tool call.

It also computes and logs token cost for each run
(used in Phase 3 for FinOps tracking).
"""

import os
from pathlib import Path
from typing import Annotated, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AnyMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode

from tools import execute_sql, make_search_vector_db_tool


# --------------------------------------------------------------------------
# LLM configuration
# --------------------------------------------------------------------------
# Gemini is used (via GCP / AI Studio) to keep the project within budget.
# The model is injected into search_vector_db for Pydantic filter extraction.

# Load .env from the project root (one level above src/),
# regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

LLM_MODEL_NAME = "gemini-2.5-flash"

api_key = os.environ.get("GOOGLE_API_KEY")
if not api_key:
    raise RuntimeError(
        f"GOOGLE_API_KEY not found. Verify that the .env file exists at "
        f"{PROJECT_ROOT / '.env'} and contains a line like "
        f"GOOGLE_API_KEY=your_key (without spaces or quotes)."
    )

llm = ChatGoogleGenerativeAI(
    model=LLM_MODEL_NAME,
    temperature=0,
    google_api_key=os.environ.get("GOOGLE_API_KEY"),
)

# Build the tools
search_vector_db = make_search_vector_db_tool(llm)
tools = [execute_sql, search_vector_db]

llm_with_tools = llm.bind_tools(tools)


# --------------------------------------------------------------------------
# Define the graph state
# --------------------------------------------------------------------------

class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


SYSTEM_PROMPT = SystemMessage(content="""\
You are an AI financial analyst specialized in BNP Paribas.

You have access to two tools:
- execute_sql: for any NUMERIC question (revenues, results, ratios,
  market capitalization, credit ratings). The database contains data for
  2023, 2024, and 2025.
- search_vector_db: for any QUALITATIVE question (strategy, risks,
  ESG, governance, recent events) from BNP Paribas reports.

If a question combines both aspects (for example: "what was the 2025 net result
and what does the 2025 integrated report say about credit risks?"), use BOTH tools
before answering.

If a tool returns an SQL error, immediately fix the query based on the schema
provided in the error message — do not give an intermediate explanation,
retry directly.

Always answer in English, concisely and factually, citing the exact figures or
passages found.
""")


# --------------------------------------------------------------------------
# Graph nodes
# --------------------------------------------------------------------------

def agent_node(state: AgentState) -> dict:
    """
    Reasoning node: calls the LLM (with access to tools) on the message history.
    The LLM decides whether to answer directly or call one or more tools.
    """
    messages = state["messages"]

    # Add the system prompt only if it is not already present
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SYSTEM_PROMPT] + messages

    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


def should_continue(state: AgentState) -> str:
    """
    Decide whether to continue the ReAct loop (tool call) or finish
    (the LLM produced a final response without tool_calls).
    """
    last_message = state["messages"][-1]

    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END


# --------------------------------------------------------------------------
# Build the graph
# --------------------------------------------------------------------------

def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(tools))

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        should_continue,
        {"tools": "tools", END: END},
    )

    # After tool execution, we always return to the agent
    # (ReAct loop: observation -> new decision)
    graph.add_edge("tools", "agent")

    return graph.compile()


# --------------------------------------------------------------------------
# FinOps: token-cost calculation
# --------------------------------------------------------------------------

# Gemini 1.5 Flash pricing (approximate, USD per million tokens)
# Adjust according to the current GCP pricing when you update REPORT.md
PRICE_PER_M_INPUT_TOKENS = 0.075   # USD / 1M tokens (input)
PRICE_PER_M_OUTPUT_TOKENS = 0.30   # USD / 1M tokens (output)


def compute_run_cost(messages: list) -> dict:
    """
    Walks through the messages produced during the agent run and sums the
    usage tokens reported by the LLM (`usage_metadata` on AIMessage) to
    calculate the total cost of the agent loop.
    """
    total_input_tokens = 0
    total_output_tokens = 0

    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if usage:
            total_input_tokens += usage.get("input_tokens", 0)
            total_output_tokens += usage.get("output_tokens", 0)

    cost_usd = (
        (total_input_tokens / 1_000_000) * PRICE_PER_M_INPUT_TOKENS
        + (total_output_tokens / 1_000_000) * PRICE_PER_M_OUTPUT_TOKENS
    )

    return {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_input_tokens + total_output_tokens,
        "estimated_cost_usd": round(cost_usd, 6),
    }


def extract_text_content(content) -> str:
    """
    Normalizes AIMessage content into a simple text string.

    Gemini 2.5 sometimes returns `content` as a list of blocks
    (for example: [{'type': 'text', 'text': '...', 'extras': {...}}])
    instead of a plain string. This function extracts and concatenates the
    text from all blocks of type 'text'.
    """
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)

    return str(content)


# --------------------------------------------------------------------------
# Local test entry point
# --------------------------------------------------------------------------

if __name__ == "__main__":
    app = build_agent_graph()

    question = (
        "What was the revenue of the 'Retail' division in 2025?"
    )

    print(f"Question: {question}\n")

    result = app.invoke({"messages": [("user", question)]})

    final_answer = extract_text_content(result["messages"][-1].content)
    print(f"\n=== Final answer ===\n{final_answer}")

    cost = compute_run_cost(result["messages"])
    print("\n=== FinOps ===")
    print(f"Input tokens  : {cost['input_tokens']}")
    print(f"Output tokens : {cost['output_tokens']}")
    print(f"Total tokens  : {cost['total_tokens']}")
    print(f"Estimated cost: ${cost['estimated_cost_usd']}")