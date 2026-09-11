"""POS Hardware Troubleshooting RAG Tool for Cymbal Operations Agent.

Performs vector similarity search with adjacent context window stitching ($N-1$ to $N+1$)
and full-text search fallback over fine-grained POS runbook chunk embeddings in BigQuery.
"""

import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from google.api_core.exceptions import GoogleAPICallError
from google.cloud import bigquery
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

PROJECT_ID = os.getenv("PROJECT_ID", "vic-data-elevate")
TABLE_NAME = f"`{PROJECT_ID}.cymbal_gold.pos_manual_chunk_embeddings`"
BASELINE_TABLE_NAME = f"`{PROJECT_ID}.cymbal_gold.pos_manual_embeddings`"

SIMILARITY_THRESHOLD = 0.70

UNCERTIFIED_WARNING_FALLBACK = (
    "Warning: The inquiry does not match any certified POS hardware terminal "
    "documentation (relevance score < 0.70). Only queries regarding supported POS terminals "
    "(Toshiba TCx 810, Clover Station Solo, HP Engage One Pro, NCR Voyix RealPOS XR7, "
    "Diebold Nixdorf BEETLE A1150) can be resolved."
)


def _gcs_to_https(uri: str) -> str:
    """Converts a gs:// URI to a clickable HTTPS storage URL."""
    if not uri:
        return ""
    if uri.startswith("gs://"):
        return uri.replace("gs://", "https://storage.cloud.google.com/")
    return uri


def _prepare_search_term(query: str) -> str:
    """Extracts and formats search terms safely for BigQuery full-text SEARCH()."""
    # Detect hardware error codes (e.g. ERR-PAY-4001, ERR-DN-PRNT-24V, etc.)
    error_codes = re.findall(r"\b[A-Za-z0-9]{2,}(?:-[A-Za-z0-9]+)+\b", query)
    if error_codes:
        return " OR ".join(f"`{code}`" for code in error_codes)

    # Filter stop words and take key search terms
    stop_words = {
        "what", "is", "the", "a", "an", "and", "or", "how", "do", "we",
        "when", "to", "for", "in", "on", "at", "by", "of", "with", "can",
        "i", "you", "does", "did", "are", "were", "be", "been",
    }
    words = [w for w in re.findall(r"[A-Za-z0-9]+", query) if w.lower() not in stop_words]
    if words:
        return " ".join(words[:6])
    return query


def _execute_query_with_retry(client: bigquery.Client, sql: str, params: List[bigquery.ScalarQueryParameter]) -> List[bigquery.Row]:
    """Executes a BigQuery query with 3 exponential backoff retries."""
    max_retries = 3
    backoff_delay = 1.0  # seconds

    job_config = bigquery.QueryJobConfig(
        query_parameters=params,
        labels={"datacloud": "jetski"},
    )

    for attempt in range(1, max_retries + 1):
        try:
            query_job = client.query(sql, job_config=job_config)
            return list(query_job.result())
        except (GoogleAPICallError, Exception) as exc:
            logger.warning("BigQuery RAG query attempt %d/%d failed: %s", attempt, max_retries, exc)
            if attempt == max_retries:
                raise
            time.sleep(backoff_delay * (2 ** (attempt - 1)))
    return []


def pos_troubleshooting_rag_tool(query: str) -> str:
    """Searches official POS terminal service manuals and hardware diagnostics runbooks.

    Performs vector similarity search and full-text keyword retrieval over fine-grained
    troubleshooting procedures with adjacent context window stitching for Toshiba TCx 810,
    Clover Station Solo, HP Engage One Pro, NCR Voyix RealPOS XR7, and Diebold Nixdorf BEETLE A1150.

    Args:
        query: Hardware fault description, error code (e.g. 'ERR-PAY-4001'), or operational procedure.

    Returns:
        A certified troubleshooting procedure with source manual citation and hardware details,
        or a safety warning if the inquiry is out-of-scope.
    """
    client = bigquery.Client(project=PROJECT_ID)

    # Step 1: Vector Search over pos_manual_chunk_embeddings with adjacent context stitching
    vector_search_sql = f"""
    WITH matched AS (
      SELECT
        base.document_filename,
        base.document_title,
        base.equipment_covered,
        base.source_pdf_uri,
        base.chunk_index,
        ROUND(1 - distance, 4) AS similarity_score
      FROM VECTOR_SEARCH(
        TABLE {TABLE_NAME},
        'embedding',
        (SELECT AI.EMBED(@query, endpoint => 'text-embedding-005').result AS query_embedding),
        top_k => 3,
        distance_type => 'COSINE'
      )
    )
    SELECT
      m.document_filename,
      m.document_title,
      m.equipment_covered,
      m.source_pdf_uri,
      m.chunk_index,
      m.similarity_score,
      STRING_AGG(c.chunk_content, '\\n' ORDER BY c.chunk_index ASC) AS stitched_procedure
    FROM matched m
    JOIN {TABLE_NAME} c
      ON m.document_filename = c.document_filename
     AND c.chunk_index BETWEEN (m.chunk_index - 1) AND (m.chunk_index + 1)
    WHERE m.similarity_score >= {SIMILARITY_THRESHOLD}
    GROUP BY m.document_filename, m.document_title, m.equipment_covered, m.source_pdf_uri, m.chunk_index, m.similarity_score
    ORDER BY m.similarity_score DESC
    LIMIT 4
    """

    try:
        results = _execute_query_with_retry(
            client,
            vector_search_sql,
            [bigquery.ScalarQueryParameter("query", "STRING", query)],
        )
        match_type = "Vector Similarity Search"
    except Exception as exc:
        logger.error("Vector search failed: %s", exc)
        results = []
        match_type = "Unknown"

    # Step 2: Fallback to full-text SEARCH if vector similarity fell below 0.70 threshold
    if not results:
        search_term = _prepare_search_term(query)
        logger.info("Vector search similarity below threshold. Triggering full-text SEARCH fallback with: %s", search_term)

        fulltext_search_sql = f"""
        WITH matched AS (
          SELECT
            document_filename,
            document_title,
            equipment_covered,
            source_pdf_uri,
            chunk_index,
            0.85 AS similarity_score
          FROM {TABLE_NAME}
          WHERE SEARCH(chunk_content, @search_term)
          ORDER BY chunk_index
          LIMIT 4
        )
        SELECT
          m.document_filename,
          m.document_title,
          m.equipment_covered,
          m.source_pdf_uri,
          m.chunk_index,
          m.similarity_score,
          STRING_AGG(c.chunk_content, '\\n' ORDER BY c.chunk_index ASC) AS stitched_procedure
        FROM matched m
        JOIN {TABLE_NAME} c
          ON m.document_filename = c.document_filename
         AND c.chunk_index BETWEEN (m.chunk_index - 1) AND (m.chunk_index + 1)
        GROUP BY m.document_filename, m.document_title, m.equipment_covered, m.source_pdf_uri, m.chunk_index, m.similarity_score
        ORDER BY m.chunk_index ASC
        LIMIT 4
        """

        try:
            results = _execute_query_with_retry(
                client,
                fulltext_search_sql,
                [bigquery.ScalarQueryParameter("search_term", "STRING", search_term)],
            )
            match_type = "Full-Text Keyword Search (Fallback)"
        except Exception as exc:
            logger.error("Full-text SEARCH fallback failed: %s", exc)
            results = []

    # Step 3: If no matches found in either vector search or text search, return certified warning
    if not results:
        return UNCERTIFIED_WARNING_FALLBACK

    # Step 4: Format matched results with citations and clickable HTTPS links
    formatted_sections: List[str] = []
    for row in results:
        doc_title = row.document_title or row.document_filename
        equipment = row.equipment_covered or "POS Hardware Terminal"
        https_url = _gcs_to_https(row.source_pdf_uri)
        score = row.similarity_score
        procedure = row.stitched_procedure

        citation = f"[{doc_title}]({https_url})" if https_url else doc_title

        section = (
            f"### Certified POS Hardware Runbook: {equipment}\n\n"
            f"- **Source Manual:** {citation}\n"
            f"- **Retrieval Method:** {match_type} (Confidence Score: {score:.4f})\n"
            f"- **Chunk Context:** Window [{row.chunk_index - 1} - {row.chunk_index + 1}]\n\n"
            f"#### Troubleshooting Procedure & Field Protocol:\n\n"
            f"{procedure}\n"
        )
        formatted_sections.append(section)

    return "\n---\n".join(formatted_sections)
