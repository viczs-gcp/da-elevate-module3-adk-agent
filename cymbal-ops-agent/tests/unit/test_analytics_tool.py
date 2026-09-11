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

"""Unit tests for cymbal_analytics_tool, temporal guardrails, and stream response parsing."""

from unittest.mock import MagicMock, patch
import pytest

from app.tools.analytics_tool import (
    CLARIFICATION_PROMPT,
    FALLBACK_MESSAGE,
    _format_stream_response,
    check_temporal_date_requirement,
    cymbal_analytics_tool,
)


def test_temporal_date_check_blocks_missing_date_for_partitioned_queries() -> None:
    """Verifies that queries requesting metrics on partitioned tables without dates are blocked."""
    # Net transaction revenue without date
    res = check_temporal_date_requirement("What is the Net Transaction Revenue for Store 8?")
    assert res == CLARIFICATION_PROMPT

    # POS transactions without date
    res2 = check_temporal_date_requirement("Show me all pos_transactions for store 48")
    assert res2 == CLARIFICATION_PROMPT

    # Checkout logs without timeframe
    res3 = check_temporal_date_requirement("Retrieve checkout logs for offending cashier")
    assert res3 == CLARIFICATION_PROMPT


def test_temporal_date_check_allows_compliant_timeframes() -> None:
    """Verifies that queries with temporal boundaries pass the guardrail check."""
    # Relative timeframe: today
    assert check_temporal_date_requirement("What is the Net Transaction Revenue for Store 8 today?") is None

    # Relative timeframe: last 7 days
    assert check_temporal_date_requirement("Show promo abuse alerts in the last 7 days") is None

    # Historical baseline
    assert check_temporal_date_requirement("Compare override rate to 7-day historical baseline") is None

    # Explicit ISO date range
    assert check_temporal_date_requirement("What are sales between 2026-09-01 and 2026-09-07?") is None

    # Transaction ID containing date
    assert check_temporal_date_requirement("Check transaction details for TXN-20260312-0015811") is None


def test_temporal_date_check_allows_non_partitioned_queries() -> None:
    """Verifies that non-partitioned inventory and policy queries pass without requiring dates."""
    inventory_query = (
        "What is the estimated cover hours remaining for store inventory positions "
        "experiencing stockout risk?"
    )
    assert check_temporal_date_requirement(inventory_query) is None

    warranty_query = "Is the customer item covered under warranty policy duration?"
    assert check_temporal_date_requirement(warranty_query) is None


def test_cymbal_analytics_tool_returns_clarification_for_unpartitioned_query() -> None:
    """Verifies cymbal_analytics_tool pauses and returns clarification prompt immediately."""
    result = cymbal_analytics_tool("What is the Net Transaction Revenue across all regions?")
    assert "[CLARIFICATION REQUIRED]" in result
    assert "Please specify a target date range" in result


def test_format_stream_response_parsing() -> None:
    """Tests parsing of streaming Data Agent steps into formatted markdown."""
    steps = [
        {"data": {"generatedSql": "SELECT store_id, SUM(amount) FROM sales GROUP BY 1"}},
        {
            "Data Retrieved": {
                "headers": ["store_id", "total_sales"],
                "rows": [[8, 45200.50]],
                "summary": "1 row returned",
            }
        },
        {
            "text": {
                "textType": "FINAL_RESPONSE",
                "parts": ["Net Transaction Revenue for Store 8 today is $45,200.50."],
            }
        },
    ]

    formatted = _format_stream_response(steps)
    assert "Net Transaction Revenue for Store 8 today is $45,200.50." in formatted
    assert "```sql" in formatted
    assert "SELECT store_id, SUM(amount)" in formatted
    assert "| store_id | total_sales |" in formatted
    assert "| 8 | 45200.5 |" in formatted


@patch("app.tools.analytics_tool.google.auth.default")
@patch("app.tools.analytics_tool.data_agent_tool.ask_data_agent")
def test_cymbal_analytics_tool_successful_execution(mock_ask, mock_auth) -> None:
    """Verifies successful tool execution returns synthesized response."""
    mock_auth.return_value = (MagicMock(), "project")
    mock_ask.return_value = {
        "status": "SUCCESS",
        "response": [
            {
                "text": {
                    "textType": "FINAL_RESPONSE",
                    "parts": ["Total On-Hand Inventory is 12,450 units."],
                }
            }
        ],
    }

    result = cymbal_analytics_tool("What is the Total On-Hand Inventory for Store 8 today?")
    assert "Total On-Hand Inventory is 12,450 units." in result


@patch("app.tools.analytics_tool.google.auth.default")
@patch("app.tools.analytics_tool.data_agent_tool.ask_data_agent")
def test_cymbal_analytics_tool_retry_and_fallback(mock_ask, mock_auth) -> None:
    """Verifies that transient errors retry up to 3 times before returning the fallback message."""
    mock_auth.return_value = (MagicMock(), "project")
    mock_ask.side_effect = Exception("Service unavailable")

    with patch("time.sleep", return_value=None):
        result = cymbal_analytics_tool("What is the Total On-Hand Inventory today?")
        assert result == FALLBACK_MESSAGE
        assert mock_ask.call_count == 3
