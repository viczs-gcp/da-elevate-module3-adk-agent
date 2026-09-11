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

"""Centralized, environment-driven configuration for the Cymbal Operations Agent.

All GCP Project IDs, dataset/table identifiers, Cloud Run MCP target audiences, and
service-account principals are resolved from environment variables (loaded via
``python-dotenv``) so that no deployment-specific identifiers are hardcoded in
source files.

Populate a local ``.env`` file (see ``.env.example``) for local development, or
inject the same variables via Cloud Run / Terraform for deployed environments.
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

# Load .env once for the whole application. Real environment variables always win.
load_dotenv()

logger = logging.getLogger(__name__)

_MISSING_TEMPLATE = (
    "Required environment variable %s is not set. "
    "Copy .env.example to .env and populate it (local development), or inject "
    "the variable via Cloud Run / Terraform (deployed environments)."
)


def get_env(name: str, default: str = "", *, aliases: tuple[str, ...] = ()) -> str:
    """Resolves an environment variable, optionally checking alias names.

    Args:
        name: Primary environment variable name.
        default: Value returned when neither the primary name nor any alias is set.
        aliases: Fallback environment variable names checked in order.

    Returns:
        The resolved value, or ``default`` when nothing is configured.
    """
    for key in (name, *aliases):
        value = os.getenv(key)
        if value:
            return value.strip()
    if not default:
        logger.debug(_MISSING_TEMPLATE, name)
    return default


def require_env(name: str, value: str) -> str:
    """Validates that a resolved configuration value is present.

    Args:
        name: The environment variable name (used for the error message).
        value: The resolved value to validate.

    Returns:
        The validated non-empty value.

    Raises:
        ValueError: If the value is empty or unset.
    """
    if not value:
        raise ValueError(_MISSING_TEMPLATE.replace("%s", name))
    return value


_TRUTHY = frozenset({"1", "true", "t", "yes", "y", "on"})
_FALSY = frozenset({"0", "false", "f", "no", "n", "off"})


def env_flag(name: str, default: bool = False) -> bool:
    """Resolves an environment variable as a boolean feature flag.

    Args:
        name: Environment variable name.
        default: Value returned when the variable is unset, empty, or unparseable.

    Returns:
        The parsed boolean value.
    """
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    value = raw.strip().lower()
    if value in _TRUTHY:
        return True
    if value in _FALSY:
        return False
    logger.warning(
        "Environment variable %s has unparseable boolean value %r; using default %s.",
        name,
        raw,
        default,
    )
    return default


# --------------------------------------------------------------------------- #
# Core GCP configuration
# --------------------------------------------------------------------------- #
PROJECT_ID: str = get_env("PROJECT_ID", aliases=("GOOGLE_CLOUD_PROJECT",))
LOCATION: str = get_env("GOOGLE_CLOUD_LOCATION", "global")
REGION: str = get_env("REGION", "us-central1")

# --------------------------------------------------------------------------- #
# BigQuery Conversational Data Agent (NL2SQL analytics tool)
# --------------------------------------------------------------------------- #
DATA_AGENT_ID: str = get_env("DATA_AGENT_ID")
DATA_AGENT_LOCATION: str = get_env("DATA_AGENT_LOCATION", LOCATION)
DATA_AGENT_NAME: str = get_env(
    "DATA_AGENT_NAME",
    (
        f"projects/{PROJECT_ID}/locations/{DATA_AGENT_LOCATION}/dataAgents/{DATA_AGENT_ID}"
        if PROJECT_ID and DATA_AGENT_ID
        else ""
    ),
    aliases=("BQ_DATA_AGENT_NAME",),
)

# --------------------------------------------------------------------------- #
# BigQuery RAG corpus (POS hardware runbook chunk embeddings)
# --------------------------------------------------------------------------- #
BQ_DATASET: str = get_env("BQ_DATASET", "cymbal_gold")
POS_CHUNK_EMBEDDINGS_TABLE: str = get_env(
    "POS_CHUNK_EMBEDDINGS_TABLE", "pos_manual_chunk_embeddings"
)
POS_BASELINE_EMBEDDINGS_TABLE: str = get_env(
    "POS_BASELINE_EMBEDDINGS_TABLE", "pos_manual_embeddings"
)
EMBEDDING_ENDPOINT: str = get_env("EMBEDDING_ENDPOINT", "text-embedding-005")
SIMILARITY_THRESHOLD: float = float(get_env("SIMILARITY_THRESHOLD", "0.70"))

# --------------------------------------------------------------------------- #
# Cloud Bigtable MCP microservice (Cloud Run)
# --------------------------------------------------------------------------- #
BIGTABLE_MCP_URL: str = get_env(
    "BIGTABLE_MCP_URL", aliases=("BIGTABLE_MCP_SERVICE_URL",)
).rstrip("/")
# OIDC target audience defaults to the Cloud Run service URL itself.
BIGTABLE_MCP_AUDIENCE: str = get_env(
    "BIGTABLE_MCP_AUDIENCE", BIGTABLE_MCP_URL
).rstrip("/")
BIGTABLE_MCP_SERVICE_ACCOUNT: str = get_env("BIGTABLE_MCP_SERVICE_ACCOUNT")

# --------------------------------------------------------------------------- #
# BigQuery Agent Analytics telemetry (BigQueryAgentAnalyticsPlugin)
# --------------------------------------------------------------------------- #
BQ_TELEMETRY_DATASET: str = get_env("BQ_TELEMETRY_DATASET", "agent_telemetry")
BQ_TELEMETRY_TABLE: str = get_env("BQ_TELEMETRY_TABLE", "events")
# Telemetry must land in a concrete BigQuery region -- "global" (a valid Vertex AI
# location) is not a valid BigQuery dataset location, so default to REGION.
BQ_TELEMETRY_LOCATION: str = get_env("BQ_TELEMETRY_LOCATION", REGION)
# Set BQ_TELEMETRY_ENABLED=FALSE to run without streaming telemetry (offline
# tests, CI, or environments without BigQuery write access).
BQ_TELEMETRY_ENABLED: bool = env_flag("BQ_TELEMETRY_ENABLED", True)

# --------------------------------------------------------------------------- #
# Model configuration
# --------------------------------------------------------------------------- #
AGENT_MODEL: str = get_env("AGENT_MODEL", "gemini-3.6-flash")


def bq_table_ref(table: str, dataset: str = "", project: str = "") -> str:
    """Builds a fully-qualified, backtick-quoted BigQuery table reference.

    Args:
        table: Table name.
        dataset: Dataset name, defaults to ``BQ_DATASET``.
        project: Project ID, defaults to ``PROJECT_ID``.

    Returns:
        A backtick-quoted ``project.dataset.table`` reference for use in SQL.
    """
    resolved_project = project or PROJECT_ID
    resolved_dataset = dataset or BQ_DATASET
    return f"`{resolved_project}.{resolved_dataset}.{table}`"


__all__ = [
    "AGENT_MODEL",
    "BIGTABLE_MCP_AUDIENCE",
    "BIGTABLE_MCP_SERVICE_ACCOUNT",
    "BIGTABLE_MCP_URL",
    "BQ_DATASET",
    "BQ_TELEMETRY_DATASET",
    "BQ_TELEMETRY_ENABLED",
    "BQ_TELEMETRY_LOCATION",
    "BQ_TELEMETRY_TABLE",
    "DATA_AGENT_ID",
    "DATA_AGENT_LOCATION",
    "DATA_AGENT_NAME",
    "EMBEDDING_ENDPOINT",
    "LOCATION",
    "POS_BASELINE_EMBEDDINGS_TABLE",
    "POS_CHUNK_EMBEDDINGS_TABLE",
    "PROJECT_ID",
    "REGION",
    "SIMILARITY_THRESHOLD",
    "bq_table_ref",
    "env_flag",
    "get_env",
    "require_env",
]
