"""Independent detection of the four Run B anomaly patterns.

This detector reads only staged raw and processed workforce data. It never
loads the ground-truth labels; the separate validator compares its findings to
those labels after detection.
"""

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

from generator.config import REFERENCE_DATE, data_root


FINDING_COLUMNS = [
    "finding_id",
    "anomaly_type",
    "affected_entity_id",
    "affected_record_key",
    "source_dataset",
    "canonical_key",
    "source_record_keys",
    "evidence_json",
    "severity",
]


def _canonical_date(value) -> str:
    return pd.Timestamp(value).date().isoformat()


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _finding(
    anomaly_type: str,
    entity_id: str,
    record_key: str,
    source_dataset: str,
    canonical_key: str,
    source_keys: list[str],
    evidence: dict,
    severity: str,
) -> dict[str, str]:
    stable_id = hashlib.sha256(f"{anomaly_type}|{canonical_key}".encode("utf-8")).hexdigest()[:16]
    return {
        "finding_id": f"FND-{stable_id}",
        "anomaly_type": anomaly_type,
        "affected_entity_id": str(entity_id),
        "affected_record_key": str(record_key),
        "source_dataset": source_dataset,
        "canonical_key": canonical_key,
        "source_record_keys": _json(sorted(set(map(str, source_keys)))),
        "evidence_json": _json(evidence),
        "severity": severity,
    }


def _detect_overallocations(data_root: Path) -> list[dict[str, str]]:
    employees = pd.read_csv(data_root / "raw" / "employees.csv", dtype=str, keep_default_na=False)
    allocations = pd.read_csv(data_root / "raw" / "allocations.csv", dtype=str, keep_default_na=False)
    availability = pd.read_csv(data_root / "raw" / "availability.csv", dtype=str, keep_default_na=False)

    # Match capacity_analysis.py: only active employees and active allocations
    # count, and a dated allocation contributes its full hours to every
    # availability week whose inclusive date range it overlaps.
    active_employee_ids = set(
        employees.loc[employees["status"] == "active", "employee_id"].astype(str)
    )
    active_allocations = allocations[
        allocations["allocation_status"] == "active"
    ].copy()
    active_allocations["_start"] = pd.to_datetime(
        active_allocations["allocation_start"], errors="raise"
    )
    active_allocations["_end"] = pd.to_datetime(
        active_allocations["allocation_end"], errors="raise"
    )
    availability["_week_start"] = pd.to_datetime(availability["availability_date"], errors="raise")
    availability["_available_hours"] = pd.to_numeric(availability["available_hours"], errors="raise")
    findings = []
    availability = availability[
        availability["employee_id"].astype(str).isin(active_employee_ids)
    ].sort_values(["employee_id", "_week_start", "availability_id"], kind="stable")

    for row in availability.to_dict("records"):
        week_start = row["_week_start"]
        week_end = week_start + pd.Timedelta(days=6)
        contributors = active_allocations[
            (active_allocations["employee_id"].astype(str) == str(row["employee_id"]))
            & (active_allocations["_start"] <= week_end)
            & (active_allocations["_end"] >= week_start)
        ]
        record_keys = sorted(contributors["allocation_id"].astype(str).tolist())
        allocated_hours = float(
            pd.to_numeric(contributors["allocated_hours"], errors="raise").sum()
        )
        available_hours = float(row["_available_hours"])
        if available_hours <= 0 or allocated_hours <= available_hours:
            continue
        findings.append(_finding(
            "Allocation Exceeds Availability",
            row["employee_id"],
            row["availability_id"],
            "raw/allocations.csv",
            f"availability:{row['availability_id']}",
            record_keys,
            {
                "availability_id": row["availability_id"],
                "availability_date": _canonical_date(week_start),
                "available_hours": available_hours,
                "allocated_hours": allocated_hours,
                "allocation_ids": record_keys,
            },
            "High",
        ))
    return findings


def _detect_stale_current_skills(data_root: Path, reference_date: date) -> list[dict[str, str]]:
    raw_skills = pd.read_csv(
        data_root / "raw" / "employee_skills.csv", dtype=str, keep_default_na=False
    )
    intelligence = pd.read_csv(
        data_root / "processed" / "skill_intelligence.csv", dtype=str, keep_default_na=False
    )
    joined = raw_skills.merge(
        intelligence[["employee_skill_id", "skill_status", "is_qualified"]],
        on="employee_skill_id",
        how="inner",
        validate="one_to_one",
        suffixes=("_raw", "_processed"),
    )
    reference = pd.Timestamp(reference_date)
    joined["_verified"] = pd.to_datetime(joined["last_verified_date"], errors="coerce")
    joined["_expiry"] = pd.to_datetime(joined["expiry_date"], errors="coerce")
    joined["_age_days"] = (reference - joined["_verified"]).dt.days
    expected = []
    for row in joined.to_dict("records"):
        if pd.notna(row["_expiry"]) and row["_expiry"] < reference:
            expected.append("Expired")
        elif pd.notna(row["_age_days"]) and row["_age_days"] > 365:
            expected.append("Stale")
        else:
            expected.append("Current")
    joined["_expected_status"] = expected
    mismatches = joined[
        joined["_expected_status"].isin(["Stale", "Expired"])
        & joined["skill_status"].astype(str).str.casefold().eq("current")
    ].sort_values("employee_skill_id", kind="stable")

    findings = []
    for row in mismatches.to_dict("records"):
        skill_key = str(row["employee_skill_id"])
        findings.append(_finding(
            "Stale Skill Treated as Current",
            row["employee_id"],
            skill_key,
            "processed/skill_intelligence.csv",
            f"employee_skill:{skill_key}",
            [skill_key],
            {
                "skill_id": row["skill_id"],
                "expected_status_from_raw_dates": row["_expected_status"],
                "processed_status": row["skill_status"],
                "is_qualified": str(row["is_qualified"]).casefold() == "true",
                "last_verified_date": _canonical_date(row["_verified"]),
                "expiry_date": _canonical_date(row["_expiry"]) if pd.notna(row["_expiry"]) else "",
                "days_since_verified": int(row["_age_days"]) if pd.notna(row["_age_days"]) else None,
            },
            "Medium",
        ))
    return findings


def _detect_double_counted_demand(data_root: Path) -> list[dict[str, str]]:
    demand = pd.read_csv(data_root / "raw" / "demand_plans.csv", dtype=str, keep_default_na=False)
    key_columns = ["project_id", "role_id", "skill_id", "demand_week", "demand_type"]
    demand["demand_week"] = pd.to_datetime(demand["demand_week"], errors="raise").dt.strftime("%Y-%m-%d")
    findings = []
    grouped = demand.groupby(key_columns, dropna=False, sort=True)
    for key, group in grouped:
        if len(group) < 2:
            continue
        canonical = "|".join(map(str, key))
        demand_ids = sorted(group["demand_id"].astype(str).tolist())
        findings.append(_finding(
            "Demand Double Count",
            canonical,
            demand_ids[-1],
            "raw/demand_plans.csv",
            f"demand:{canonical}",
            demand_ids,
            {
                "logical_key": dict(zip(key_columns, map(str, key))),
                "demand_ids": demand_ids,
                "row_count": int(len(group)),
                "required_hours_total": float(pd.to_numeric(group["required_hours"], errors="raise").sum()),
            },
            "High",
        ))
    return findings


def _detect_overlapping_projects(data_root: Path) -> list[dict[str, str]]:
    allocations = pd.read_csv(data_root / "raw" / "allocations.csv", dtype=str, keep_default_na=False)
    allocations = allocations[
        allocations["allocation_status"] == "active"
    ].copy()
    allocations["_start"] = pd.to_datetime(allocations["allocation_start"], errors="raise")
    allocations["_end"] = pd.to_datetime(allocations["allocation_end"], errors="raise")
    findings = []
    for employee_id, group in allocations.groupby("employee_id", sort=True):
        group = group.sort_values(["_start", "allocation_id"], kind="stable")
        rows = list(group.to_dict("records"))
        for index, first in enumerate(rows):
            for second in rows[index + 1:]:
                if second["_start"] > first["_end"]:
                    break
                if first["project_id"] == second["project_id"]:
                    continue
                left, right = sorted([str(first["allocation_id"]), str(second["allocation_id"])])
                canonical = f"allocation_pair:{left}|{right}"
                overlap_start = max(first["_start"], second["_start"])
                overlap_end = min(first["_end"], second["_end"])
                findings.append(_finding(
                    "Overlapping Projects",
                    employee_id,
                    right,
                    "raw/allocations.csv",
                    canonical,
                    [left, right],
                    {
                        "allocation_ids": [left, right],
                        "project_ids": sorted([str(first["project_id"]), str(second["project_id"])]),
                        "overlap_start": _canonical_date(overlap_start),
                        "overlap_end": _canonical_date(overlap_end),
                    },
                    "High",
                ))
    return findings


def detect_anomalies(
    selected_data_root: Path,
    reference_date: date = REFERENCE_DATE,
) -> pd.DataFrame:
    """Return stable, canonical findings without consulting ground truth."""
    root = Path(selected_data_root).resolve()
    findings = []
    findings.extend(_detect_overallocations(root))
    findings.extend(_detect_stale_current_skills(root, reference_date))
    findings.extend(_detect_double_counted_demand(root))
    findings.extend(_detect_overlapping_projects(root))
    frame = pd.DataFrame(findings, columns=FINDING_COLUMNS)
    if not frame.empty:
        frame = frame.sort_values(["anomaly_type", "canonical_key"], kind="stable").reset_index(drop=True)
    return frame


def main() -> None:
    selected_root = os.environ.get("WORKFORCEIQ_DATA_ROOT")
    output = os.environ.get("WORKFORCEIQ_ANOMALY_DETECTIONS_PATH")
    if not selected_root or not output:
        raise SystemExit(
            "Set WORKFORCEIQ_DATA_ROOT and WORKFORCEIQ_ANOMALY_DETECTIONS_PATH explicitly."
        )
    output_path = Path(output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    findings = detect_anomalies(data_root(BASE_DIR))
    findings.to_csv(output_path, index=False)
    print(f"Canonical anomaly findings: {len(findings)}")
    print(f"Saved anomaly findings: {output_path}")


if __name__ == "__main__":
    main()

