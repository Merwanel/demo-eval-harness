"""Bring the lab up, run a campaign of trials, write campaign.json, tear down."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from harness.agent import make_client, provider_name, run_trial
from harness.constants import (
    LAB_NETWORK,
    RUNNER_IMAGE,
    SCENARIO_ID,
    STEP_LIMIT,
    TRIAL_COUNT,
)

ROOT = Path(__file__).resolve().parents[1]
ANSIBLE_UP = ROOT / "ansible" / "up.yml"
ANSIBLE_DOWN = ROOT / "ansible" / "down.yml"
CAMPAIGN_PATH = ROOT / "campaign.json"


def _ansible_playbook(playbook: Path) -> None:
    env = os.environ.copy()
    # Prefer the project venv's ansible when present.
    venv_playbook = ROOT / ".venv" / "bin" / "ansible-playbook"
    binary = str(venv_playbook) if venv_playbook.exists() else "ansible-playbook"
    subprocess.run([binary, str(playbook)], check=True, cwd=str(ROOT), env=env)


def _docker(*args: str) -> None:
    subprocess.run(["docker", *args], check=True, cwd=str(ROOT))


def build_runner_image() -> None:
    _docker("build", "-t", RUNNER_IMAGE, "-f", "Dockerfile", ".")


def derive_counts(runs: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "successes": sum(1 for run in runs if run.get("outcome") == "success"),
        "agent_failures": sum(1 for run in runs if run.get("outcome") == "agent_failure"),
        "harness_errors": sum(1 for run in runs if run.get("outcome") == "harness_error"),
    }


def write_campaign(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def run_campaign_inner(*, model: str, trials: int, step_limit: int) -> dict[str, Any]:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    client = make_client(api_key)
    runs: list[dict[str, Any]] = []
    for index in range(1, trials + 1):
        result = run_trial(client, model, step_limit=step_limit)
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
        "scenario": SCENARIO_ID,
        "provider": provider_name(),
        "model": model,
        "trials": trials,
        **counts,
        "runs": runs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an agent evaluation campaign")
    parser.add_argument(
        "--model",
        default=os.environ.get("GROQ_MODEL"),
        help="Model id for this run (or set GROQ_MODEL). No default is baked in.",
    )
    parser.add_argument(
        "--inner",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=TRIAL_COUNT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--step-limit",
        type=int,
        default=STEP_LIMIT,
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Leave the lab container up after the campaign",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a single trial (still inside the lab network)",
    )
    args = parser.parse_args(argv)

    if not args.model:
        parser.error("model id required via --model or GROQ_MODEL")

    trials = 1 if args.smoke else args.trials

    if args.inner:
        campaign: dict[str, Any] = {
            "scenario": SCENARIO_ID,
            "provider": provider_name(),
            "model": args.model,
            "trials": trials,
            "successes": 0,
            "agent_failures": 0,
            "harness_errors": 0,
            "runs": [],
        }
        try:
            campaign = run_campaign_inner(
                model=args.model,
                trials=trials,
                step_limit=args.step_limit,
            )
        finally:
            write_campaign(Path("/app/campaign.json"), campaign)
            # Also print a one-line summary for the orchestrator logs.
            counts = derive_counts(campaign["runs"])
            print(
                json.dumps(
                    {
                        "scenario": campaign["scenario"],
                        "model": campaign["model"],
                        **counts,
                    }
                ),
                flush=True,
            )
        return 0

    # Host path: ensure the output file exists so docker can bind-mount it.
    if not CAMPAIGN_PATH.exists():
        write_campaign(
            CAMPAIGN_PATH,
            {
                "scenario": SCENARIO_ID,
                "provider": provider_name(),
                "model": args.model,
                "trials": trials,
                "successes": 0,
                "agent_failures": 0,
                "harness_errors": 0,
                "runs": [],
            },
        )

    # Smoke and full campaigns share the orchestrator; smoke overrides trial count
    # by rewriting the inner invocation through an env var the image reads… simpler:
    # rebuild args for docker. For smoke, call docker with --smoke.
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    lab_up = False
    try:
        _ansible_playbook(ANSIBLE_UP)
        lab_up = True
        build_runner_image()
        # Pass -e GROQ_API_KEY with no value so Docker copies it from the host
        # environment; the key never appears in argv (or in CalledProcessError).
        # Image ENTRYPOINT is already `python -m harness.runner`, so only flags follow.
        inner_args = [
            "run",
            "--rm",
            "--network",
            LAB_NETWORK,
            "-e",
            "GROQ_API_KEY",
            "-e",
            f"GROQ_MODEL={args.model}",
            "-v",
            f"{CAMPAIGN_PATH}:/app/campaign.json",
            RUNNER_IMAGE,
            "--inner",
            "--model",
            args.model,
            "--trials",
            str(trials),
            "--step-limit",
            str(args.step_limit),
        ]
        _docker(*inner_args)
    finally:
        # Persist is handled inside the container; host still tears down.
        if lab_up and not args.keep:
            try:
                _ansible_playbook(ANSIBLE_DOWN)
            except Exception as exc:  # noqa: BLE001
                print(f"warning: lab teardown failed: {exc}", file=sys.stderr)

    if CAMPAIGN_PATH.exists():
        summary = json.loads(CAMPAIGN_PATH.read_text(encoding="utf-8"))
        counts = derive_counts(summary.get("runs", []))
        print(
            f"campaign written to {CAMPAIGN_PATH} "
            f"(successes={counts['successes']}, "
            f"agent_failures={counts['agent_failures']}, "
            f"harness_errors={counts['harness_errors']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
