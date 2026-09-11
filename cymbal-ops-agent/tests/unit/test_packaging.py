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

"""Packaging regression tests.

Guards the remediation for three container/start-up blockers:

1. ``a2a-sdk`` missing from the dependency lists, crashing ``fast_api_app.py``.
2. ``Dockerfile`` running ``uv sync --frozen`` with no committed ``uv.lock``.
3. Runtime imports (``google-auth``, ``google-cloud-logging``, ``gcsfs``) that
   were only present transitively.
"""

import importlib.util
import pathlib
import tomllib

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"
REQUIREMENTS_PATH = REPO_ROOT / "requirements.txt"
UV_LOCK_PATH = REPO_ROOT / "uv.lock"
DOCKERFILE_PATH = REPO_ROOT / "Dockerfile"

# Modules imported at module scope by app/fast_api_app.py and app/app_utils/a2a.py.
STARTUP_IMPORT_DISTRIBUTIONS = [
    "a2a-sdk",
    "fastapi",
    "gcsfs",
    "google-adk",
    "google-auth",
    "google-cloud-bigquery",
    "google-cloud-bigtable",
    "google-cloud-logging",
    "mcp",
    "python-dotenv",
    "uvicorn",
]


@pytest.fixture(scope="module")
def declared_dependencies() -> list[str]:
    """Returns the raw dependency specifiers declared in pyproject.toml."""
    with PYPROJECT_PATH.open("rb") as handle:
        return tomllib.load(handle)["project"]["dependencies"]


def test_a2a_sdk_is_pinned_in_pyproject(declared_dependencies: list[str]) -> None:
    """a2a-sdk must be declared and pinned so the A2A FastAPI app starts up."""
    pins = [d for d in declared_dependencies if d.startswith("a2a-sdk")]
    assert pins, "a2a-sdk is missing from pyproject.toml dependencies"
    assert "==" in pins[0], f"a2a-sdk must be pinned exactly, got: {pins[0]}"


def test_a2a_sdk_is_pinned_in_requirements() -> None:
    """requirements.txt mirrors the pyproject pin for pip-based installs."""
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    assert "a2a-sdk==" in requirements


def test_startup_dependencies_declared(declared_dependencies: list[str]) -> None:
    """Every module imported at start-up is an explicit, declared dependency."""
    declared = {
        d.split(">=")[0].split("==")[0].split("[")[0].split("<")[0].strip()
        for d in declared_dependencies
    }
    missing = sorted(set(STARTUP_IMPORT_DISTRIBUTIONS) - declared)
    assert not missing, f"Undeclared start-up dependencies: {missing}"


def test_a2a_sdk_is_importable() -> None:
    """The pinned a2a-sdk exposes every symbol the app imports at start-up."""
    from a2a.server.apps import A2AFastAPIApplication  # noqa: F401
    from a2a.server.request_handlers import DefaultRequestHandler  # noqa: F401
    from a2a.server.tasks import InMemoryTaskStore, TaskStore  # noqa: F401
    from a2a.types import AgentCapabilities, AgentExtension  # noqa: F401
    from a2a.utils.constants import (  # noqa: F401
        AGENT_CARD_WELL_KNOWN_PATH,
        EXTENDED_AGENT_CARD_PATH,
    )

    assert importlib.util.find_spec("a2a") is not None


def test_uv_lock_exists_for_frozen_docker_sync() -> None:
    """Dockerfile runs `uv sync --frozen`, which requires a committed uv.lock."""
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    if "uv sync --frozen" not in dockerfile:
        pytest.skip("Dockerfile no longer uses `uv sync --frozen`")

    assert UV_LOCK_PATH.exists(), (
        "uv.lock is missing; `uv sync --frozen` in the Dockerfile will fail. "
        "Regenerate it with `uv lock`."
    )
    assert UV_LOCK_PATH.stat().st_size > 0


def test_uv_lock_resolves_from_public_pypi() -> None:
    """Lockfile must not pin an internal mirror the container cannot authenticate to."""
    lock_text = UV_LOCK_PATH.read_text(encoding="utf-8")
    registries = {
        line.strip()
        for line in lock_text.splitlines()
        if line.strip().startswith("source = { registry =")
    }
    non_public = {r for r in registries if "pypi.org/simple" not in r}
    assert not non_public, (
        f"uv.lock references non-public registries which break container builds: {non_public}"
    )


def test_uv_lock_pins_the_same_a2a_sdk_version(declared_dependencies: list[str]) -> None:
    """The lockfile agrees with the pyproject pin for a2a-sdk."""
    pin = next(d for d in declared_dependencies if d.startswith("a2a-sdk"))
    expected_version = pin.split("==")[1].strip()
    lock_text = UV_LOCK_PATH.read_text(encoding="utf-8")
    assert f'name = "a2a-sdk"\nversion = "{expected_version}"' in lock_text
