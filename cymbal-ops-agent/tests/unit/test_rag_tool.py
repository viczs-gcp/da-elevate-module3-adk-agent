# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Unit tests for pos_troubleshooting_rag_tool and helper functions."""

from unittest.mock import MagicMock, patch

from app.tools.rag_tool import (
    SIMILARITY_THRESHOLD,
    UNCERTIFIED_WARNING_FALLBACK,
    _gcs_to_https,
    _prepare_search_term,
    pos_troubleshooting_rag_tool,
)


def test_uncertified_warning_fallback_exact_string() -> None:
    """Verifies that the RAG fallback matches the exact mandatory decline string."""
    expected = (
        "I cannot find certified warranty or repair rules for this specific error "
        "in our technical repository."
    )
    assert UNCERTIFIED_WARNING_FALLBACK == expected
    assert SIMILARITY_THRESHOLD == 0.70


def test_gcs_to_https_conversion() -> None:
    """Tests GCS URI to HTTPS conversion for manual citations."""
    assert _gcs_to_https("") == ""
    assert _gcs_to_https("https://example.com/doc.pdf") == "https://example.com/doc.pdf"
    assert (
        _gcs_to_https("gs://my-bucket/manuals/Toshiba_Guide.pdf")
        == "https://storage.cloud.google.com/my-bucket/manuals/Toshiba_Guide.pdf"
    )


def test_prepare_search_term_error_codes() -> None:
    """Tests extraction of error codes for full-text fallback search."""
    term = _prepare_search_term("Cashier encounters ERR-PAY-4001 EMV freeze")
    assert "`ERR-PAY-4001`" in term

    term_multi = _prepare_search_term("Check ERR-PAY-4001 and ERR-DN-PRNT-24V")
    assert "`ERR-PAY-4001`" in term_multi
    assert "`ERR-DN-PRNT-24V`" in term_multi


def test_prepare_search_term_keywords() -> None:
    """Tests stop-word filtering when no error code is present."""
    term = _prepare_search_term("how do we replace the receipt paper roll")
    assert "how" not in term.split()
    assert "replace" in term
    assert "receipt" in term


@patch("app.tools.rag_tool.bigquery.Client")
def test_rag_tool_below_threshold_returns_mandatory_decline(mock_bq_client_cls) -> None:
    """Verifies that out-of-scope queries returning no matches output the exact decline string."""
    mock_client = MagicMock()
    mock_bq_client_cls.return_value = mock_client
    # Both vector search and fallback return no rows
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    result = pos_troubleshooting_rag_tool("How do I change the oil on a Ford F-150 truck?")
    assert result == UNCERTIFIED_WARNING_FALLBACK


@patch("app.tools.rag_tool.bigquery.Client")
def test_rag_tool_sql_contains_error_code_wildcard_case_check(mock_bq_client_cls) -> None:
    """Verifies that the vector search query includes the SQL CASE error-code wildcard check."""
    mock_client = MagicMock()
    mock_bq_client_cls.return_value = mock_client
    mock_query_job = MagicMock()
    mock_query_job.result.return_value = []
    mock_client.query.return_value = mock_query_job

    pos_troubleshooting_rag_tool("ERR-PAY-4001 EMV tokenization timeout")

    # Inspect the initial vector search SQL executed
    assert mock_client.query.called
    called_sql = mock_client.query.call_args_list[0][0][0]
    assert "VECTOR_SEARCH" in called_sql
    assert "CASE" in called_sql
    assert "REGEXP_CONTAINS(@query, r'(?i)ERR-[A-Za-z0-9_*%-]+')" in called_sql
    assert "0.25" in called_sql
    assert "hybrid_score" in called_sql
    assert "BETWEEN (m.chunk_index - 1) AND (m.chunk_index + 1)" in called_sql


@patch("app.tools.rag_tool.bigquery.Client")
def test_rag_tool_successful_match_formatting(mock_bq_client_cls) -> None:
    """Verifies that successful matches format Hybrid Score, Vector Score, and HTTPS links."""
    mock_client = MagicMock()
    mock_bq_client_cls.return_value = mock_client

    mock_row = MagicMock()
    mock_row.document_filename = "Toshiba_TCx_810_Guide.pdf"
    mock_row.document_title = "Toshiba TCx 810 POS Hardware, Diagnostics & Service Guide"
    mock_row.equipment_covered = "Toshiba TCx 810"
    mock_row.source_pdf_uri = "gs://da-bucket/Toshiba_Guide.pdf"
    mock_row.chunk_index = 42
    mock_row.vector_score = 0.6696
    mock_row.hybrid_score = 0.9196
    mock_row.stitched_procedure = "Step 1: Prevent double charge.\nStep 2: Reboot module."

    mock_query_job = MagicMock()
    mock_query_job.result.return_value = [mock_row]
    mock_client.query.return_value = mock_query_job

    result = pos_troubleshooting_rag_tool("ERR-PAY-4001 freeze")
    assert "--- [MATCH #1 | Hybrid Score: 0.9196 (Vector Score: 0.6696)] ---" in result
    assert "Manual: Toshiba TCx 810 POS Hardware, Diagnostics & Service Guide (Toshiba TCx 810)" in result
    assert "Documentation Link: https://storage.cloud.google.com/da-bucket/Toshiba_Guide.pdf" in result
    assert "Step 1: Prevent double charge." in result
