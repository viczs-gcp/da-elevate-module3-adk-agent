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

"""Unit tests for Cymbal Operations Coordinator Agent configuration and safety guardrails."""

from app.agent import (
    MODEL,
    SYSTEM_INSTRUCTION,
    app,
    cymbal_operations_agent,
    root_agent,
)


def test_coordinator_agent_identity() -> None:
    """Verifies that the agent has the correct name, model, and export bindings."""
    assert cymbal_operations_agent.name == "cymbal_operations_agent"
    assert MODEL == "gemini-3.6-flash"
    assert root_agent is cymbal_operations_agent
    assert app.root_agent is cymbal_operations_agent


def test_coordinator_agent_tools_bound() -> None:
    """Verifies that all 3 specialized tool gateways are bound to the agent."""
    assert len(cymbal_operations_agent.tools) == 3


def test_coordinator_instruction_protocols() -> None:
    """Verifies that all required dispatch and safety protocols are present in instructions."""
    # Check 3 tool gateways mentioned
    assert "cymbal_analytics_tool" in SYSTEM_INSTRUCTION
    assert "pos_troubleshooting_rag_tool" in SYSTEM_INSTRUCTION
    assert "read_cashier_realtime_alerts" in SYSTEM_INSTRUCTION

    # Check 5 dispatch protocols
    assert "SINGLE-TOOL DISPATCH" in SYSTEM_INSTRUCTION
    assert "PARALLEL TOOL DISPATCH" in SYSTEM_INSTRUCTION
    assert "SEQUENTIAL MULTI-TURN DISPATCH" in SYSTEM_INSTRUCTION
    assert "TEMPORAL DATE CHECK & CLARIFICATION" in SYSTEM_INSTRUCTION
    assert "STRICT GROUNDING" in SYSTEM_INSTRUCTION

    # Check exact refusal sentence directive
    assert "reply ONLY with that exact refusal sentence" in SYSTEM_INSTRUCTION
