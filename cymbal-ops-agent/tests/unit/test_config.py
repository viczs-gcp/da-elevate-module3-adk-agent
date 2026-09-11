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

"""Unit tests for the centralized environment-driven configuration layer.

These tests guard the remediation that removed hardcoded GCP Project IDs,
service-account principals, and Cloud Run OIDC endpoints from backend source.
"""

import pathlib
import re

import pytest

from app import config

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
BACKEND_SOURCES = sorted((REPO_ROOT / "app").rglob("*.py"))

# Patterns that would indicate a deployment-specific identifier was hardcoded.
HARDCODED_PATTERNS = {
    "service account principal": re.compile(
        r"[\"'][A-Za-z0-9._%+-]+@[A-Za-z0-9-]+\.iam\.gserviceaccount\.com[\"']"
    ),
    "cloud run endpoint": re.compile(r"[\"']https://[A-Za-z0-9.-]+\.run\.app[\"']"),
    "data agent resource id": re.compile(r"[\"']agent_[0-9a-f]{8}-[0-9a-f]{4}"),
    "fully-qualified data agent name": re.compile(r"projects/[a-z0-9-]+/locations/"),
}


def test_get_env_prefers_primary_then_aliases(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_env resolves the primary name first, then falls back through aliases."""
    monkeypatch.delenv("UNIT_TEST_PRIMARY", raising=False)
    monkeypatch.delenv("UNIT_TEST_ALIAS", raising=False)

    assert config.get_env("UNIT_TEST_PRIMARY", "fallback") == "fallback"

    monkeypatch.setenv("UNIT_TEST_ALIAS", "from-alias")
    assert (
        config.get_env("UNIT_TEST_PRIMARY", "fallback", aliases=("UNIT_TEST_ALIAS",))
        == "from-alias"
    )

    monkeypatch.setenv("UNIT_TEST_PRIMARY", "  from-primary  ")
    assert (
        config.get_env("UNIT_TEST_PRIMARY", "fallback", aliases=("UNIT_TEST_ALIAS",))
        == "from-primary"
    )


def test_require_env_raises_actionable_error_when_missing() -> None:
    """require_env surfaces a clear remediation message for unset configuration."""
    assert config.require_env("PROJECT_ID", "my-project") == "my-project"

    with pytest.raises(ValueError) as excinfo:
        config.require_env("BIGTABLE_MCP_URL", "")
    message = str(excinfo.value)
    assert "BIGTABLE_MCP_URL" in message
    assert ".env.example" in message


def test_bq_table_ref_is_fully_qualified_and_quoted() -> None:
    """bq_table_ref builds a backtick-quoted project.dataset.table reference."""
    ref = config.bq_table_ref("my_table", dataset="my_dataset", project="my-project")
    assert ref == "`my-project.my_dataset.my_table`"

    # Defaults come from the environment-driven configuration.
    default_ref = config.bq_table_ref("pos_manual_chunk_embeddings")
    assert default_ref.startswith("`")
    assert default_ref.endswith(".pos_manual_chunk_embeddings`")
    assert config.BQ_DATASET in default_ref


def test_bigtable_mcp_audience_defaults_to_service_url() -> None:
    """The OIDC audience falls back to the Cloud Run service URL and has no trailing slash."""
    if config.BIGTABLE_MCP_URL:
        assert config.BIGTABLE_MCP_AUDIENCE
        assert not config.BIGTABLE_MCP_AUDIENCE.endswith("/")
    assert not config.BIGTABLE_MCP_URL.endswith("/")


def test_similarity_threshold_is_numeric_and_within_bounds() -> None:
    """SIMILARITY_THRESHOLD is parsed to a float inside the valid cosine range."""
    assert isinstance(config.SIMILARITY_THRESHOLD, float)
    assert 0.0 < config.SIMILARITY_THRESHOLD <= 1.0


@pytest.mark.parametrize("source_path", BACKEND_SOURCES, ids=lambda p: p.name)
def test_no_hardcoded_deployment_identifiers_in_backend_sources(
    source_path: pathlib.Path,
) -> None:
    """Backend sources must not embed project IDs, SA principals, or Run endpoints."""
    text = source_path.read_text(encoding="utf-8")
    # Strip comments so documentation examples do not trigger false positives.
    code_lines = [
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    ]
    code = "\n".join(code_lines)

    for label, pattern in HARDCODED_PATTERNS.items():
        match = pattern.search(code)
        assert match is None, (
            f"Hardcoded {label} found in {source_path.relative_to(REPO_ROOT)}: "
            f"{match.group(0) if match else ''}. "
            "Resolve it from the environment via app/config.py instead."
        )


def test_env_example_documents_every_required_variable() -> None:
    """.env.example documents each variable the backend reads at runtime."""
    env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
    for name in (
        "PROJECT_ID",
        "DATA_AGENT_ID",
        "BQ_DATASET",
        "POS_CHUNK_EMBEDDINGS_TABLE",
        "SIMILARITY_THRESHOLD",
        "BIGTABLE_MCP_URL",
        "BIGTABLE_MCP_SERVICE_ACCOUNT",
        "AGENT_MODEL",
    ):
        assert name in env_example, f"{name} is not documented in .env.example"
