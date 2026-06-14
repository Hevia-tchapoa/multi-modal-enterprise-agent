"""
Tools for the ReAct agent (Phase 2).

Tool 1 - execute_sql:
    Executes a SQL query on the SQLite database finances.db.
    Includes an error-recovery loop: if the query fails (SQL syntax error,
    missing table/column, etc.), the error is returned to the LLM together
    with the database schema so it can correct the query.

Tool 2 - search_vector_db:
    Performs semantic search in Qdrant. Before querying, it uses a structured
    LLM (via Pydantic / instructor-style with_structured_output) to extract
    strict filters (company_name, document_type, document_year, quarter)
    from the natural-language question.
"""

import os
import sqlite3
from typing import Optional, Literal
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field

from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue
from sentence_transformers import SentenceTransformer


# --------------------------------------------------------------------------
# Shared configuration
# --------------------------------------------------------------------------

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
SQLITE_DB_PATH = str(_PROJECT_ROOT / "data" / "finances.db")


COLLECTION_NAME = "bnp_reports"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# Qdrant Cloud: URL and API key read from environment variables
QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY")  # None locally without auth

# Loaded once at module startup and reused by both tools
_embedder = SentenceTransformer(EMBEDDING_MODEL_NAME)
_qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


# --------------------------------------------------------------------------
# SQL schema of the database (given to the LLM to write correct queries,
# and returned on error to help it recover)
# --------------------------------------------------------------------------

SQL_SCHEMA_DESCRIPTION = """
Available tables in finances.db:

1. annual_results(id, company_name, year, produit_net_bancaire_meur,
   resultat_brut_exploitation_meur, resultat_net_part_groupe_meur,
   benefice_net_par_action_eur, rentabilite_fonds_propres_pct)
   -- Annual group financial results (2023, 2024, 2025)

2. market_capitalization(id, company_name, date, market_cap_md_eur)
   -- Market capitalization as of 31/12 each year

3. revenue_by_division(id, company_name, year, division,
   revenue_share_pct, revenue_meur)
   -- Revenue split by business line: CIB, CPBS, IPS (2025)

4. credit_ratings(id, company_name, agency, long_term_rating,
   short_term_rating, outlook, review_date)
   -- Credit ratings by agency (S&P, Fitch, Moody's, DBRS)

All tables contain company_name = 'BNP Paribas'.
"""


# --------------------------------------------------------------------------
# Tool 1 : execute_sql (avec error-recovery)
# --------------------------------------------------------------------------

MAX_SQL_RETRIES = 3


@tool
def execute_sql(query: str) -> str:
    """
    Executes a read-only SQL query (SELECT) on finances.db and returns the
    result as text.

    The database contains BNP Paribas financial data:
    annual results, market capitalization, revenue by business line,
    and credit ratings.

    If the query fails (syntax error, missing table/column, etc.), the exact
    error message and the full database schema are returned so the agent can
    immediately correct the query.

    Args:
        query: A valid SQL query (SELECT only).
    """
    # Basic safety: only read-only queries are allowed
    normalized = query.strip().lower()
    if not normalized.startswith("select"):
        return (
            "ERROR: only SELECT queries are allowed.\n\n"
            f"Database schema:\n{SQL_SCHEMA_DESCRIPTION}"
        )

    try:
        conn = sqlite3.connect(SQLITE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(query)

        columns = [desc[0] for desc in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "The query executed successfully but returned no rows."

        # Simple tabular text formatting
        header = " | ".join(columns)
        separator = "-" * len(header)
        body = "\n".join(" | ".join(str(value) for value in row) for row in rows)

        return f"{header}\n{separator}\n{body}"

    except sqlite3.Error as e:
        # ----- ERROR-RECOVERY LOOP -----
        # Return the exact SQL error and the schema so that the agent can
        # immediately reformulate a corrected query without human intervention.
        return (
            f"SQL ERROR: {str(e)}\n\n"
            f"The query that failed was: {query}\n\n"
            f"Here is the exact database schema to fix the query:\n"
            f"{SQL_SCHEMA_DESCRIPTION}\n"
            f"Please retry with a corrected SQL query."
        )


# --------------------------------------------------------------------------
# Tool 2: search_vector_db (metadata filter extraction via Pydantic + Qdrant)
# --------------------------------------------------------------------------

class VectorSearchFilters(BaseModel):
    """
    Metadata filters extracted from the user's question.
    Optional fields are left as None when not mentioned in the question.
    """
    document_type: Optional[
        Literal["URD", "URD_Amendement", "Rapport_Integre", "Etats_Financiers", "Essentiel", "Bilan_Social"]
    ] = Field(
        default=None,
        description="Document type mentioned (for example: integrated report, social report, financial statements)."
    )
    document_year: Optional[int] = Field(
        default=None,
        description="Document year mentioned in the question (for example: 2024, 2025)."
    )
    quarter: Optional[Literal["Q2", "Q4"]] = Field(
        default=None,
        description="Quarter mentioned, if the question refers to a quarterly report."
    )


def _build_qdrant_filter(filters: VectorSearchFilters) -> Optional[Filter]:
    """Build a Qdrant Filter from the extracted Pydantic filters."""
    conditions = []

    if filters.document_type:
        conditions.append(
            FieldCondition(key="document_type", match=MatchValue(value=filters.document_type))
        )
    if filters.document_year:
        conditions.append(
            FieldCondition(key="document_year", match=MatchValue(value=filters.document_year))
        )
    if filters.quarter:
        conditions.append(
            FieldCondition(key="quarter", match=MatchValue(value=filters.quarter))
        )

    if not conditions:
        return None

    return Filter(must=conditions)


def extract_filters_with_llm(query: str, llm) -> VectorSearchFilters:
    """
    Uses the LLM with structured output (Pydantic) to extract implicit
    metadata filters from the user's question.

    Equivalent to the Instructor pattern: the LLM is forced to return a
    strictly typed VectorSearchFilters object.
    """
    structured_llm = llm.with_structured_output(VectorSearchFilters)

    prompt = ChatPromptTemplate.from_messages([
        ("system",
         "You extract metadata filters from a question about BNP Paribas "
         "financial reports. Only infer a field when it is explicitly or "
         "very clearly implied by the question. Leave unspecified fields as null."),
        ("human", "{query}"),
    ])

    chain = prompt | structured_llm
    return chain.invoke({"query": query})


def make_search_vector_db_tool(llm):
    """
    Factory that creates the search_vector_db tool and injects the LLM
    required for Pydantic filter extraction.
    """

    @tool
    def search_vector_db(query: str) -> str:
        """
        Performs semantic search in BNP Paribas financial reports
        (Universal Registration Document, integrated reports, quarterly financial
        statements, social reports, etc.).

        Before searching, it automatically extracts strict filters
        (document type, year, quarter) from the question so it only searches
        within the relevant documents.

        Use this tool for any qualitative text question:
        strategy, risks, ESG, governance, events, activity descriptions.

        Args:
            query: The user's natural-language question.
        """
        # 1. Extract strict filters via Pydantic
        filters = extract_filters_with_llm(query, llm)
        qdrant_filter = _build_qdrant_filter(filters)

        # 2. Embed the question
        query_vector = _embedder.encode(query, normalize_embeddings=True).tolist()

        # 3. Search in Qdrant (with a filter if relevant)
        # NOTE: .search() is deprecated in recent qdrant-client versions
        # (>= 1.10) in favor of .query_points()
        search_response = _qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=qdrant_filter,
            limit=5,
        )
        results = search_response.points

        if not results:
            return (
                f"No results found (applied filters: {filters.model_dump(exclude_none=True)}). "
                "Try rephrasing the question or removing some constraints."
            )

        # 4. Format the results
        output_lines = [f"Applied filters: {filters.model_dump(exclude_none=True)}\n"]

        for i, point in enumerate(results, start=1):
            payload = point.payload
            output_lines.append(
                f"[Result {i}] (score={point.score:.3f}) "
                f"source={payload.get('source_file')} "
                f"type={payload.get('document_type')} "
                f"year={payload.get('document_year')} "
                f"quarter={payload.get('quarter')}\n"
                f"{payload.get('text')}\n"
            )

        return "\n".join(output_lines)

    return search_vector_db