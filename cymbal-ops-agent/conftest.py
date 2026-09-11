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

"""Root pytest configuration.

Loaded by pytest before any test module (and therefore before ``app.config`` is
imported), so environment defaults set here are observed by the configuration
layer.

The BigQuery Agent Analytics plugin streams telemetry to a live BigQuery dataset
via the Write API. Disable it by default so the suite stays hermetic and does not
emit test traffic into ``agent_telemetry``. Export ``BQ_TELEMETRY_ENABLED=TRUE``
explicitly to exercise the real plugin.
"""

from __future__ import annotations

import os

os.environ.setdefault("BQ_TELEMETRY_ENABLED", "FALSE")
