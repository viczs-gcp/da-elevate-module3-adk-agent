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

"""Unit tests for Bigtable MCP toolset configuration and credentials."""

import pytest
from google.adk.tools import McpToolset

from app.tools.bigtable_tool import (
    BIGTABLE_MCP_URL,
    bigtable_mcp_toolset,
    create_bigtable_mcp_toolset,
)


def test_bigtable_mcp_url_configured() -> None:
    """Verifies that the Bigtable MCP URL is configured correctly."""
    assert "mcp-toolbox-bigtable" in BIGTABLE_MCP_URL
    assert not BIGTABLE_MCP_URL.endswith("/")


def test_bigtable_toolset_instance() -> None:
    """Verifies that the module-level bigtable_mcp_toolset is a valid McpToolset instance."""
    assert isinstance(bigtable_mcp_toolset, McpToolset)


def test_create_bigtable_mcp_toolset_custom_url() -> None:
    """Tests creating a toolset instance with a custom URL endpoint."""
    custom_url = "https://custom-mcp-service.a.run.app"
    toolset = create_bigtable_mcp_toolset(url=custom_url)
    assert isinstance(toolset, McpToolset)
    assert toolset._connection_params.url == f"{custom_url}/mcp"


def test_row_key_format_standard() -> None:
    """Verifies the row key generation pattern for store and cashier IDs."""
    store_id = 48
    cashier_id = 1190
    row_key = f"STORE_{store_id:03d}#CASH_{cashier_id}"
    assert row_key == "STORE_048#CASH_1190"
    assert row_key.startswith("STORE_")
    assert "#CASH_" in row_key
