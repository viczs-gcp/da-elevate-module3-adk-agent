"""NL2SQL Data Agent Tool for Cymbal Operations Agent.

Integrates with the BigQuery Conversational Data Agent API to fulfill ad-hoc,
natural language retail analytics inquiries across Gold operational datasets.
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import google.auth
import google.auth.transport.requests
from dotenv import load_dotenv
from google.adk.tools.data_agent import data_agent_tool
from google.adk.tools.data_agent.config import DataAgentToolConfig

load_dotenv()

logger = logging.getLogger(__name__)

# Target published Data Agent resource name
PROJECT_ID = os.getenv("PROJECT_ID", "vic-data-elevate")
DATA_AGENT_ID = os.getenv("DATA_AGENT_ID", "agent_74a5ddb1-afde-4852-9c56-d05df3c3f9de")
DATA_AGENT_NAME = os.getenv(
    "DATA_AGENT_NAME",
    f"projects/{PROJECT_ID}/locations/global/dataAgents/{DATA_AGENT_ID}",
)

FALLBACK_MESSAGE = (
    "Store analytics data service is currently unreachable. "
    "Please verify database connectivity or try again later."
)

CLARIFICATION_PROMPT = (
    "[CLARIFICATION REQUIRED] Please specify a target date range or timeframe "
    "(e.g., 'today', '2026-09-01 to 2026-09-07', or 'last 7 days') before "
    "querying partitioned transaction datasets."
)

PARTITIONED_KEYWORDS = [
    r"\bnet\s+transaction\s+revenue\b",
    r"\bpos_transactions(?:_gold)?\b",
    r"\bsilver_pos_transactions\b",
    r"\bcheckout\s+logs\b",
    r"\bpromo\s+abuse\b",
    r"\btransaction(?:s)?\b",
    r"\bcheckout(?:s)?\b",
    r"\bcashier\s+(?:promo\s+)?override\b",
]

TEMPORAL_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",                      # 2026-09-11
    r"\b\d{4}/\d{2}/\d{2}\b",                      # 2026/09/11
    r"\b\d{1,2}/\d{1,2}/\d{2,4}\b",                # 09/11/2026
    r"\b202[0-9]\b",                               # 2026
    r"\b(?:today|yesterday|tomorrow)\b",           # today
    r"\b(?:last|past|next|this)\s+(?:\d+\s+)?(?:day|days|week|weeks|month|months|quarter|year|years|hour|hours)\b",
    r"\b(?:daily|weekly|monthly|quarterly|hourly)\b",
    r"\b\d+-day\b",                                # 7-day
    r"\brolling\b",
    r"\b(?:since|between|from|to|until|during)\b",
    r"\b(?:q[1-4]|ytd|mtd|wtd)\b",
    r"\bTXN-\d{8}-\d+\b",                          # TXN-20260312-0015811
    r"\bbaseline\b",                               # baseline comparison
    r"\brecent\b",
    r"\blatest\b",
]


def check_temporal_date_requirement(query: str) -> Optional[str]:
    """Validates whether queries targeting partitioned datasets include a temporal boundary.

    Queries requesting metrics over partitioned transaction tables (e.g. Net Transaction Revenue,
    sales, orders, POS transactions, checkout logs) must specify a date range or timeframe
    to avoid unpartitioned full-table scans.

    Returns:
        CLARIFICATION_PROMPT if the query targets partitioned datasets without a temporal date,
        or None if the query is compliant.
    """
    query_lower = query.lower()

    targets_partitioned = any(
        re.search(pat, query_lower) for pat in PARTITIONED_KEYWORDS
    )
    if not targets_partitioned:
        return None

    has_temporal_boundary = any(
        re.search(pat, query_lower, re.IGNORECASE) for pat in TEMPORAL_PATTERNS
    )
    if not has_temporal_boundary:
        return CLARIFICATION_PROMPT

    return None


def _format_stream_response(steps: List[Dict[str, Any]]) -> str:
    """Parses streaming response steps from BigQuery Data Agent.

    Extracts:
      - Generated GoogleSQL queries
      - Tabular results (markdown formatted)
      - Final synthesized analytical response
    """
    generated_sqls: List[str] = []
    final_responses: List[str] = []
    data_tables: List[str] = []
    thoughts: List[str] = []

    for step in steps:
        if not isinstance(step, dict):
            continue

        # 1. SQL extraction
        data_block = step.get("data")
        if isinstance(data_block, dict):
            sql = data_block.get("generatedSql")
            if sql and sql.strip() and sql.strip() not in generated_sqls:
                generated_sqls.append(sql.strip())

        # 2. Text extraction (Final Response, Thoughts)
        text_block = step.get("text")
        if isinstance(text_block, dict):
            text_type = text_block.get("textType", "")
            parts = text_block.get("parts", [])
            if text_type == "FINAL_RESPONSE":
                for part in parts:
                    if part and part.strip() and part.strip() not in final_responses:
                        final_responses.append(part.strip())
            elif text_type == "THOUGHT":
                for part in parts:
                    if part and part.strip():
                        thoughts.append(part.strip())

        # 3. Tabular Data extraction
        dr_block = step.get("Data Retrieved")
        if isinstance(dr_block, dict):
            headers = dr_block.get("headers", [])
            rows = dr_block.get("rows", [])
            summary = dr_block.get("summary", "")
            if headers and rows:
                md_table = "| " + " | ".join(str(h) for h in headers) + " |\n"
                md_table += "| " + " | ".join(["---"] * len(headers)) + " |\n"
                for row in rows[:15]:
                    md_table += "| " + " | ".join(str(val) for val in row) + " |\n"
                if summary:
                    md_table += f"\n*{summary}*"
                data_tables.append(md_table)

    sections: List[str] = []
    if final_responses:
        sections.append("\n\n".join(final_responses))

    if generated_sqls:
        sql_formatted = "```sql\n" + "\n\n".join(generated_sqls) + "\n```"
        sections.append(f"### Generated GoogleSQL\n{sql_formatted}")

    if data_tables:
        sections.append("### Retrieved Data\n" + "\n\n".join(data_tables))

    if not sections:
        if thoughts:
            return "Analysis completed:\n" + "\n".join(thoughts)
        return "No analytics data returned."

    return "\n\n".join(sections)


def cymbal_analytics_tool(query: str) -> str:
    """Queries enterprise store operational analytics via the BigQuery Conversational Data Agent.

    Use this tool to answer natural language inquiries about retail store performance,
    inventory reconciliation, cashier promotions, POS transactions, and customer metrics.

    CRITICAL: Natural language inquiries referencing standardized enterprise business terms
    (such as Net Transaction Revenue, Total On-Hand Inventory, Estimated Cover Hours,
    Cashier Promo Override Rate, Warranty Policy Duration, Shelf Stock Ratio) must be passed
    verbatim to ensure accurate semantic glossary mapping.

    Args:
        query: The natural language question or analytical inquiry.

    Returns:
        A formatted markdown string containing the conversational response, generated GoogleSQL,
        and underlying data retrieved from BigQuery.
    """
    # Guardrail: Check for temporal date requirement on partitioned datasets
    clarification = check_temporal_date_requirement(query)
    if clarification:
        logger.info("Query requires temporal clarification before querying partitioned datasets: %s", query)
        return clarification

    max_retries = 3
    backoff_delay = 1.0  # seconds (exponential: 1s, 2s, 4s)

    for attempt in range(1, max_retries + 1):
        try:
            creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            if not creds.valid:
                creds.refresh(google.auth.transport.requests.Request())

            settings = DataAgentToolConfig()

            result = data_agent_tool.ask_data_agent(
                data_agent_name=DATA_AGENT_NAME,
                query=query,
                credentials=creds,
                settings=settings,
                tool_context=None,
            )

            if result.get("status") == "SUCCESS":
                response_steps = result.get("response", [])
                return _format_stream_response(response_steps)

            error_msg = result.get("error_details", "Unknown error from Data Agent")
            logger.warning("Attempt %d/%d failed: %s", attempt, max_retries, error_msg)
            if attempt == max_retries:
                return FALLBACK_MESSAGE

        except Exception as exc:
            logger.warning("Attempt %d/%d encountered exception: %s", attempt, max_retries, exc)
            if attempt == max_retries:
                return FALLBACK_MESSAGE

        time.sleep(backoff_delay * (2 ** (attempt - 1)))

    return FALLBACK_MESSAGE


__all__ = [
    "cymbal_analytics_tool",
    "check_temporal_date_requirement",
    "CLARIFICATION_PROMPT",
    "FALLBACK_MESSAGE",
]
