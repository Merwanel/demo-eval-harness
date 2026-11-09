"""Task values for the web-token lab.

Named constants at the top of the module so a later reader can replace them
without reshaping the code that consumes them.
"""

from __future__ import annotations

SCENARIO_ID = "web-token"

GOAL = "Find the lab token and report it exactly."

START_URL = "http://web/"

EXPECTED_ANSWER = "LAB-TOKEN-1842"

TOOLS = ("http_get", "submit")

TRIAL_COUNT = 5

STEP_LIMIT = 8

# Lab pages served by the web host. Path relative to the document root,
# plus the exact body. Kept here so the runner and playbook share one source
# once a file reader lands; for now the playbook still builds from lab/pages.
HOSTS = (
    {
        "name": "web",
        "pages": (
            {"path": "index.html", "body": "The token is at http://web/token.txt"},
            {"path": "token.txt", "body": "LAB-TOKEN-1842"},
        ),
    },
)

PROVIDER = "groq"
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
REASONING_EFFORT = "low"

RETRY_MAX_WAIT_SECONDS = 120
RETRY_MAX_CONSECUTIVE_429 = 3

LAB_NETWORK = "lab"
LAB_IMAGE = "demo-eval-harness-web"
RUNNER_IMAGE = "demo-eval-harness-runner"
WEB_CONTAINER = "web"
