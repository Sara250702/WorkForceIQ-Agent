"""Validate Run B ground truth against injected data and independent findings."""

from __future__ import annotations

from datetime import date
import hashlib
import json
import os
from pathlib import Path
import sys

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from engine.anomaly_detection import FINDING_COLUMNS, detect_anomalies
from generator.anomaly_spec import (
    ANOMALY_REFERENCE_DATE,
    ANOMALY_SEED,
    EXPECTED_ANOMALIES,
    GROUND_TRUTH_COLUMNS,
)


class AnomalyValidationError(AssertionError):
    """Raised when Run B data, labels, or findings do not match the approved plan."""


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AnomalyValidationError(message)


def _json_cell(value: str, label: str) -> dict:
    try:
        result = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise AnomalyValidationError(f"{label} is not valid JSON.") from error
    _check(isinstance(result, dict), f"{label} must encode a JSON object.")
    return result


def _read(path: Path) -> pd.DataFrame:
    _check(path.is_file(), f"Required Run B validation input is missing: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _one(frame: pd.DataFrame, column: str, value: str, label: str) -> pd.Series:
    matches = frame[frame[column].astype(str) == str(value)]
    _check(len(matches) == 1, f"Expected one {label}={value}; found {len(matches)}.")
    return matches.iloc[0]


def _date(value: str, label: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, errors="coerce")
    _check(pd.notna(parsed), f"Invalid date for {label}: {value!r}")
    return parsed


def _expected_canonical_keys() -> dict[str, str]:
    demand = EXPECTED_ANOMALIES["demand_double_count"]
    demand_key = "|".join([
        demand["project_id"], demand["role_id"], demand["skill_id"],
        demand["demand_week"], demand["demand_type"],
    ])
    overlap = EXPECTED_ANOMALIES["overlapping_projects"]
    left, right = sorted([overlap["existing_allocation_id"], overlap["allocation_id"]])
    return {
        "over_allocation": f"availability:{EXPECTED_ANOMALIES['over_allocation']['availability_id']}",
        "stale_skill_current": f"employee_skill:{EXPECTED_ANOMALIES['stale_skill_current']['employee_skill_id']}",
        "demand_double_count": f"demand:{demand_key}",
        "overlapping_projects": f"allocation_pair:{left}|{right}",
    }


def _finding_id(anomaly_type: str, canonical_key: str) -> str:
    digest = hashlib.sha256(f"{anomaly_type}|{canonical_key}".encode("utf-8")).hexdigest()[:16]
    return f"FND-{digest}"


def _finding_fingerprints(frame: pd.DataFrame) -> dict[str, str]:
    """Hash every field of each canonical finding, keyed by stable finding ID."""
    fingerprints = {}
    for row in frame.to_dict("records"):
        finding_id = str(row["finding_id"])
        canonical_row = json.dumps(
            {str(key): str(value) for key, value in row.items()},
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprints[finding_id] = hashlib.sha256(canonical_row.encode("utf-8")).hexdigest()
    return fingerprints


def _verify_ground_truth(
    data_root: Path,
    truth_path: Path,
    seed: int,
    reference_date: date,
) -> pd.DataFrame:
    _check(seed == ANOMALY_SEED, f"Unexpected anomaly seed: {seed}.")
    _check(reference_date == ANOMALY_REFERENCE_DATE, f"Unexpected reference date: {reference_date}.")
    raw_dir, processed_dir = data_root / "raw", data_root / "processed"
    truth = _read(truth_path)
    _check(list(truth.columns) == GROUND_TRUTH_COLUMNS, "Ground-truth columns do not match the approved schema.")
    _check(len(truth) == 4, f"Expected exactly four ground-truth records; found {len(truth)}.")
    _check(truth["anomaly_id"].is_unique, "Ground-truth anomaly IDs are not unique.")
    _check(truth["canonical_key"].is_unique, "Ground-truth canonical keys are not unique.")
    _check(set(truth["injection_seed"]) == {str(seed)}, "Ground-truth seed values are inconsistent.")
    _check(not truth_path.resolve().is_relative_to(raw_dir.resolve()), "Ground truth must not be stored in raw model inputs.")
    _check(not truth_path.resolve().is_relative_to(processed_dir.resolve()), "Ground truth must not be stored in processed model inputs.")

    expected_by_id = {spec["anomaly_id"]: (name, spec) for name, spec in EXPECTED_ANOMALIES.items()}
    _check(set(truth["anomaly_id"]) == set(expected_by_id), "Ground truth does not contain exactly the four approved anomaly IDs.")
    canonical = _expected_canonical_keys()
    record_by_name = {name: _one(truth, "anomaly_id", spec["anomaly_id"], name) for name, spec in EXPECTED_ANOMALIES.items()}

    allocations = _read(raw_dir / "allocations.csv")
    availability = _read(raw_dir / "availability.csv")
    demand = _read(raw_dir / "demand_plans.csv")
    raw_skills = _read(raw_dir / "employee_skills.csv")
    intelligence = _read(processed_dir / "skill_intelligence.csv")
    capacity = _read(processed_dir / "capacity_analysis.csv")

    def verify_metadata(name: str, spec: dict) -> pd.Series:
        record = record_by_name[name]
        _check(record["anomaly_type"] == spec["anomaly_type"], f"Wrong anomaly type for {name}.")
        _check(record["expected_detection"] == spec["expected_detection"], f"Wrong expected detection for {name}.")
        _check(record["severity"] == spec["severity"], f"Wrong severity for {name}.")
        _check(record["canonical_key"] == canonical[name], f"Wrong canonical key for {name}.")
        return record

    # Allocation exceeds availability.
    spec = EXPECTED_ANOMALIES["over_allocation"]
    record = verify_metadata("over_allocation", spec)
    _check(record["affected_entity_id"] == spec["employee_id"], "Over-allocation ground-truth employee mismatch.")
    _check(record["affected_record_key"] == spec["allocation_id"], "Over-allocation ground-truth allocation key mismatch.")
    _check(record["source_dataset"] == "raw/allocations.csv", "Over-allocation source dataset mismatch.")
    before = _json_cell(record["original_value"], "Over-allocation original_value")
    after = _json_cell(record["injected_value"], "Over-allocation injected_value")
    _check(before == {
        "allocation_record": "ABSENT",
        "availability_id": spec["availability_id"],
        "available_hours": 40.0,
        "allocated_hours_before": 0.0,
    }, "Over-allocation original value does not match the approved precondition.")
    allocation = _one(allocations, "allocation_id", spec["allocation_id"], "injected over-allocation")
    _check(after == {column: str(value) for column, value in allocation.to_dict().items()}, "Over-allocation injected value differs from the staged row.")
    _check(allocation["employee_id"] == spec["employee_id"] and allocation["project_id"] == spec["project_id"], "Over-allocation row entities changed.")
    _check(allocation["allocation_start"] == spec["allocation_start"] and allocation["allocation_end"] == spec["allocation_end"], "Over-allocation dates changed.")
    _check(float(allocation["allocated_hours"]) == spec["allocated_hours_injected"], "Over-allocation hours changed.")
    availability_row = _one(availability, "availability_id", spec["availability_id"], "over-allocation availability")
    capacity_row = _one(capacity, "availability_id", spec["availability_id"], "over-allocation capacity")
    _check(float(availability_row["available_hours"]) == spec["available_hours"], "Over-allocation available hours changed.")
    _check(float(capacity_row["allocated_hours"]) == 41.0 and capacity_row["utilization_status"] == "Overallocated", "Injected allocation is not reflected in capacity analysis.")

    # Stale skill classified as current.
    spec = EXPECTED_ANOMALIES["stale_skill_current"]
    record = verify_metadata("stale_skill_current", spec)
    _check(record["affected_entity_id"] == spec["employee_id"], "Stale-skill ground-truth employee mismatch.")
    _check(record["affected_record_key"] == spec["employee_skill_id"], "Stale-skill ground-truth key mismatch.")
    _check(record["source_dataset"] == "processed/skill_intelligence.csv", "Stale-skill source dataset mismatch.")
    before = _json_cell(record["original_value"], "Stale-skill original_value")
    after = _json_cell(record["injected_value"], "Stale-skill injected_value")
    expected_before = {
        "employee_skill_id": spec["employee_skill_id"],
        "skill_status": "Stale",
        "is_qualified": False,
        "last_verified_date": spec["last_verified_date"],
        "expiry_date": spec["expiry_date"],
        "days_since_verified": spec["days_since_verified"],
    }
    expected_after = {**expected_before, "skill_status": "Current", "is_qualified": True}
    _check(before == expected_before and after == expected_after, "Stale-skill ground-truth values differ from the approved change.")
    raw_skill = _one(raw_skills, "employee_skill_id", spec["employee_skill_id"], "stale source skill")
    skill = _one(intelligence, "employee_skill_id", spec["employee_skill_id"], "misclassified skill intelligence row")
    _check(raw_skill["employee_id"] == spec["employee_id"] and raw_skill["skill_id"] == spec["skill_id"], "Stale source-skill identity changed.")
    _check(raw_skill["last_verified_date"] == spec["last_verified_date"] and raw_skill["expiry_date"] == spec["expiry_date"], "Raw stale-skill evidence changed.")
    _check(skill["skill_status"] == "Current" and skill["is_qualified"].casefold() == "true", "Stale skill was not injected as Current and qualified.")
    age = (_date(reference_date.isoformat(), "reference date") - _date(raw_skill["last_verified_date"], "last verified date")).days
    _check(age == spec["days_since_verified"] and age > 365, "Selected raw skill is not stale at the fixed reference date.")
    _check(_date(raw_skill["expiry_date"], "expiry date") >= _date(reference_date.isoformat(), "reference date"), "Selected stale skill is expired rather than stale-only.")

    # Demand double count.
    spec = EXPECTED_ANOMALIES["demand_double_count"]
    record = verify_metadata("demand_double_count", spec)
    demand_key = (spec["project_id"], spec["role_id"], spec["skill_id"], spec["demand_week"], spec["demand_type"])
    _check(record["affected_entity_id"] == "|".join(demand_key), "Demand ground-truth entity key mismatch.")
    _check(record["affected_record_key"] == spec["injected_demand_id"], "Demand ground-truth row key mismatch.")
    _check(record["source_dataset"] == "raw/demand_plans.csv", "Demand source dataset mismatch.")
    before = _json_cell(record["original_value"], "Demand original_value")
    _check(before == {"logical_key_count": 1, "required_hours_total": 105.0}, "Demand original value does not match the approved precondition.")
    original = _one(demand, "demand_id", spec["source_demand_id"], "original demand")
    duplicate = _one(demand, "demand_id", spec["injected_demand_id"], "injected demand duplicate")
    business_fields = ["project_id", "role_id", "skill_id", "demand_week", "demand_type", "required_employees", "required_hours"]
    _check(all(original[column] == duplicate[column] for column in business_fields), "Demand clone does not exactly repeat the approved business fields.")
    matches = demand[
        demand["project_id"].eq(spec["project_id"])
        & demand["role_id"].eq(spec["role_id"])
        & demand["skill_id"].eq(spec["skill_id"])
        & pd.to_datetime(demand["demand_week"]).dt.strftime("%Y-%m-%d").eq(spec["demand_week"])
        & demand["demand_type"].eq(spec["demand_type"])
    ]
    _check(len(matches) == 2, f"Expected exactly two demand rows for the injected key; found {len(matches)}.")
    _check(round(pd.to_numeric(matches["required_hours"], errors="raise").sum(), 8) == 210.0, "Double-counted demand hours do not total 210.")
    after = _json_cell(record["injected_value"], "Demand injected_value")
    _check(after == {column: str(value) for column, value in duplicate.to_dict().items()}, "Demand ground-truth injected row differs from staged data.")

    # Overlapping project assignments.
    spec = EXPECTED_ANOMALIES["overlapping_projects"]
    record = verify_metadata("overlapping_projects", spec)
    _check(record["affected_entity_id"] == spec["employee_id"], "Overlap ground-truth employee mismatch.")
    _check(record["affected_record_key"] == spec["allocation_id"], "Overlap ground-truth allocation key mismatch.")
    _check(record["source_dataset"] == "raw/allocations.csv", "Overlap source dataset mismatch.")
    before = _json_cell(record["original_value"], "Overlap original_value")
    after = _json_cell(record["injected_value"], "Overlap injected_value")
    expected_before = {
        "allocation_record": "ABSENT",
        "existing_allocation_id": spec["existing_allocation_id"],
        "existing_project_id": spec["existing_project_id"],
        "available_hours": 32.0,
        "allocated_hours_before": 30.0,
    }
    _check(before == expected_before, "Overlap original value does not match the approved precondition.")
    new_allocation = _one(allocations, "allocation_id", spec["allocation_id"], "injected overlap allocation")
    old_allocation = _one(allocations, "allocation_id", spec["existing_allocation_id"], "existing overlap allocation")
    _check(after == {column: str(value) for column, value in new_allocation.to_dict().items()}, "Overlap injected value differs from the staged row.")
    _check(new_allocation["employee_id"] == old_allocation["employee_id"] == spec["employee_id"], "Overlap employee changed.")
    _check(new_allocation["project_id"] == spec["project_id"] and old_allocation["project_id"] == spec["existing_project_id"], "Overlap project IDs changed.")
    overlap_day = _date(spec["allocation_start"], "overlap date")
    _check(_date(new_allocation["allocation_start"], "new overlap start") == overlap_day == _date(new_allocation["allocation_end"], "new overlap end"), "Injected overlap dates changed.")
    _check(_date(old_allocation["allocation_start"], "existing overlap start") <= overlap_day <= _date(old_allocation["allocation_end"], "existing overlap end"), "Existing allocation no longer intersects the injected date.")
    av_overlap = _one(availability, "availability_id", spec["availability_id"], "overlap availability")
    start = _date(av_overlap["availability_date"], "overlap availability week")
    end = start + pd.Timedelta(days=6)
    weekly_allocations = allocations[
        allocations["employee_id"].eq(spec["employee_id"])
        & allocations["allocation_status"].str.casefold().eq("active")
        & (pd.to_datetime(allocations["allocation_start"]) <= end)
        & (pd.to_datetime(allocations["allocation_end"]) >= start)
    ]
    total_week_hours = pd.to_numeric(weekly_allocations["allocated_hours"], errors="raise").sum()
    _check(float(av_overlap["available_hours"]) == 32.0 and float(total_week_hours) == 31.0, "Overlap injection changed the approved weekly capacity values.")

    return truth


def validate_anomaly_run(
    data_root: Path,
    truth_path: Path,
    baseline_findings_path: Path,
    detections_path: Path,
    seed: int = ANOMALY_SEED,
    reference_date: date = ANOMALY_REFERENCE_DATE,
) -> dict[str, int]:
    """Require exactly four approved new findings and no other detection delta."""
    data_root = Path(data_root).resolve()
    truth = _verify_ground_truth(data_root, Path(truth_path).resolve(), seed, reference_date)
    baseline = _read(Path(baseline_findings_path).resolve())
    stored_detections = _read(Path(detections_path).resolve())
    _check(list(baseline.columns) == FINDING_COLUMNS, "Pre-injection finding fingerprint schema mismatch.")
    _check(list(stored_detections.columns) == FINDING_COLUMNS, "Anomaly detection output schema mismatch.")
    _check(baseline["finding_id"].is_unique, "Pre-injection finding IDs are not unique.")
    _check(stored_detections["finding_id"].is_unique, "Canonical detection output contains duplicate finding IDs.")
    _check(stored_detections["canonical_key"].is_unique, "Canonical detection output contains duplicate canonical keys.")

    # Recompute from data. The detector has no ground-truth input.
    recomputed = detect_anomalies(data_root, reference_date)
    stored = stored_detections.sort_values(["anomaly_type", "canonical_key"], kind="stable").reset_index(drop=True)
    recomputed = recomputed.sort_values(["anomaly_type", "canonical_key"], kind="stable").reset_index(drop=True)
    _check(stored.equals(recomputed), "Stored anomaly detections differ from independent recomputation.")

    baseline_ids = set(baseline["finding_id"].astype(str))
    baseline_fingerprints = _finding_fingerprints(baseline)
    final_fingerprints = _finding_fingerprints(stored_detections)
    expected_new = {}
    for name, spec in EXPECTED_ANOMALIES.items():
        canonical = truth.loc[truth["anomaly_id"] == spec["anomaly_id"], "canonical_key"].iloc[0]
        finding_id = _finding_id(spec["expected_detection"], canonical)
        _check(finding_id not in baseline_ids, f"Approved anomaly {name} was already present before injection.")
        expected_new[finding_id] = (name, spec, canonical)
    final_ids = set(stored_detections["finding_id"].astype(str))
    new_ids = final_ids - baseline_ids
    _check(new_ids == set(expected_new), f"Expected exactly four new canonical findings; found {len(new_ids)} with IDs {sorted(new_ids)}.")
    _check(baseline_ids.issubset(final_ids), "One or more pre-injection findings disappeared after injection.")
    changed_baseline = sorted(
        finding_id for finding_id, fingerprint in baseline_fingerprints.items()
        if finding_id in final_fingerprints and final_fingerprints[finding_id] != fingerprint
    )
    _check(
        not changed_baseline,
        f"Pre-injection findings changed after injection: {changed_baseline}",
    )

    for finding_id, (name, spec, canonical) in expected_new.items():
        matches = stored_detections[stored_detections["canonical_key"] == canonical]
        _check(len(matches) == 1, f"Expected exactly one canonical finding for {name}; found {len(matches)}.")
        finding = matches.iloc[0]
        _check(finding["anomaly_type"] == spec["expected_detection"], f"Detection type mismatch for {name}.")
        _check(finding["finding_id"] == finding_id, f"Canonical finding ID mismatch for {name}.")
        gt = truth[truth["anomaly_id"] == spec["anomaly_id"]].iloc[0]
        _check(finding["affected_record_key"] == gt["affected_record_key"] or gt["affected_record_key"] in json.loads(finding["source_record_keys"]), f"Finding does not identify the ground-truth source record for {name}.")

    print("PASS - Exactly four approved ground-truth records")
    print("PASS - Ground truth matches the injected source and processed values")
    print("PASS - Detector output matches independent recomputation")
    print("PASS - Exactly four new canonical findings; no unexpected detection deltas")
    print("PASS - All pre-injection finding fingerprints remain unchanged")
    return {"ground_truth_records": len(truth), "baseline_findings": len(baseline), "final_findings": len(stored_detections), "new_canonical_findings": len(new_ids)}


def main() -> None:
    root = os.environ.get("WORKFORCEIQ_DATA_ROOT")
    truth = os.environ.get("WORKFORCEIQ_GROUND_TRUTH_PATH")
    baseline = os.environ.get("WORKFORCEIQ_PRE_INJECTION_FINDINGS_PATH")
    detections = os.environ.get("WORKFORCEIQ_ANOMALY_DETECTIONS_PATH")
    if not all([root, truth, baseline, detections]):
        raise SystemExit(
            "Set WORKFORCEIQ_DATA_ROOT, WORKFORCEIQ_GROUND_TRUTH_PATH, "
            "WORKFORCEIQ_PRE_INJECTION_FINDINGS_PATH, and "
            "WORKFORCEIQ_ANOMALY_DETECTIONS_PATH explicitly."
        )
    result = validate_anomaly_run(
        Path(root), Path(truth), Path(baseline), Path(detections),
        seed=ANOMALY_SEED, reference_date=ANOMALY_REFERENCE_DATE,
    )
    print("ANOMALY_VALIDATION_METRICS=" + json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

