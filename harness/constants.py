"""Harness and provider constants that are not part of the task description.

Task values live in scenario.yml and are loaded by harness.scenario.
"""

from __future__ import annotations

PROVIDER = "groq"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REASONING_EFFORT = "low"

RETRY_MAX_WAIT_SECONDS = 120
RETRY_MAX_CONSECUTIVE_429 = 3

LAB_NETWORK = "lab"
RUNNER_IMAGE = "demo-eval-harness-runner"
