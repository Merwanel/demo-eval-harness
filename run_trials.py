"""Container entrypoint: run trials inside the lab network and write campaign.json."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from harness.campaign import derive_counts, empty_campaign, run_campaign, write_campaign
from harness.scenario import load_scenario

CAMPAIGN_PATH = Path("/app/campaign.json")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run agent trials inside the lab network")
    parser.add_argument(
        "--model",
        default=os.environ.get("GROQ_MODEL"),
        help="Model id for this run (or set GROQ_MODEL). No default is baked in.",
    )
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a single trial",
    )
    args = parser.parse_args(argv)

    if not args.model:
        parser.error("model id required via --model or GROQ_MODEL")

    scenario = load_scenario()
    trials = 1 if args.smoke else scenario.trial_count
    campaign = empty_campaign(scenario, args.model, trials)
    try:
        campaign = run_campaign(model=args.model, scenario=scenario, trials=trials)
    finally:
        write_campaign(CAMPAIGN_PATH, campaign)
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


if __name__ == "__main__":
    raise SystemExit(main())
