"""Scenario serialization helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any


def make_scenario(
    name: str,
    assumptions: dict[str, Any],
    overrides: dict[str, Any] | None,
    summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "name": (name or "Scenario").strip() or "Scenario",
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "assumptions": assumptions,
        "overrides": overrides or {},
        "summary": summary or {},
    }


def scenario_options(scenarios: dict[str, Any] | None) -> list[dict[str, str]]:
    if not scenarios:
        return []
    return [{"label": name, "value": name} for name in sorted(scenarios.keys())]


def export_payload(
    scenario_name: str,
    assumptions: dict[str, Any],
    overrides: dict[str, Any] | None,
    model_summary: dict[str, Any],
    simulation_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "scenario_name": (scenario_name or "Export").strip() or "Export",
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "assumptions": assumptions,
        "manual_overrides": overrides or {},
        "model_summary": model_summary,
        "simulation_summary": simulation_summary or {},
    }
