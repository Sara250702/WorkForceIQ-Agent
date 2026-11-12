"""Prepare and atomically inject the four approved Run B anomalies."""

from __future__ import annotations

import csv
from datetime import date, timedelta
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

import pandas as pd

from generator.anomaly_spec import (
    ANOMALY_REFERENCE_DATE,
    ANOMALY_SEED,
    EXPECTED_ANOMALIES,
    GROUND_TRUTH_COLUMNS,
)
from generator.config import HORIZON_END, HORIZON_START


class AnomalyPreconditionError(RuntimeError):
    """Raised before any staged CSV is changed when a candidate differs."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AnomalyPreconditionError(message)


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.is_file():
        raise AnomalyPreconditionError(f"Required staged CSV is missing: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _one_row(frame: pd.DataFrame, column: str, value: str, label: str) -> pd.Series:
    matches = frame[frame[column].astype(str) == value]
    _require(len(matches) == 1, f"Expected exactly one {label}={value}; found {len(matches)}.")
    return matches.iloc[0]


def _iso_date(value: str, label: str) -> date:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError) as error:
        raise AnomalyPreconditionError(f"Invalid {label}: {value!r}") from error


def _number(value: str, label: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise AnomalyPreconditionError(f"Invalid numeric {label}: {value!r}") from error


def _next_numeric_id(values, pattern: str, prefix: str, width: int, label: str) -> str:
    numbers = []
    for value in values:
        match = re.fullmatch(pattern, str(value))
        _require(match is not None, f"Unexpected {label} format: {value!r}")
        numbers.append(int(match.group(1)))
    _require(bool(numbers), f"Cannot allocate a new {label}; no existing IDs were found.")
    return f"{prefix}{max(numbers) + 1:0{width}d}"


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _record(series: pd.Series) -> dict[str, str]:
    return {str(key): str(value) for key, value in series.to_dict().items()}


def _logical_demand_key(row: pd.Series) -> tuple[str, ...]:
    return tuple(
        str(row[column])[:10] if column == "demand_week" else str(row[column])
        for column in ("project_id", "role_id", "skill_id", "demand_week", "demand_type")
    )


def build_injection_plan(
    data_root: Path,
    seed: int = ANOMALY_SEED,
    reference_date: date = ANOMALY_REFERENCE_DATE,
) -> tuple[dict[str, pd.DataFrame], pd.DataFrame, dict[str, dict]]:
    """Validate every approved candidate and build changed frames in memory.

    No file is written by this function. All four scenarios must pass their
    preconditions before a plan is returned to the transactional writer.
    """
    _require(seed == ANOMALY_SEED, f"Run B anomaly seed must be {ANOMALY_SEED}.")
    _require(
        reference_date == ANOMALY_REFERENCE_DATE,
        f"Run B reference date must be {ANOMALY_REFERENCE_DATE.isoformat()}.",
    )

    raw_dir = Path(data_root) / "raw"
    processed_dir = Path(data_root) / "processed"
    allocations = _read_csv(raw_dir / "allocations.csv")
    availability = _read_csv(raw_dir / "availability.csv")
    projects = _read_csv(raw_dir / "projects.csv")
    employees = _read_csv(raw_dir / "employees.csv")
    roles = _read_csv(raw_dir / "roles.csv")
    skills = _read_csv(raw_dir / "skills.csv")
    demand = _read_csv(raw_dir / "demand_plans.csv")
    employee_skills = _read_csv(raw_dir / "employee_skills.csv")
    skill_intelligence = _read_csv(processed_dir / "skill_intelligence.csv")
    capacity = _read_csv(processed_dir / "capacity_analysis.csv")

    for column in (
        "allocation_id", "employee_id", "project_id", "allocation_start",
        "allocation_end", "allocated_hours", "allocation_status",
    ):
        _require(column in allocations.columns, f"allocations.csv lacks {column!r}.")
    for column in (
        "demand_id", "project_id", "role_id", "skill_id", "demand_week",
        "required_employees", "required_hours", "demand_type",
    ):
        _require(column in demand.columns, f"demand_plans.csv lacks {column!r}.")

    planned_allocations = allocations.copy()
    planned_demand = demand.copy()
    planned_skills = skill_intelligence.copy()
    selections: dict[str, dict] = {}
    ground_truth: list[dict[str, str]] = []

    # 1. One full-week over-allocation, with no existing allocation in the week.
    over = EXPECTED_ANOMALIES["over_allocation"]
    av_over = _one_row(availability, "availability_id", over["availability_id"], "availability record")
    _require(av_over["employee_id"] == over["employee_id"], "Over-allocation employee does not match the approved candidate.")
    _require(_iso_date(av_over["availability_date"], "over-allocation availability date").isoformat() == over["allocation_start"], "Over-allocation week start changed.")
    _require(_number(av_over["available_hours"], "over-allocation available hours") == over["available_hours"], "Over-allocation availability changed.")
    over_start = _iso_date(over["allocation_start"], "over-allocation start")
    over_end = _iso_date(over["allocation_end"], "over-allocation end")
    _require(over_end - over_start == timedelta(days=6), "Over-allocation candidate must cover exactly one full week.")
    _require(HORIZON_START <= over_start and over_end <= HORIZON_END, "Over-allocation week is outside the approved horizon.")
    active_allocations = allocations[allocations["allocation_status"] == "active"].copy()
    active_allocations["_start"] = pd.to_datetime(active_allocations["allocation_start"], errors="coerce")
    active_allocations["_end"] = pd.to_datetime(active_allocations["allocation_end"], errors="coerce")
    week_rows = active_allocations[
        (active_allocations["employee_id"] == over["employee_id"])
        & (active_allocations["_start"] <= pd.Timestamp(over_end))
        & (active_allocations["_end"] >= pd.Timestamp(over_start))
    ]
    _require(week_rows.empty, "Approved over-allocation employee-week already has an active allocation.")
    capacity_over = _one_row(capacity, "availability_id", over["availability_id"], "clean over-allocation capacity")
    _require(capacity_over["employee_id"] == over["employee_id"], "Clean capacity employee does not match the over-allocation candidate.")
    _require(_number(capacity_over["available_hours"], "clean available hours") == over["available_hours"], "Clean capacity availability changed.")
    _require(_number(capacity_over["allocated_hours"], "clean allocated hours") == 0.0, "Clean capacity already has allocations for the over-allocation week.")
    over_project = _one_row(projects, "project_id", over["project_id"], "over-allocation project")
    _require(over_project["project_status"].casefold() == "active", "Over-allocation project is no longer active.")
    _require(
        _iso_date(over_project["start_date"], "project start") <= over_start
        and _iso_date(over_project["end_date"], "project end") >= over_end,
        "Over-allocation project no longer covers the approved week.",
    )
    employee = _one_row(employees, "employee_id", over["employee_id"], "over-allocation employee")
    role = _one_row(roles, "role_id", employee["role_id"], "over-allocation employee role")
    _require(role["department"] == over_project["department"], "Over-allocation candidate is no longer department-aligned.")
    next_allocation_id = _next_numeric_id(
        allocations["allocation_id"], r"ALLOC-2026-(\d+)", "ALLOC-2026-", 6, "allocation ID"
    )
    _require(next_allocation_id == over["allocation_id"], f"Expected next allocation ID {over['allocation_id']}; found {next_allocation_id}.")
    over_row = {column: "" for column in allocations.columns}
    over_row.update({
        "allocation_id": over["allocation_id"],
        "employee_id": over["employee_id"],
        "project_id": over["project_id"],
        "allocation_start": over["allocation_start"],
        "allocation_end": over["allocation_end"],
        "allocated_hours": "41",
        "allocation_status": "active",
    })
    _require(not allocations["allocation_id"].eq(over_row["allocation_id"]).any(), "Over-allocation ID already exists.")
    planned_allocations = pd.concat([planned_allocations, pd.DataFrame([over_row])], ignore_index=True)
    selections["over_allocation"] = over_row
    ground_truth.append({
        "anomaly_id": over["anomaly_id"],
        "anomaly_type": over["anomaly_type"],
        "affected_entity_id": over["employee_id"],
        "affected_record_key": over["allocation_id"],
        "source_dataset": "raw/allocations.csv",
        "original_value": _json({
            "allocation_record": "ABSENT",
            "availability_id": av_over["availability_id"],
            "available_hours": 40.0,
            "allocated_hours_before": 0.0,
        }),
        "injected_value": _json(over_row),
        "expected_detection": over["expected_detection"],
        "severity": over["severity"],
        "injection_seed": str(seed),
        "canonical_key": f"availability:{over['availability_id']}",
    })

    # 2. One project pair, exactly one overlapping allocation, still within capacity.
    overlap = EXPECTED_ANOMALIES["overlapping_projects"]
    existing_overlap = _one_row(allocations, "allocation_id", overlap["existing_allocation_id"], "existing overlap allocation")
    _require(existing_overlap["employee_id"] == overlap["employee_id"], "Overlap employee differs from the approved candidate.")
    _require(existing_overlap["project_id"] == overlap["existing_project_id"], "Existing overlap project differs from the approved candidate.")
    overlap_day = _iso_date(overlap["allocation_start"], "overlap start")
    _require(HORIZON_START <= overlap_day <= HORIZON_END, "Overlap date is outside the approved horizon.")
    existing_start = _iso_date(existing_overlap["allocation_start"], "existing allocation start")
    existing_end = _iso_date(existing_overlap["allocation_end"], "existing allocation end")
    _require(existing_start <= overlap_day <= existing_end, "Existing allocation no longer covers the approved overlap date.")
    _require(_iso_date(overlap["allocation_end"], "overlap end") == overlap_day, "Approved overlap must remain one day.")
    av_overlap = _one_row(availability, "availability_id", overlap["availability_id"], "overlap availability record")
    _require(av_overlap["employee_id"] == overlap["employee_id"], "Overlap availability employee changed.")
    week_start = _iso_date(av_overlap["availability_date"], "overlap availability date")
    week_end = week_start + timedelta(days=6)
    _require(week_start <= overlap_day <= week_end, "Overlap date is outside the selected availability week.")
    _require(_number(av_overlap["available_hours"], "overlap available hours") == overlap["available_hours"], "Overlap availability changed.")
    active_week = active_allocations[
        (active_allocations["employee_id"] == overlap["employee_id"])
        & (active_allocations["_start"] <= pd.Timestamp(week_end))
        & (active_allocations["_end"] >= pd.Timestamp(week_start))
    ]
    before_week_hours = sum(_number(value, "weekly allocated hours") for value in active_week["allocated_hours"])
    _require(before_week_hours == overlap["allocated_hours_before"], "Overlap employee weekly allocation total changed.")
    capacity_overlap = _one_row(capacity, "availability_id", overlap["availability_id"], "clean overlap capacity")
    _require(capacity_overlap["employee_id"] == overlap["employee_id"], "Clean capacity employee does not match the overlap candidate.")
    _require(_number(capacity_overlap["available_hours"], "overlap capacity availability") == overlap["available_hours"], "Clean overlap capacity availability changed.")
    _require(_number(capacity_overlap["allocated_hours"], "overlap capacity allocation") == overlap["allocated_hours_before"], "Clean overlap capacity allocations changed.")
    _require(before_week_hours + overlap["allocated_hours"] <= overlap["available_hours"], "Overlap injection would cause an unintended over-allocation.")
    covering_day = active_allocations[
        (active_allocations["employee_id"] == overlap["employee_id"])
        & (active_allocations["_start"] <= pd.Timestamp(overlap_day))
        & (active_allocations["_end"] >= pd.Timestamp(overlap_day))
    ]
    _require(
        len(covering_day) == 1 and covering_day.iloc[0]["allocation_id"] == overlap["existing_allocation_id"],
        "Approved overlap date no longer has exactly the intended existing allocation.",
    )
    existing_project = _one_row(
        projects, "project_id", existing_overlap["project_id"], "existing overlap project"
    )
    _require(
        existing_project["project_id"] == overlap["existing_project_id"],
        "Existing overlap allocation references an unexpected project.",
    )
    target_project = _one_row(projects, "project_id", overlap["project_id"], "overlap target project")
    _require(target_project["project_status"].casefold() == "active", "Overlap target project is no longer active.")
    _require(
        _iso_date(target_project["start_date"], "target project start") <= overlap_day
        <= _iso_date(target_project["end_date"], "target project end"),
        "Overlap target project no longer covers the approved date.",
    )
    overlap_employee = _one_row(employees, "employee_id", overlap["employee_id"], "overlap employee")
    overlap_role = _one_row(roles, "role_id", overlap_employee["role_id"], "overlap employee role")
    _require(overlap_role["department"] == target_project["department"], "Overlap candidate is no longer department-aligned.")
    _require(
        not active_allocations[
            (active_allocations["employee_id"] == overlap["employee_id"])
            & (active_allocations["project_id"] == overlap["project_id"])
            & (active_allocations["_start"] <= pd.Timestamp(overlap_day))
            & (active_allocations["_end"] >= pd.Timestamp(overlap_day))
        ].shape[0],
        "Employee already has an allocation to the target project on the overlap date.",
    )
    overlap_id = _next_numeric_id(
        planned_allocations["allocation_id"], r"ALLOC-2026-(\d+)", "ALLOC-2026-", 6, "allocation ID"
    )
    _require(overlap_id == overlap["allocation_id"], f"Expected next allocation ID {overlap['allocation_id']}; found {overlap_id}.")
    overlap_row = {column: "" for column in allocations.columns}
    overlap_row.update({
        "allocation_id": overlap["allocation_id"],
        "employee_id": overlap["employee_id"],
        "project_id": overlap["project_id"],
        "allocation_start": overlap["allocation_start"],
        "allocation_end": overlap["allocation_end"],
        "allocated_hours": "1",
        "allocation_status": "active",
    })
    _require(not planned_allocations["allocation_id"].eq(overlap_row["allocation_id"]).any(), "Overlap allocation ID already exists.")
    planned_allocations = pd.concat([planned_allocations, pd.DataFrame([overlap_row])], ignore_index=True)
    selections["overlapping_projects"] = overlap_row
    ground_truth.append({
        "anomaly_id": overlap["anomaly_id"],
        "anomaly_type": overlap["anomaly_type"],
        "affected_entity_id": overlap["employee_id"],
        "affected_record_key": overlap["allocation_id"],
        "source_dataset": "raw/allocations.csv",
        "original_value": _json({
            "allocation_record": "ABSENT",
            "existing_allocation_id": overlap["existing_allocation_id"],
            "existing_project_id": overlap["existing_project_id"],
            "available_hours": 32.0,
            "allocated_hours_before": 30.0,
        }),
        "injected_value": _json(overlap_row),
        "expected_detection": overlap["expected_detection"],
        "severity": overlap["severity"],
        "injection_seed": str(seed),
        "canonical_key": f"allocation_pair:{overlap['existing_allocation_id']}|{overlap['allocation_id']}",
    })

    # 3. Duplicate one committed demand business key with a new primary key.
    demand_spec = EXPECTED_ANOMALIES["demand_double_count"]
    source_demand = _one_row(demand, "demand_id", demand_spec["source_demand_id"], "source demand")
    for column in ("project_id", "role_id", "skill_id", "demand_type", "required_employees"):
        _require(source_demand[column] == str(demand_spec[column]), f"Demand candidate {column} changed.")
    _one_row(projects, "project_id", source_demand["project_id"], "demand project")
    _one_row(roles, "role_id", source_demand["role_id"], "demand role")
    _one_row(skills, "skill_id", source_demand["skill_id"], "demand skill")
    _require(int(source_demand["required_employees"]) == demand_spec["required_employees"], "Demand candidate staffing level changed.")
    _require(_iso_date(source_demand["demand_week"], "demand week").isoformat() == demand_spec["demand_week"], "Demand candidate week changed.")
    _require(_number(source_demand["required_hours"], "required demand hours") == demand_spec["required_hours"], "Demand candidate hours changed.")
    demand_key = _logical_demand_key(source_demand)
    existing_key_count = sum(_logical_demand_key(row) == demand_key for _, row in demand.iterrows())
    _require(existing_key_count == 1, f"Demand business key must occur once before injection; found {existing_key_count}.")
    next_demand_id = _next_numeric_id(
        demand["demand_id"], r"DEM-(\d+)", "DEM-", 8, "demand ID"
    )
    _require(next_demand_id == demand_spec["injected_demand_id"], f"Expected next demand ID {demand_spec['injected_demand_id']}; found {next_demand_id}.")
    demand_row = _record(source_demand)
    demand_row["demand_id"] = demand_spec["injected_demand_id"]
    _require(not demand["demand_id"].eq(demand_row["demand_id"]).any(), "Injected demand ID already exists.")
    planned_demand = pd.concat([planned_demand, pd.DataFrame([demand_row])], ignore_index=True)
    selections["demand_double_count"] = demand_row
    ground_truth.append({
        "anomaly_id": demand_spec["anomaly_id"],
        "anomaly_type": demand_spec["anomaly_type"],
        "affected_entity_id": "|".join(demand_key),
        "affected_record_key": demand_spec["injected_demand_id"],
        "source_dataset": "raw/demand_plans.csv",
        "original_value": _json({"logical_key_count": 1, "required_hours_total": demand_spec["required_hours"]}),
        "injected_value": _json(demand_row),
        "expected_detection": demand_spec["expected_detection"],
        "severity": demand_spec["severity"],
        "injection_seed": str(seed),
        "canonical_key": "demand:" + "|".join(demand_key),
    })

    # 4. Corrupt only the derived classification; raw verification evidence stays intact.
    stale = EXPECTED_ANOMALIES["stale_skill_current"]
    raw_skill = _one_row(employee_skills, "employee_skill_id", stale["employee_skill_id"], "source employee skill")
    derived_skill = _one_row(skill_intelligence, "employee_skill_id", stale["employee_skill_id"], "derived skill intelligence record")
    _one_row(employees, "employee_id", stale["employee_id"], "stale-skill employee")
    _one_row(skills, "skill_id", stale["skill_id"], "stale-skill taxonomy record")
    for frame, label in ((raw_skill, "raw"), (derived_skill, "derived")):
        _require(frame["employee_id"] == stale["employee_id"], f"Stale-skill {label} employee changed.")
        _require(frame["skill_id"] == stale["skill_id"], f"Stale-skill {label} skill changed.")
        _require(int(frame["proficiency_level"]) == stale["proficiency_level"], f"Stale-skill {label} proficiency changed.")
        _require(_iso_date(frame["last_verified_date"], "skill verification date").isoformat() == stale["last_verified_date"], f"Stale-skill {label} verification date changed.")
        _require(_iso_date(frame["expiry_date"], "skill expiry date").isoformat() == stale["expiry_date"], f"Stale-skill {label} expiry date changed.")
    verified_date = _iso_date(raw_skill["last_verified_date"], "skill verification date")
    expiry_date = _iso_date(raw_skill["expiry_date"], "skill expiry date")
    days_since_verified = (reference_date - verified_date).days
    _require(days_since_verified == stale["days_since_verified"] and days_since_verified > 365, "Stale-skill verification age changed or is not stale.")
    _require(expiry_date >= reference_date, "Stale-skill candidate is expired, not stale-only.")
    _require(derived_skill["skill_status"] == stale["skill_status_before"], "Stale-skill derived status is not Stale before injection.")
    _require(derived_skill["is_qualified"].casefold() == "false", "Stale-skill qualification is not false before injection.")
    skill_mask = planned_skills["employee_skill_id"] == stale["employee_skill_id"]
    _require(int(skill_mask.sum()) == 1, "Stale-skill derived record is not unique.")
    planned_skills.loc[skill_mask, "skill_status"] = stale["skill_status_injected"]
    planned_skills.loc[skill_mask, "is_qualified"] = "True"
    stale_after = _record(planned_skills.loc[skill_mask].iloc[0])
    selections["stale_skill_current"] = stale_after
    ground_truth.append({
        "anomaly_id": stale["anomaly_id"],
        "anomaly_type": stale["anomaly_type"],
        "affected_entity_id": stale["employee_id"],
        "affected_record_key": stale["employee_skill_id"],
        "source_dataset": "processed/skill_intelligence.csv",
        "original_value": _json({
            "employee_skill_id": stale["employee_skill_id"],
            "skill_status": stale["skill_status_before"],
            "is_qualified": False,
            "last_verified_date": stale["last_verified_date"],
            "expiry_date": stale["expiry_date"],
            "days_since_verified": stale["days_since_verified"],
        }),
        "injected_value": _json({
            "employee_skill_id": stale["employee_skill_id"],
            "skill_status": stale["skill_status_injected"],
            "is_qualified": True,
            "last_verified_date": stale["last_verified_date"],
            "expiry_date": stale["expiry_date"],
            "days_since_verified": stale["days_since_verified"],
        }),
        "expected_detection": stale["expected_detection"],
        "severity": stale["severity"],
        "injection_seed": str(seed),
        "canonical_key": f"employee_skill:{stale['employee_skill_id']}",
    })

    _require(len(ground_truth) == 4, "Injection plan did not produce exactly four ground-truth labels.")
    _require(len({row["anomaly_id"] for row in ground_truth}) == 4, "Ground-truth anomaly IDs are not unique.")
    _require(len({row["canonical_key"] for row in ground_truth}) == 4, "Ground-truth canonical keys are not unique.")
    _require(not planned_allocations["allocation_id"].duplicated().any(), "Planned allocations contain duplicate primary keys.")
    _require(not planned_demand["demand_id"].duplicated().any(), "Planned demand contains duplicate primary keys.")

    changed = {
        raw_dir / "allocations.csv": planned_allocations,
        raw_dir / "demand_plans.csv": planned_demand,
        processed_dir / "skill_intelligence.csv": planned_skills,
    }
    truth = pd.DataFrame(ground_truth, columns=GROUND_TRUTH_COLUMNS)
    return changed, truth, selections


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(frame.columns), lineterminator="\n")
        writer.writeheader()
        writer.writerows(frame.to_dict("records"))
        stream.flush()
        os.fsync(stream.fileno())


def _write_ground_truth(path: Path, frame: pd.DataFrame) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=GROUND_TRUTH_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(frame.to_dict("records"))
        stream.flush()
        os.fsync(stream.fileno())


def apply_injections(
    data_root: Path,
    stage_root: Path,
    seed: int = ANOMALY_SEED,
    reference_date: date = ANOMALY_REFERENCE_DATE,
) -> tuple[Path, dict[str, dict]]:
    """Validate all candidates, then replace staged files as one rollbackable transaction."""
    stage_root = Path(stage_root).resolve()
    ground_truth_path = stage_root / "ground_truth" / "anomaly_ground_truth.csv"
    _require(not ground_truth_path.exists(), f"Ground-truth file already exists: {ground_truth_path}")

    # This is the complete precondition phase. It performs no writes.
    changed_frames, ground_truth, selections = build_injection_plan(
        Path(data_root), seed=seed, reference_date=reference_date
    )

    transaction_root = Path(tempfile.mkdtemp(prefix=".run-b-anomaly-txn-", dir=stage_root))
    prepared = transaction_root / "prepared"
    backups = transaction_root / "backups"
    prepared.mkdir()
    backups.mkdir()
    replaced: list[Path] = []
    created_ground_truth = False
    preserve_transaction = False
    try:
        for index, (target, frame) in enumerate(changed_frames.items()):
            staged_copy = prepared / f"{index}-{target.name}"
            backup_copy = backups / f"{index}-{target.name}"
            shutil.copy2(target, backup_copy)
            _write_frame(staged_copy, frame)
            _require(staged_copy.is_file() and staged_copy.stat().st_size > 0, f"Prepared replacement is empty: {target}")

        prepared_truth = prepared / "anomaly_ground_truth.csv"
        _write_ground_truth(prepared_truth, ground_truth)
        readback_truth = pd.read_csv(prepared_truth, dtype=str, keep_default_na=False)
        _require(list(readback_truth.columns) == GROUND_TRUTH_COLUMNS and len(readback_truth) == 4, "Prepared ground truth failed its read-back check.")

        # All preconditions and prepared-file checks have passed before the first replacement.
        ground_truth_path.parent.mkdir(parents=False, exist_ok=False)
        for index, target in enumerate(changed_frames):
            os.replace(prepared / f"{index}-{target.name}", target)
            replaced.append(target)
        os.replace(prepared_truth, ground_truth_path)
        created_ground_truth = True
        return ground_truth_path, selections
    except Exception as write_error:
        # Restore any staged file already replaced if a commit operation fails.
        rollback_errors: list[str] = []
        for index, target in reversed(list(enumerate(changed_frames))):
            if target in replaced:
                try:
                    backup_copy = backups / f"{index}-{target.name}"
                    restore_copy = prepared / f"rollback-{index}-{target.name}"
                    shutil.copy2(backup_copy, restore_copy)
                    os.replace(restore_copy, target)
                except Exception as rollback_error:
                    rollback_errors.append(
                        f"{target}: {type(rollback_error).__name__}: {rollback_error}"
                    )
        if created_ground_truth and ground_truth_path.exists():
            try:
                ground_truth_path.unlink()
            except Exception as rollback_error:
                rollback_errors.append(
                    f"{ground_truth_path}: {type(rollback_error).__name__}: {rollback_error}"
                )
        if ground_truth_path.parent.exists() and not any(ground_truth_path.parent.iterdir()):
            try:
                ground_truth_path.parent.rmdir()
            except Exception as rollback_error:
                rollback_errors.append(
                    f"{ground_truth_path.parent}: {type(rollback_error).__name__}: {rollback_error}"
                )
        if rollback_errors:
            preserve_transaction = True
            raise RuntimeError(
                f"Staged-file commit failed ({type(write_error).__name__}: {write_error}); "
                f"rollback also failed: {'; '.join(rollback_errors)}. "
                f"Recovery copies were preserved at {backups}."
            ) from write_error
        raise
    finally:
        if transaction_root.exists() and not preserve_transaction:
            shutil.rmtree(transaction_root, ignore_errors=True)

