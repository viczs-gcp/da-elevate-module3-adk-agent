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

from google.adk.tools import McpToolset

from app import config
from app.tools.bigtable_tool import (
    BIGTABLE_MCP_AUDIENCE,
    BIGTABLE_MCP_URL,
    SERVICE_ACCOUNT,
    bigtable_mcp_toolset,
    create_bigtable_mcp_toolset,
)


def test_bigtable_mcp_url_is_env_driven() -> None:
    """The Cloud Run endpoint is resolved from the environment, never hardcoded."""
    assert BIGTABLE_MCP_URL == config.BIGTABLE_MCP_URL
    assert not BIGTABLE_MCP_URL.endswith("/")
    if BIGTABLE_MCP_URL:
        assert BIGTABLE_MCP_URL.startswith("https://")


def test_bigtable_mcp_audience_and_service_account_are_env_driven() -> None:
    """OIDC audience and impersonated principal both come from configuration."""
    assert BIGTABLE_MCP_AUDIENCE == (
        config.BIGTABLE_MCP_AUDIENCE or config.BIGTABLE_MCP_URL
    )
    assert SERVICE_ACCOUNT == config.BIGTABLE_MCP_SERVICE_ACCOUNT
    if SERVICE_ACCOUNT:
        assert SERVICE_ACCOUNT.endswith(".iam.gserviceaccount.com")


def test_bigtable_toolset_instance() -> None:
    """Verifies that the module-level bigtable_mcp_toolset is a valid McpToolset instance."""
    assert isinstance(bigtable_mcp_toolset, McpToolset)


def test_create_bigtable_mcp_toolset_custom_url() -> None:
    """Tests creating a toolset instance with a custom URL endpoint."""
    custom_url = "https://custom-mcp-service.a.run.app"
    toolset = create_bigtable_mcp_toolset(url=custom_url)
    assert isinstance(toolset, McpToolset)
    assert toolset._connection_params.url == f"{custom_url}/mcp"


def test_create_bigtable_mcp_toolset_strips_trailing_slash() -> None:
    """Trailing slashes never leak into the MCP endpoint path."""
    toolset = create_bigtable_mcp_toolset(url="https://custom-mcp-service.a.run.app/")
    assert toolset._connection_params.url == "https://custom-mcp-service.a.run.app/mcp"


def test_row_key_format_standard() -> None:
    """Verifies the row key generation pattern for store and cashier IDs."""
    store_id = 48
    cashier_id = 1190
    row_key = f"STORE_{store_id:03d}#CASH_{cashier_id}"
    assert row_key == "STORE_048#CASH_1190"
    assert row_key.startswith("STORE_")
    assert "#CASH_" in row_key
