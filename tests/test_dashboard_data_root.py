from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest

from dashboard import data as dashboard_data
from engine import what_if_simulator
from services import tools


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _recommendation_row(**updates: object) -> dict[str, object]:
    row: dict[str, object] = {
        "demand_week": "2026-11-16",
        "skill_id": "SKL-000001",
        "skill_name": "Test Skill",
        "gap_hours": 15.0,
        "internal_employees": 2,
        "internal_available_hours": 7.0,
        "remaining_gap": 8.0,
        "potential_trainees": 1,
        "recommendation": "Training",
    }
    row.update(updates)
    return row


def test_default_data_root_is_project_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WORKFORCEIQ_DATA_ROOT", raising=False)
    expected = (PROJECT_ROOT / "data").resolve()

    assert dashboard_data.get_data_root() == expected
    assert tools.get_data_root() == expected
    assert what_if_simulator.get_data_root() == expected


def test_dashboard_csv_cache_is_separated_by_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    _write_csv(first_root / "processed" / "probe.csv", [{"value": "first"}])
    _write_csv(second_root / "processed" / "probe.csv", [{"value": "second"}])
    _write_csv(first_root / "raw" / "projects.csv", [{"project_id": "P-FIRST"}])
    _write_csv(second_root / "raw" / "projects.csv", [{"project_id": "P-SECOND"}])

    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(first_root))
    assert dashboard_data.load_csv("probe.csv").iloc[0]["value"] == "first"
    assert dashboard_data.load_csv("../projects.csv").iloc[0]["project_id"] == "P-FIRST"

    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(second_root))
    assert dashboard_data.load_csv("probe.csv").iloc[0]["value"] == "second"
    assert dashboard_data.load_csv("../projects.csv").iloc[0]["project_id"] == "P-SECOND"


def test_dashboard_other_readers_use_the_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "configured"
    _write_csv(root / "processed" / "sample.csv", [{"value": 1}, {"value": 2}])
    _write_csv(root / "raw" / "employees.csv", [{"status": "active"}, {"status": "inactive"}])
    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(root))

    assert dashboard_data.read_head("sample.csv", rows=1)["value"].tolist() == [1]
    assert dashboard_data.get_csv_rows("sample.csv") == 2
    assert dashboard_data.get_employee_count() == 1


def test_service_tools_read_from_the_configured_processed_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "configured"
    _write_csv(root / "processed" / "workforce_recommendations.csv", [_recommendation_row()])
    _write_csv(
        root / "processed" / "talent_discovery.csv",
        [{
            "skill_name": "Test Skill",
            "is_qualified": True,
            "skill_status": "Current",
            "proficiency_level": 4,
            "skill_available_hours": 6.0,
            "availability_date": "2026-11-16",
            "employee_id": "EMP-000001",
            "employee_name": "Test Employee",
            "role_id": "ROLE-000001",
            "employment_type": "Full-time",
            "available_hours": 10.0,
        }],
    )
    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(root))

    shortage = tools.analyze_skill_shortage("Test Skill", "2026-11-16")
    talent = tools.find_internal_talent("Test Skill", "2026-11-16", 3, 10)

    assert shortage["status"] == "success"
    assert shortage["records"][0]["skill_id"] == "SKL-000001"
    assert talent["status"] == "success"
    assert talent["employees"][0]["employee_id"] == "EMP-000001"


@pytest.mark.parametrize(
    ("wrapper_name", "service_name", "arguments"),
    [
        ("shortage_tool", "analyze_skill_shortage", ("Test Skill", "2026-11-16")),
        ("talent_tool", "find_internal_talent", ("Test Skill", "2026-11-16", 3, 10)),
        ("strategy_tool", "compare_workforce_strategies", ("SKL-000001", "2026-11-16")),
    ],
)
def test_tool_cache_is_isolated_by_data_root_and_reused_within_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    wrapper_name: str,
    service_name: str,
    arguments: tuple[object, ...],
) -> None:
    first_root = (tmp_path / "first").resolve()
    second_root = (tmp_path / "second").resolve()
    calls: list[Path] = []

    def fake_service(*_: object) -> dict[str, str]:
        current_root = tools.get_data_root()
        calls.append(current_root)
        return {"root": str(current_root)}

    monkeypatch.setattr(tools, service_name, fake_service)
    cached_function = getattr(dashboard_data, f"_cached_{wrapper_name}")
    cached_function.clear()
    wrapper = getattr(dashboard_data, wrapper_name)

    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(first_root))
    first_result = wrapper(*arguments)
    assert first_result["root"] == str(first_root)

    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(second_root))
    second_result = wrapper(*arguments)
    assert second_result["root"] == str(second_root)
    assert wrapper(*arguments) == second_result

    assert calls == [first_root, second_root]


def test_simulator_reads_each_input_from_current_configured_root(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = tmp_path / "configured"
    expected = [
        root / "processed" / "workforce_recommendations.csv",
        root / "processed" / "talent_discovery.csv",
        root / "processed" / "skill_intelligence.csv",
        root / "processed" / "capacity_analysis.csv",
        root / "raw" / "training.csv",
    ]
    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(root))
    seen: list[Path] = []

    def fake_read_csv(path: os.PathLike[str] | str, **_: object) -> pd.DataFrame:
        seen.append(Path(path))
        return pd.DataFrame()

    monkeypatch.setattr(what_if_simulator.pd, "read_csv", fake_read_csv)
    result = what_if_simulator.load_data()

    assert seen == expected
    assert set(result) == {"recommendations", "talent", "skills", "capacity", "training"}

    seen.clear()
    monkeypatch.setattr(
        what_if_simulator,
        "compare_scenarios",
        lambda data, demand_week, skill_id: pd.DataFrame([{
            "strategy": "Internal Reallocation",
            "hours_resolved": 4.0,
            "remaining_gap": 1.0,
            "estimated_cost": 0.0,
        }]),
    )
    scenarios = tools.compare_workforce_strategies("SKL-000001", "2026-11-16")

    assert seen == expected
    assert scenarios["status"] == "success"
    assert scenarios["scenarios"][0]["strategy"] == "Internal Reallocation"


def test_run_a_data_root_is_shared_by_dashboard_and_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured_root = os.environ.get("WORKFORCEIQ_TEST_DATA_ROOT")
    if not configured_root:
        pytest.skip("Set WORKFORCEIQ_TEST_DATA_ROOT to run the Run A data smoke test")
    root = Path(configured_root).resolve()
    assert root.is_dir()
    monkeypatch.setenv("WORKFORCEIQ_DATA_ROOT", str(root))

    assert dashboard_data.get_data_root() == tools.get_data_root() == what_if_simulator.get_data_root() == root
    recommendations = dashboard_data.load_csv("workforce_recommendations.csv")
    assert len(recommendations) == 6779
    employees = dashboard_data.load_csv("../employees.csv")
    assert len(employees) == 5000
    expected_active = int((employees.status.astype(str).str.casefold() == "active").sum())
    assert dashboard_data.get_employee_count() == expected_active
    assert len(dashboard_data.load_csv("../skills.csv")) == 300

    first = recommendations.iloc[0]
    result = tools.analyze_skill_shortage(str(first.skill_name), str(first.demand_week))
    assert result["status"] == "success"
    assert result["records"][0]["skill_id"] == str(first.skill_id)
