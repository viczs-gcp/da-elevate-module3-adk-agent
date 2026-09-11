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

"""Offline mock interceptors for Gemini completions and GCP client bootstrapping.

These interceptors let the integration suite (``test_agent.py`` and
``test_server_e2e.py``) run in a CI/CD pipeline with **no live Vertex AI keys,
no ADC, and no network egress**.

Two independent interceptors are provided:

* :func:`install_mock_gemini` - replaces
  ``google.adk.models.Gemini.generate_content_async`` with a deterministic
  async generator that yields canned :class:`LlmResponse` chunks.
* :func:`install_mock_gcp_clients` - stubs ``google.auth.default`` and the
  Cloud Logging client so that importing ``app.fast_api_app`` does not require
  Application Default Credentials.

Both are activated automatically by :func:`install_all` when the
``MOCK_LLM`` environment variable is truthy (the default for the integration
suite). Set ``MOCK_LLM=FALSE`` to exercise the live Vertex AI backend.
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from typing import Any
from unittest import mock

MOCK_RESPONSE_TEXT = (
    "[MOCK LLM] Cymbal Retail Operations Coordinator acknowledged the request. "
    "This deterministic completion is served by the offline integration test "
    "interceptor; no live Vertex AI call was made."
)

# Sentinels so repeated imports (pytest + uvicorn worker) stay idempotent.
_GEMINI_PATCHER: Any = None
_GCP_PATCHERS: list[Any] = []


def env_flag(name: str, default: str = "TRUE") -> bool:
    """Reads a truthy/falsy environment flag.

    Args:
        name: Environment variable name.
        default: Value used when the variable is unset.

    Returns:
        True when the value is one of ``1/true/yes/on`` (case-insensitive).
    """
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}


def build_mock_llm_response(text: str = MOCK_RESPONSE_TEXT, *, partial: bool = False) -> Any:
    """Builds a single canned ADK ``LlmResponse`` carrying model text.

    Args:
        text: Response text emitted by the mock model.
        partial: Whether the chunk is a streaming partial rather than the final turn.

    Returns:
        An ``LlmResponse`` instance shaped like a real Gemini completion.
    """
    from google.adk.models import LlmResponse
    from google.genai import types

    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        partial=partial,
        turn_complete=not partial,
    )


def install_mock_gemini(text: str = MOCK_RESPONSE_TEXT) -> None:
    """Intercepts Gemini completions with a deterministic offline generator.

    Patches ``google.adk.models.Gemini.generate_content_async`` on the class, so
    every already-constructed agent instance is intercepted as well.

    Args:
        text: Response text the mocked model should emit.
    """
    global _GEMINI_PATCHER
    if _GEMINI_PATCHER is not None:
        return

    from google.adk.models import Gemini

    async def _mock_generate_content_async(
        self: Any, llm_request: Any, stream: bool = False
    ) -> AsyncGenerator[Any, None]:
        """Yields canned completions instead of calling the Vertex AI backend."""
        if stream:
            # Emit two partial chunks then the aggregated final turn, mirroring SSE.
            midpoint = max(1, len(text) // 2)
            yield build_mock_llm_response(text[:midpoint], partial=True)
            yield build_mock_llm_response(text[midpoint:], partial=True)
        yield build_mock_llm_response(text)

    _GEMINI_PATCHER = mock.patch.object(
        Gemini, "generate_content_async", _mock_generate_content_async
    )
    _GEMINI_PATCHER.start()


def install_mock_gcp_clients() -> None:
    """Stubs ADC and Cloud Logging so module import works without GCP credentials."""
    if _GCP_PATCHERS:
        return

    import google.auth
    from google.auth import credentials as ga_credentials

    mock_credentials = mock.create_autospec(ga_credentials.Credentials, instance=True)
    mock_credentials.valid = True

    auth_patcher = mock.patch.object(
        google.auth, "default", return_value=(mock_credentials, "mock-project")
    )
    auth_patcher.start()
    _GCP_PATCHERS.append(auth_patcher)

    try:
        from google.cloud import logging as google_cloud_logging

        logging_patcher = mock.patch.object(
            google_cloud_logging, "Client", autospec=True
        )
        logging_patcher.start()
        _GCP_PATCHERS.append(logging_patcher)
    except ImportError:  # pragma: no cover - optional dependency
        pass


def install_all(text: str = MOCK_RESPONSE_TEXT) -> bool:
    """Installs every interceptor when ``MOCK_LLM`` is enabled.

    Args:
        text: Response text the mocked model should emit.

    Returns:
        True when the interceptors were installed, False when running live.
    """
    if not env_flag("MOCK_LLM"):
        return False
    install_mock_gcp_clients()
    install_mock_gemini(text)
    return True


def uninstall_all() -> None:
    """Removes all installed interceptors (used by pytest fixture teardown)."""
    global _GEMINI_PATCHER
    if _GEMINI_PATCHER is not None:
        _GEMINI_PATCHER.stop()
        _GEMINI_PATCHER = None
    while _GCP_PATCHERS:
        _GCP_PATCHERS.pop().stop()


__all__ = [
    "MOCK_RESPONSE_TEXT",
    "build_mock_llm_response",
    "env_flag",
    "install_all",
    "install_mock_gcp_clients",
    "install_mock_gemini",
    "uninstall_all",
]
