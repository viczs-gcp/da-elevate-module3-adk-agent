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

"""Unit tests for the BigQuery Agent Analytics telemetry wiring (Challenge 1.2).

Covers the environment-driven telemetry configuration in ``app/config.py`` and
the plugin factory that feeds ``App(plugins=...)`` in ``app/agent.py``.
"""

from __future__ import annotations

import importlib
from unittest import mock

import pytest
from google.adk.plugins.bigquery_agent_analytics_plugin import (
    BigQueryAgentAnalyticsPlugin,
)

from app import agent as agent_module
from app import config

PLUGIN_PATH = "app.agent.BigQueryAgentAnalyticsPlugin"


# --------------------------------------------------------------------------- #
# config.env_flag
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("TRUE", True),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("FALSE", False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
    ],
)
def test_env_flag_parses_common_boolean_spellings(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: bool
) -> None:
    """env_flag accepts the usual truthy/falsy spellings, case-insensitively."""
    monkeypatch.setenv("UNIT_TEST_FLAG", raw)
    assert config.env_flag("UNIT_TEST_FLAG", not expected) is expected


@pytest.mark.parametrize("raw", ["", "   ", "maybe"])
def test_env_flag_falls_back_to_default(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """Unset, blank, and unparseable values fall back to the supplied default."""
    monkeypatch.setenv("UNIT_TEST_FLAG", raw)
    assert config.env_flag("UNIT_TEST_FLAG", True) is True
    assert config.env_flag("UNIT_TEST_FLAG", False) is False

    monkeypatch.delenv("UNIT_TEST_FLAG", raising=False)
    assert config.env_flag("UNIT_TEST_FLAG", True) is True


# --------------------------------------------------------------------------- #
# Telemetry configuration defaults
# --------------------------------------------------------------------------- #
def test_telemetry_defaults_match_lab_requirements() -> None:
    """Dataset/table default to the lab-mandated agent_telemetry.events."""
    assert config.BQ_TELEMETRY_DATASET == "agent_telemetry"
    assert config.BQ_TELEMETRY_TABLE == "events"


def test_telemetry_location_is_a_valid_bigquery_region() -> None:
    """BigQuery has no 'global' location, so telemetry must use a real region."""
    assert config.BQ_TELEMETRY_LOCATION
    assert config.BQ_TELEMETRY_LOCATION != "global"
    # Defaults to REGION rather than the Vertex AI LOCATION.
    assert config.BQ_TELEMETRY_LOCATION == config.REGION


def test_telemetry_dataset_is_not_the_analytics_dataset() -> None:
    """Telemetry is isolated from the curated Gold data warehouse dataset."""
    assert config.BQ_TELEMETRY_DATASET != config.BQ_DATASET


def test_telemetry_env_names_are_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reimporting config with overrides proves the values are env-driven."""
    monkeypatch.setenv("BQ_TELEMETRY_DATASET", "custom_telemetry")
    monkeypatch.setenv("BQ_TELEMETRY_TABLE", "custom_events")
    monkeypatch.setenv("BQ_TELEMETRY_LOCATION", "europe-west4")
    monkeypatch.setenv("BQ_TELEMETRY_ENABLED", "FALSE")
    try:
        reloaded = importlib.reload(config)
        assert reloaded.BQ_TELEMETRY_DATASET == "custom_telemetry"
        assert reloaded.BQ_TELEMETRY_TABLE == "custom_events"
        assert reloaded.BQ_TELEMETRY_LOCATION == "europe-west4"
        assert reloaded.BQ_TELEMETRY_ENABLED is False
    finally:
        monkeypatch.undo()
        importlib.reload(config)


# --------------------------------------------------------------------------- #
# app.agent.build_telemetry_plugins
# --------------------------------------------------------------------------- #
def test_build_telemetry_plugins_returns_empty_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The BQ_TELEMETRY_ENABLED kill switch short-circuits plugin creation."""
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_ENABLED", False)
    with mock.patch(PLUGIN_PATH) as plugin_cls:
        assert agent_module.build_telemetry_plugins() == []
    plugin_cls.assert_not_called()


def test_build_telemetry_plugins_returns_empty_without_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unconfigured PROJECT_ID degrades gracefully instead of crashing."""
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_ENABLED", True)
    monkeypatch.setattr(agent_module.config, "PROJECT_ID", "")
    with mock.patch(PLUGIN_PATH) as plugin_cls:
        assert agent_module.build_telemetry_plugins() == []
    plugin_cls.assert_not_called()


def test_build_telemetry_plugins_passes_config_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The plugin is constructed purely from config -- never from literals."""
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_ENABLED", True)
    monkeypatch.setattr(agent_module.config, "PROJECT_ID", "unit-test-project")
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_DATASET", "unit_telemetry")
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_TABLE", "unit_events")
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_LOCATION", "us-central1")

    with mock.patch(PLUGIN_PATH) as plugin_cls:
        plugins = agent_module.build_telemetry_plugins()

    assert plugins == [plugin_cls.return_value]
    plugin_cls.assert_called_once_with(
        project_id="unit-test-project",
        dataset_id="unit_telemetry",
        table_id="unit_events",
        location="us-central1",
    )


def test_build_telemetry_plugins_creates_a_real_adk_plugin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The factory yields a genuine BigQueryAgentAnalyticsPlugin instance.

    ``__init__`` performs no network I/O (the BigQuery client is created lazily
    on first use), so this is safe to assert offline.
    """
    monkeypatch.setattr(agent_module.config, "BQ_TELEMETRY_ENABLED", True)
    monkeypatch.setattr(agent_module.config, "PROJECT_ID", "unit-test-project")

    plugins = agent_module.build_telemetry_plugins()

    assert len(plugins) == 1
    plugin = plugins[0]
    assert isinstance(plugin, BigQueryAgentAnalyticsPlugin)
    assert plugin.project_id == "unit-test-project"
    assert plugin.dataset_id == config.BQ_TELEMETRY_DATASET
    assert plugin.table_id == config.BQ_TELEMETRY_TABLE
    assert plugin.location == config.BQ_TELEMETRY_LOCATION


def test_app_accepts_the_telemetry_plugin_list() -> None:
    """App(plugins=...) is wired and holds exactly the factory's output."""
    # The suite runs with telemetry disabled (see root conftest.py), so the live
    # App has no plugins; assert the wiring instead of the disabled result.
    assert hasattr(agent_module.app, "plugins")
    assert agent_module.app.plugins == agent_module.build_telemetry_plugins()


def test_env_example_documents_telemetry_variables() -> None:
    """.env.example documents every telemetry variable the backend reads."""
    import pathlib

    repo_root = pathlib.Path(__file__).resolve().parents[2]
    env_example = (repo_root / ".env.example").read_text(encoding="utf-8")
    for name in (
        "BQ_TELEMETRY_DATASET",
        "BQ_TELEMETRY_TABLE",
        "BQ_TELEMETRY_LOCATION",
        "BQ_TELEMETRY_ENABLED",
    ):
        assert name in env_example, f"{name} is not documented in .env.example"
