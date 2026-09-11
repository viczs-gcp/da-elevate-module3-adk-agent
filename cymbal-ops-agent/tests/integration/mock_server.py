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

"""Uvicorn entrypoint that boots the real FastAPI app behind offline mock interceptors.

``test_server_e2e.py`` launches the server in a **subprocess**, so in-process
``unittest.mock`` patches from the test session cannot reach it. This module is
imported by that subprocess instead of ``app.fast_api_app`` directly: it installs
the Gemini / GCP interceptors *before* the application module is imported, then
re-exports the identical ASGI ``app`` object.

Usage::

    uvicorn tests.integration.mock_server:app --host 0.0.0.0 --port 8000

Set ``MOCK_LLM=FALSE`` to fall through to the live Vertex AI backend.
"""

from __future__ import annotations

from tests.integration.mock_llm import install_all

# Must run before `app.fast_api_app` is imported: that module calls
# google.auth.default() and constructs a Cloud Logging client at import time.
MOCKED = install_all()

from app.fast_api_app import app  # noqa: E402  (import intentionally deferred)

__all__ = ["MOCKED", "app"]
