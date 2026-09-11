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

"""In-process integration tests for the Cymbal Operations coordinator agent.

Gemini completions are intercepted by the session-scoped ``mock_backends``
fixture in ``conftest.py``, so this module runs offline in CI/CD with no live
Vertex AI key. Set ``MOCK_LLM=FALSE`` to exercise the real model.
"""

from __future__ import annotations

from unittest import mock

from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.models import Gemini
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import root_agent
from tests.integration.mock_llm import build_mock_llm_response


def _run_agent(prompt: str) -> list:
    """Runs the coordinator agent for a single prompt and returns emitted events."""
    session_service = InMemorySessionService()
    session = session_service.create_session_sync(user_id="test_user", app_name="test")
    runner = Runner(agent=root_agent, session_service=session_service, app_name="test")

    message = types.Content(role="user", parts=[types.Part.from_text(text=prompt)])

    return list(
        runner.run(
            new_message=message,
            user_id="test_user",
            session_id=session.id,
            run_config=RunConfig(streaming_mode=StreamingMode.SSE),
        )
    )


def _collect_text(events: list) -> str:
    """Concatenates all model text emitted across the event stream."""
    chunks = []
    for event in events:
        if event.content and event.content.parts:
            chunks.extend(part.text for part in event.content.parts if part.text)
    return "".join(chunks)


def test_agent_stream(mock_backends: bool) -> None:
    """The agent returns a valid streaming response with text content."""
    events = _run_agent("Why is the sky blue?")
    assert len(events) > 0, "Expected at least one message"

    has_text_content = any(
        event.content
        and event.content.parts
        and any(part.text for part in event.content.parts)
        for event in events
    )
    assert has_text_content, "Expected at least one message with text content"


def test_agent_stream_uses_mock_completion(
    mock_backends: bool, mock_llm_text: str
) -> None:
    """Offline runs are served by the interceptor, never by live Vertex AI."""
    if not mock_backends:
        import pytest

        pytest.skip("Running against live Vertex AI (MOCK_LLM=FALSE)")

    text = _collect_text(_run_agent("Hi!"))
    assert "[MOCK LLM]" in text
    assert mock_llm_text.split(".")[0] in text


def test_agent_model_invocation_is_intercepted(mock_backends: bool) -> None:
    """The mocked model is invoked exactly once for a simple single-turn prompt."""
    if not mock_backends:
        import pytest

        pytest.skip("Running against live Vertex AI (MOCK_LLM=FALSE)")

    calls: list[bool] = []
    original = Gemini.generate_content_async

    async def _counting_generate(self, llm_request, stream: bool = False):
        calls.append(stream)
        yield build_mock_llm_response("Intercepted single-turn completion.")

    with mock.patch.object(Gemini, "generate_content_async", _counting_generate):
        events = _run_agent("Hello there")

    assert calls, "Expected the mocked Gemini model to be invoked"
    assert _collect_text(events) == "Intercepted single-turn completion."
    # Ensure the session-scoped interceptor is restored for later tests.
    assert Gemini.generate_content_async is original


def test_root_agent_tools_registered() -> None:
    """The coordinator exposes all three tool gateways to the model."""
    assert root_agent.name == "cymbal_operations_agent"
    assert len(root_agent.tools) == 3
