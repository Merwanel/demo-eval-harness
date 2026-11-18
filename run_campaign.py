"""Host driver: bring the lab up, run the campaign container, tear down."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from harness.campaign import derive_counts, empty_campaign, write_campaign
from harness.scenario import load_scenario

ROOT = Path(__file__).resolve().parent
ANSIBLE_UP = ROOT / "ansible" / "up.yml"
ANSIBLE_DOWN = ROOT / "ansible" / "down.yml"
CAMPAIGNS_DIR = ROOT / "campaigns"
SCENARIO_PATH = ROOT / "scenario.yml"

LAB_NETWORK = "lab"
EGRESS_NETWORK = "egress"
RUNNER_IMAGE = "demo-eval-harness-runner"


def campaign_path_for(model: str, when: datetime | None = None) -> Path:
    """campaigns/<date>_<hour>_<model>.json — model slashes become hyphens."""
    stamp = when or datetime.now(timezone.utc)
    date = stamp.strftime("%Y-%m-%d")
    hour = stamp.strftime("%H%M")
    safe_model = re.sub(r"[^\w.-]+", "-", model).strip("-")
    return CAMPAIGNS_DIR / f"{date}_{hour}_{safe_model}.json"


def _ansible_playbook(playbook: Path) -> None:
    env = os.environ.copy()
    venv_playbook = ROOT / ".venv" / "bin" / "ansible-playbook"
    binary = str(venv_playbook) if venv_playbook.exists() else "ansible-playbook"
    subprocess.run([binary, str(playbook)], check=True, cwd=str(ROOT), env=env)


def _docker(*args: str) -> None:
    subprocess.run(["docker", *args], check=True, cwd=str(ROOT))


def build_runner_image() -> None:
    _docker("build", "-t", RUNNER_IMAGE, "-f", "Dockerfile", ".")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an agent evaluation campaign")
    parser.add_argument(
        "--model",
        default=os.environ.get("GROQ_MODEL"),
        help="Model id for this run (or set GROQ_MODEL). No default is baked in.",
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

    scenario = load_scenario(SCENARIO_PATH)
    trials = 1 if args.smoke else scenario.trial_count
    campaign_path = campaign_path_for(args.model)

    # File must exist before docker can bind-mount it.
    CAMPAIGNS_DIR.mkdir(parents=True, exist_ok=True)
    write_campaign(campaign_path, empty_campaign(scenario, args.model, trials))

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise SystemExit("GROQ_API_KEY is required")

    lab_up = False
    try:
        _ansible_playbook(ANSIBLE_UP)
        lab_up = True
        build_runner_image()
        docker_args = [
            "run",
            "--rm",
            # egress first so the runner keeps a default route to the model API;
            # lab is internal (no route off it) and only provides the target hosts.
            "--network",
            EGRESS_NETWORK,
            "--network",
            LAB_NETWORK,
            "-e",
            "GROQ_API_KEY",
            "-e",
            f"GROQ_MODEL={args.model}",
            "-v",
            f"{campaign_path}:/app/campaign.json",
            RUNNER_IMAGE,
            "--model",
            args.model,
        ]
        if args.smoke:
            docker_args.append("--smoke")
        _docker(*docker_args)
    finally:
        if lab_up and not args.keep:
            try:
                _ansible_playbook(ANSIBLE_DOWN)
            except Exception as exc:  # noqa: BLE001
                print(f"warning: lab teardown failed: {exc}", file=sys.stderr)

    if campaign_path.exists():
        summary = json.loads(campaign_path.read_text(encoding="utf-8"))
        counts = derive_counts(summary.get("runs", []))
        print(
            f"campaign written to {campaign_path} "
            f"(successes={counts['successes']}, "
            f"agent_failures={counts['agent_failures']}, "
            f"harness_errors={counts['harness_errors']})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
