"""Run a campaign of trials and write campaign.json."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness.agent import make_client, provider_name, run_trial
from harness.scenario import Scenario


def derive_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "successes": sum(1 for run in runs if run.get("outcome") == "success"),
        "agent_failures": sum(1 for run in runs if run.get("outcome") == "agent_failure"),
        "harness_errors": sum(1 for run in runs if run.get("outcome") == "harness_error"),
    }


def write_campaign(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def empty_campaign(scenario: Scenario, model: str, trials: int) -> dict[str, Any]:
    return {
        "scenario": scenario.id,
        "provider": provider_name(),
        "model": model,
        "trials": trials,
        "successes": 0,
        "agent_failures": 0,
        "harness_errors": 0,
        "runs": [],
    }


def run_campaign(*, model: str, scenario: Scenario, trials: int) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    client = make_client(api_key)
    runs: list[dict[str, Any]] = []
    for index in range(1, trials + 1):
        result = run_trial(client, model, scenario)
        runs.append(
            {
                "trial": index,
                "outcome": result["outcome"],
                "answer": result.get("answer", ""),
                "steps": result.get("steps", []),
            }
        )

    counts = derive_counts(runs)
    return {
        "scenario": scenario.id,
        "provider": provider_name(),
        "model": model,
        "trials": trials,
        **counts,
        "runs": runs,
    }
