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

"""Shared fixtures for the integration suite.

By default the suite runs fully offline: Gemini completions and GCP credential
bootstrapping are intercepted so no live Vertex AI key, ADC token, or network
egress is required. Export ``MOCK_LLM=FALSE`` to run against the real backend.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.integration.mock_llm import (
    MOCK_RESPONSE_TEXT,
    env_flag,
    install_all,
    uninstall_all,
)


def offline_mode() -> bool:
    """Returns True when the suite should run against mocked backends."""
    return env_flag("MOCK_LLM")


@pytest.fixture(scope="session")
def mock_llm_text() -> str:
    """The deterministic completion text emitted by the mocked Gemini model."""
    return MOCK_RESPONSE_TEXT


@pytest.fixture(scope="session", autouse=True)
def mock_backends() -> Iterator[bool]:
    """Installs the offline Gemini / GCP interceptors for the whole session.

    Yields:
        True when interceptors are active, False when running against live Vertex AI.
    """
    mocked = install_all()
    try:
        yield mocked
    finally:
        if mocked:
            uninstall_all()
