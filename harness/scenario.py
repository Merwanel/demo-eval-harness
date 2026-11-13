"""Load and validate scenario.yml as the single task description."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SCENARIO_PATH = ROOT / "scenario.yml"

REQUIRED_FIELDS = frozenset(
    {
        "id",
        "hosts",
        "goal",
        "check",
        "tools",
        "start_url",
        "trial_count",
        "step_limit",
    }
)


@dataclass(frozen=True)
class Page:
    path: str
    body: str


@dataclass(frozen=True)
class Host:
    name: str
    pages: tuple[Page, ...]


@dataclass(frozen=True)
class Scenario:
    id: str
    hosts: tuple[Host, ...]
    goal: str
    check: str
    tools: tuple[str, ...]
    start_url: str
    trial_count: int
    step_limit: int


class ScenarioError(ValueError):
    """scenario.yml is missing a field, has an unknown field, or fails a rule."""


def _require_str(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ScenarioError(f"{field} must be a non-empty string")
    return value


def _require_positive_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ScenarioError(f"{field} must be a positive integer")
    return value


def _parse_page(raw: Any, host_name: str, index: int) -> Page:
    label = f"hosts[{host_name!r}].pages[{index}]"
    if not isinstance(raw, dict):
        raise ScenarioError(f"{label} must be a mapping")
    unknown = set(raw) - {"path", "body"}
    if unknown:
        raise ScenarioError(f"{label} has unknown field(s): {sorted(unknown)}")
    for key in ("path", "body"):
        if key not in raw:
            raise ScenarioError(f"{label} is missing field {key!r}")
    path = raw["path"]
    body = raw["body"]
    if not isinstance(path, str) or not path or path.startswith("/"):
        raise ScenarioError(f"{label}.path must be a relative path string")
    if not isinstance(body, str):
        raise ScenarioError(f"{label}.body must be a string")
    return Page(path=path, body=body)


def _parse_host(raw: Any, index: int) -> Host:
    label = f"hosts[{index}]"
    if not isinstance(raw, dict):
        raise ScenarioError(f"{label} must be a mapping")
    unknown = set(raw) - {"name", "pages"}
    if unknown:
        raise ScenarioError(f"{label} has unknown field(s): {sorted(unknown)}")
    if "name" not in raw:
        raise ScenarioError(f"{label} is missing field 'name'")
    if "pages" not in raw:
        raise ScenarioError(f"{label} is missing field 'pages'")
    name = _require_str(raw["name"], f"{label}.name")
    pages_raw = raw["pages"]
    if not isinstance(pages_raw, list) or not pages_raw:
        raise ScenarioError(f"host {name!r} must have a non-empty pages list")
    pages = tuple(_parse_page(page, name, i) for i, page in enumerate(pages_raw))
    return Host(name=name, pages=pages)


def load_scenario(path: Path | None = None) -> Scenario:
    scenario_path = path if path is not None else DEFAULT_SCENARIO_PATH
    try:
        text = scenario_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ScenarioError(f"cannot read {scenario_path}: {exc}") from exc

    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ScenarioError(f"invalid YAML in {scenario_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ScenarioError("scenario.yml must be a mapping at the top level")

    missing = REQUIRED_FIELDS - set(data)
    if missing:
        raise ScenarioError(f"missing field(s): {sorted(missing)}")
    unknown = set(data) - REQUIRED_FIELDS
    if unknown:
        raise ScenarioError(f"unknown field(s): {sorted(unknown)}")

    hosts_raw = data["hosts"]
    if not isinstance(hosts_raw, list) or not hosts_raw:
        raise ScenarioError("hosts must be a non-empty list")
    hosts = tuple(_parse_host(host, i) for i, host in enumerate(hosts_raw))

    tools_raw = data["tools"]
    if not isinstance(tools_raw, list) or not tools_raw:
        raise ScenarioError("tools must be a non-empty list")
    tools: list[str] = []
    for i, tool in enumerate(tools_raw):
        if not isinstance(tool, str) or not tool:
            raise ScenarioError(f"tools[{i}] must be a non-empty string")
        tools.append(tool)

    return Scenario(
        id=_require_str(data["id"], "id"),
        hosts=hosts,
        goal=_require_str(data["goal"], "goal"),
        check=_require_str(data["check"], "check"),
        tools=tuple(tools),
        start_url=_require_str(data["start_url"], "start_url"),
        trial_count=_require_positive_int(data["trial_count"], "trial_count"),
        step_limit=_require_positive_int(data["step_limit"], "step_limit"),
    )
