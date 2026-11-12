"""Isolated fixture tests for Run B anomaly injection and verification."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from engine.anomaly_detection import detect_anomalies
from generator import generate_all
from generator import inject_anomalies
from generator.anomaly_spec import ANOMALY_REFERENCE_DATE, ANOMALY_SEED
from generator import run_b_anomalies
from generator.run_b_anomalies import (
    EXPECTED_RUN_A_CSV_PATHS,
    _normalized_manifest_paths,
    validate_stage_target,
    verify_resolved_database_path,
)
from validation.validate_anomalies import AnomalyValidationError, validate_anomaly_run


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False)


def _fixture_tree(root: Path, *, natural_findings: bool = True) -> tuple[Path, Path]:
    """Create the minimum coherent raw/processed inputs required by the helpers."""
    data_root = root / "data"
    raw, processed = data_root / "raw", data_root / "processed"
    raw.mkdir(parents=True)
    processed.mkdir(parents=True)
    stage_root = root

    employees = [
        {"employee_id": "EMP-000001", "employee_name": "A One", "status": "active", "employment_type": "Full-time", "role_id": "ROLE-000011"},
        {"employee_id": "EMP-000004", "employee_name": "A Four", "status": "active", "employment_type": "Full-time", "role_id": "ROLE-000009"},
        {"employee_id": "EMP-000099", "employee_name": "Natural Overlap", "status": "active", "employment_type": "Full-time", "role_id": "ROLE-000005"},
        {"employee_id": "EMP-000100", "employee_name": "Natural Overage", "status": "active", "employment_type": "Full-time", "role_id": "ROLE-000005"},
        {"employee_id": "EMP-000200", "employee_name": "ID Counter", "status": "active", "employment_type": "Full-time", "role_id": "ROLE-000005"},
    ]
    _write_csv(raw / "employees.csv", employees)
    _write_csv(raw / "roles.csv", [
        {"role_id": "ROLE-000005", "department": "Engineering"},
        {"role_id": "ROLE-000009", "department": "Human Resources"},
        {"role_id": "ROLE-000011", "department": "IT Operations"},
    ])
    _write_csv(raw / "skills.csv", [
        {"skill_id": "SKL-000007", "skill_name": "Skill Seven", "skill_category": "Data"},
        {"skill_id": "SKL-000040", "skill_name": "Skill Forty", "skill_category": "Data"},
    ])
    project_rows = [
        {"project_id": project_id, "project_status": "active", "department": "Engineering", "start_date": "2026-01-01", "end_date": "2027-12-31"}
        for project_id in ("PRJ-2026-000002", "PRJ-2026-000005", "PRJ-2026-000020", "PRJ-2026-000312")
    ]
    project_rows.extend([
        {"project_id": "PRJ-2026-000046", "project_status": "active", "department": "IT Operations", "start_date": "2026-09-05", "end_date": "2027-05-22", "approval_probability": "0.86"},
        {"project_id": "PRJ-2026-000089", "project_status": "active", "department": "Human Resources", "start_date": "2027-01-01", "end_date": "2027-06-01", "approval_probability": "0.96"},
    ])
    _write_csv(raw / "projects.csv", project_rows)

    allocations = [
        {"allocation_id": "ALLOC-2026-000001", "employee_id": "EMP-000099", "project_id": "PRJ-2026-000020", "allocation_start": "2027-04-01", "allocation_end": "2027-04-04", "allocated_hours": "2", "allocation_status": "active"},
        {"allocation_id": "ALLOC-2026-000002", "employee_id": "EMP-000099", "project_id": "PRJ-2026-000005", "allocation_start": "2027-04-03", "allocation_end": "2027-04-05", "allocated_hours": "3", "allocation_status": "active"},
        {"allocation_id": "ALLOC-2026-000003", "employee_id": "EMP-000100", "project_id": "PRJ-2026-000002", "allocation_start": "2027-04-05", "allocation_end": "2027-04-11", "allocated_hours": "12", "allocation_status": "active"},
        {"allocation_id": "ALLOC-2026-001701", "employee_id": "EMP-000004", "project_id": "PRJ-2026-000312", "allocation_start": "2027-03-22", "allocation_end": "2027-03-28", "allocated_hours": "30", "allocation_status": "active"},
        {"allocation_id": "ALLOC-2026-002716", "employee_id": "EMP-000200", "project_id": "PRJ-2026-000002", "allocation_start": "2026-08-01", "allocation_end": "2026-08-07", "allocated_hours": "1", "allocation_status": "complete"},
    ]
    _write_csv(raw / "allocations.csv", allocations)
    _write_csv(raw / "availability.csv", [
        {"availability_id": "AVAIL-00000002", "employee_id": "EMP-000001", "availability_date": "2026-11-16", "available_hours": "40"},
        {"availability_id": "AVAIL-00000179", "employee_id": "EMP-000004", "availability_date": "2027-03-22", "available_hours": "32"},
        {"availability_id": "AVAIL-00000900", "employee_id": "EMP-000100", "availability_date": "2027-04-05", "available_hours": "10"},
    ])

    demand_rows = [
        {"demand_id": "DEM-00000094", "project_id": "PRJ-2026-000002", "role_id": "ROLE-000005", "skill_id": "SKL-000040", "demand_week": "2027-01-11", "required_employees": "3", "required_hours": "105.0", "demand_type": "committed"},
        {"demand_id": "DEM-00000100", "project_id": "PRJ-2026-000005", "role_id": "ROLE-000005", "skill_id": "SKL-000040", "demand_week": "2027-01-18", "required_employees": "1", "required_hours": "35.0", "demand_type": "committed"},
        {"demand_id": "DEM-00000101", "project_id": "PRJ-2026-000005", "role_id": "ROLE-000005", "skill_id": "SKL-000040", "demand_week": "2027-01-18", "required_employees": "1", "required_hours": "35.0", "demand_type": "committed"},
        {"demand_id": "DEM-00041434", "project_id": "PRJ-2026-000002", "role_id": "ROLE-000005", "skill_id": "SKL-000007", "demand_week": "2027-01-25", "required_employees": "1", "required_hours": "35.0", "demand_type": "committed"},
    ]
    _write_csv(raw / "demand_plans.csv", demand_rows)

    employee_skills = [{
        "employee_skill_id": "ES-0000004", "employee_id": "EMP-000001", "skill_id": "SKL-000007",
        "proficiency_level": "4", "last_verified_date": "2025-06-08", "expiry_date": "2028-08-05",
    }]
    intelligence = [{
        "employee_skill_id": "ES-0000004", "employee_id": "EMP-000001", "skill_id": "SKL-000007",
        "proficiency_level": "4", "last_verified_date": "2025-06-08", "expiry_date": "2028-08-05",
        "days_since_verified": "521", "skill_status": "Stale", "is_qualified": "False",
    }]
    if natural_findings:
        employee_skills.append({
            "employee_skill_id": "ES-0000099", "employee_id": "EMP-000099", "skill_id": "SKL-000040",
            "proficiency_level": "4", "last_verified_date": "2024-01-01", "expiry_date": "2028-01-01",
        })
        intelligence.append({
            "employee_skill_id": "ES-0000099", "employee_id": "EMP-000099", "skill_id": "SKL-000040",
            "proficiency_level": "4", "last_verified_date": "2024-01-01", "expiry_date": "2028-01-01",
            "days_since_verified": "1045", "skill_status": "Current", "is_qualified": "True",
        })
    _write_csv(raw / "employee_skills.csv", employee_skills)
    _write_csv(processed / "skill_intelligence.csv", intelligence)
    _write_csv(processed / "capacity_analysis.csv", [
        {"availability_id": "AVAIL-00000002", "employee_id": "EMP-000001", "available_hours": "40", "allocated_hours": "0", "utilization_status": "Underutilized"},
        {"availability_id": "AVAIL-00000179", "employee_id": "EMP-000004", "available_hours": "32", "allocated_hours": "30", "utilization_status": "Healthy Utilization"},
        {"availability_id": "AVAIL-00000900", "employee_id": "EMP-000100", "available_hours": "10", "allocated_hours": "12", "utilization_status": "Overallocated"},
    ])
    return data_root, stage_root


def _refresh_capacity_after_injection(data_root: Path) -> None:
    capacity_path = data_root / "processed" / "capacity_analysis.csv"
    capacity = pd.read_csv(capacity_path, dtype=str, keep_default_na=False)
    updates = {"AVAIL-00000002": ("41", "Overallocated"), "AVAIL-00000179": ("31", "Healthy Utilization")}
    for availability_id, (hours, status) in updates.items():
        mask = capacity["availability_id"] == availability_id
        capacity.loc[mask, "allocated_hours"] = hours
        capacity.loc[mask, "utilization_status"] = status
    capacity.to_csv(capacity_path, index=False)


def _inject_and_detect(root: Path, *, natural_findings: bool = True):
    data_root, stage_root = _fixture_tree(root, natural_findings=natural_findings)
    baseline = detect_anomalies(data_root, ANOMALY_REFERENCE_DATE)
    baseline_path = stage_root / "reports" / "pre_injection_findings.csv"
    baseline_path.parent.mkdir(parents=True)
    baseline.to_csv(baseline_path, index=False)
    truth_path, selected = inject_anomalies.apply_injections(
        data_root, stage_root, ANOMALY_SEED, ANOMALY_REFERENCE_DATE
    )
    _refresh_capacity_after_injection(data_root)
    detections = detect_anomalies(data_root, ANOMALY_REFERENCE_DATE)
    detections_path = stage_root / "reports" / "anomaly_detections.csv"
    detections.to_csv(detections_path, index=False)
    return data_root, stage_root, truth_path, baseline_path, detections_path, baseline, detections, selected


def test_all_four_injections_detect_and_match_ground_truth(tmp_path: Path) -> None:
    data_root, stage_root, truth_path, baseline_path, detections_path, baseline, detections, _ = _inject_and_detect(tmp_path)

    assert len(pd.read_csv(truth_path)) == 4
    assert set(pd.read_csv(truth_path)["anomaly_type"]) == {
        "Allocation Exceeds Availability", "Stale Skill Treated as Current",
        "Demand Double Count", "Overlapping Projects",
    }
    # Detection works without a ground-truth file argument or environment setting.
    assert len(detect_anomalies(data_root, ANOMALY_REFERENCE_DATE)) == len(detections)
    assert len(detections) - len(baseline) == 4
    metrics = validate_anomaly_run(
        data_root, truth_path, baseline_path, detections_path,
        ANOMALY_SEED, ANOMALY_REFERENCE_DATE,
    )
    assert metrics["ground_truth_records"] == 4
    assert metrics["new_canonical_findings"] == 4


def test_identical_fixture_inputs_produce_identical_injection_and_ground_truth(tmp_path: Path) -> None:
    first_data, first_stage = _fixture_tree(tmp_path / "first", natural_findings=False)
    second_data, second_stage = _fixture_tree(tmp_path / "second", natural_findings=False)
    first_truth, _ = inject_anomalies.apply_injections(first_data, first_stage, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)
    second_truth, _ = inject_anomalies.apply_injections(second_data, second_stage, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)

    for relative in (
        "raw/allocations.csv", "raw/demand_plans.csv", "processed/skill_intelligence.csv",
    ):
        assert (first_data / relative).read_bytes() == (second_data / relative).read_bytes()
    assert first_truth.read_bytes() == second_truth.read_bytes()


def test_failed_candidate_precondition_leaves_every_csv_unchanged(tmp_path: Path) -> None:
    data_root, stage_root = _fixture_tree(tmp_path, natural_findings=False)
    demand_path = data_root / "raw" / "demand_plans.csv"
    demand = pd.read_csv(demand_path, dtype=str, keep_default_na=False)
    demand.loc[demand["demand_id"] == "DEM-00000094", "required_hours"] = "106"
    demand.to_csv(demand_path, index=False)
    before = {path: path.read_bytes() for path in data_root.rglob("*.csv")}

    with pytest.raises(inject_anomalies.AnomalyPreconditionError, match="hours changed"):
        inject_anomalies.apply_injections(data_root, stage_root, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)

    assert {path: path.read_bytes() for path in data_root.rglob("*.csv")} == before
    assert not (stage_root / "ground_truth").exists()


def test_commit_failure_successfully_rolls_back_replaced_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root, stage_root = _fixture_tree(tmp_path, natural_findings=False)
    target = data_root / "raw" / "allocations.csv"
    original = target.read_bytes()
    real_replace = inject_anomalies.os.replace
    calls = 0

    def fail_second_replace(source, destination):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("simulated commit failure")
        return real_replace(source, destination)

    monkeypatch.setattr(inject_anomalies.os, "replace", fail_second_replace)
    with pytest.raises(OSError, match="simulated commit failure"):
        inject_anomalies.apply_injections(data_root, stage_root, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)
    assert target.read_bytes() == original
    assert not (stage_root / "ground_truth").exists()
    assert not list(stage_root.glob(".run-b-anomaly-txn-*"))


def test_rollback_failure_reports_both_errors_and_preserves_recovery_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_root, stage_root = _fixture_tree(tmp_path, natural_findings=False)
    allocation_path = data_root / "raw" / "allocations.csv"
    original = allocation_path.read_bytes()
    real_replace = inject_anomalies.os.replace
    calls = 0

    def fail_commit_and_rollback(source, destination):
        nonlocal calls
        calls += 1
        if calls in (2, 3):
            raise OSError(f"simulated replace failure {calls}")
        return real_replace(source, destination)

    monkeypatch.setattr(inject_anomalies.os, "replace", fail_commit_and_rollback)
    with pytest.raises(RuntimeError, match="commit failed.*rollback also failed") as error:
        inject_anomalies.apply_injections(data_root, stage_root, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)

    assert "simulated replace failure 2" in str(error.value)
    assert "simulated replace failure 3" in str(error.value)
    transactions = list(stage_root.glob(".run-b-anomaly-txn-*"))
    assert len(transactions) == 1
    backup_files = list((transactions[0] / "backups").glob("*.csv"))
    assert len(backup_files) == 3
    assert next(path for path in backup_files if path.name.endswith("allocations.csv")).read_bytes() == original


def test_natural_findings_are_baseline_findings_not_injected_labels(tmp_path: Path) -> None:
    data_root, _, truth_path, baseline_path, detections_path, baseline, detections, _ = _inject_and_detect(tmp_path)
    truth = pd.read_csv(truth_path, dtype=str)
    injected_keys = set(truth["canonical_key"])
    natural = baseline[~baseline["canonical_key"].isin(injected_keys)]

    assert {"Demand Double Count", "Overlapping Projects", "Stale Skill Treated as Current"}.issubset(set(natural["anomaly_type"]))
    assert set(baseline["finding_id"]).issubset(set(detections["finding_id"]))
    assert len(detections) - len(baseline) == 4
    result = validate_anomaly_run(data_root, truth_path, baseline_path, detections_path, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)
    assert result["new_canonical_findings"] == 4


def test_changed_baseline_finding_content_is_rejected_with_same_finding_id(tmp_path: Path) -> None:
    data_root, _, truth_path, baseline_path, detections_path, baseline, _, _ = _inject_and_detect(tmp_path)
    allocation_path = data_root / "raw" / "allocations.csv"
    allocations = pd.read_csv(allocation_path, dtype=str, keep_default_na=False)
    allocations.loc[allocations["allocation_id"] == "ALLOC-2026-000002", "allocation_start"] = "2027-04-04"
    allocations.to_csv(allocation_path, index=False)
    changed_detections = detect_anomalies(data_root, ANOMALY_REFERENCE_DATE)
    changed_detections.to_csv(detections_path, index=False)

    old_overlap = baseline[baseline["anomaly_type"] == "Overlapping Projects"].iloc[0]
    new_overlap = changed_detections[changed_detections["finding_id"] == old_overlap["finding_id"]].iloc[0]
    assert new_overlap["finding_id"] == old_overlap["finding_id"]
    assert new_overlap["evidence_json"] != old_overlap["evidence_json"]
    with pytest.raises(AnomalyValidationError, match="Pre-injection findings changed"):
        validate_anomaly_run(data_root, truth_path, baseline_path, detections_path, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)


def test_staging_root_preflight_isolated_and_requires_fresh_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    staging_root = project_root / "data" / "staging"
    run_a = staging_root / "fixture_run_a"
    forbidden = staging_root / "fixture_run_b_old"
    monkeypatch.setattr("generator.run_b_anomalies.BASE_DIR", project_root)
    monkeypatch.setattr("generator.run_b_anomalies.RUN_A_ROOT", run_a)
    monkeypatch.setattr("generator.run_b_anomalies.FORBIDDEN_RUN_B_ROOT", forbidden)
    monkeypatch.setattr(generate_all, "BASE_DIR", project_root)

    target = staging_root / "fresh_fixture_run"
    assert validate_stage_target(target, staging_root, run_a) == target.resolve()
    assert staging_root.is_dir()
    target.mkdir()
    with pytest.raises(FileExistsError, match="Refusing to reuse"):
        validate_stage_target(target, staging_root, run_a)


def test_database_path_isolation_checks_are_mocked_and_do_not_connect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original_db = tmp_path / "real-project.db"
    expected_db = tmp_path / "staging" / "database" / "workforceiq.db"
    monkeypatch.setattr("generator.run_b_anomalies.ORIGINAL_DATABASE", original_db)
    calls = []

    def fake_subprocess_run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(stdout=str(expected_db), stderr="", returncode=0)

    monkeypatch.setattr("generator.run_b_anomalies.subprocess.run", fake_subprocess_run)
    resolved = verify_resolved_database_path(expected_db, {"WORKFORCEIQ_DATABASE_PATH": str(expected_db)})
    assert resolved == expected_db.resolve()
    assert len(calls) == 1
    assert "database.db_connection" in calls[0][0][2]
    assert not original_db.exists() and not expected_db.exists()

    with pytest.raises(RuntimeError, match="Configured database target is unsafe"):
        verify_resolved_database_path(expected_db, {"WORKFORCEIQ_DATABASE_PATH": str(original_db)})


def test_backup_integrity_verification_uses_only_temporary_fixture_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    backup_root = tmp_path / "fixture_backup"
    entries = []
    for index in range(45):
        relative = Path("source") / f"fixture_{index:02d}.txt"
        path = backup_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"fixture-{index}\n", encoding="utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        entries.append({"path": relative.as_posix(), "sha256_backup": digest, "sha256_original": digest})
    (backup_root / "baseline-manifest.json").write_text(
        json.dumps({"file_count": 45, "files": entries}), encoding="utf-8"
    )

    assert generate_all.verify_backup(backup_root)["file_count"] == 45
    (backup_root / entries[0]["path"]).write_text("tampered\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="backup copy failed verification"):
        generate_all.verify_backup(backup_root)


def _preservation_runner_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, csv_count: int = 17):
    project_root = tmp_path / "project"
    staging_root = project_root / "data" / "staging"
    run_a = staging_root / "fixture_run_a"
    raw, processed = run_a / "data" / "raw", run_a / "data" / "processed"
    raw.mkdir(parents=True)
    processed.mkdir(parents=True)
    for index, relative_path in enumerate(sorted(EXPECTED_RUN_A_CSV_PATHS)[:csv_count]):
        _write_csv(run_a / "data" / relative_path, [{"id": str(index), "value": f"fixture-{index}"}])
    run_a_db = run_a / "database" / "workforceiq.db"
    run_a_db.parent.mkdir()
    run_a_db.write_bytes(b"run-a-db-fixture")
    original_db = project_root / "data" / "workforceiq.db"
    original_db.parent.mkdir(parents=True, exist_ok=True)
    original_db.write_bytes(b"original-db-fixture")

    backup = project_root / "backups" / "baseline"
    entries = []
    for index in range(45):
        relative = Path("source") / f"fixture_{index:02d}.txt"
        target = backup / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"backup-{index}\n", encoding="utf-8")
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        entries.append({"path": relative.as_posix(), "sha256_backup": digest, "sha256_original": digest})
    (backup / "baseline-manifest.json").write_text(
        json.dumps({"file_count": 45, "files": entries}), encoding="utf-8"
    )
    monkeypatch.setattr(run_b_anomalies, "BASE_DIR", project_root)
    monkeypatch.setattr(run_b_anomalies, "RUN_A_ROOT", run_a)
    monkeypatch.setattr(run_b_anomalies, "ORIGINAL_DATABASE", original_db)
    monkeypatch.setattr(run_b_anomalies, "FORBIDDEN_RUN_B_ROOT", staging_root / "forbidden")
    monkeypatch.setattr(generate_all, "BASE_DIR", project_root)
    return project_root, backup, run_a, run_a_db, original_db, staging_root


def test_preservation_report_is_readable_before_first_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, backup, _, _, _, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    stage = staging_root / "new_run_b"
    observed = []

    def stop_at_first_generator(script: Path, env: dict[str, str]) -> None:
        report_path = stage / "reports" / "pre_generation_preservation_hashes.json"
        assert report_path.is_file()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["verification_status"] == "PASS"
        assert report["baseline_backup"]["files_verified"] == 45
        assert report["run_a"]["raw_processed_csv_count"] == 17
        assert len(report["run_a"]["raw_processed_sha256_by_path"]) == 17
        assert report["original_database"]["sha256"] == hashlib.sha256(b"original-db-fixture").hexdigest()
        assert Path(env["WORKFORCEIQ_DATA_ROOT"]) == (stage / "data").resolve()
        observed.append(script.name)
        raise RuntimeError("fixture stopped before generator execution")

    monkeypatch.setattr(run_b_anomalies, "run_script", stop_at_first_generator)
    with pytest.raises(RuntimeError, match="fixture stopped"):
        run_b_anomalies.run_b_anomalies(backup, stage)
    assert observed == [generate_all.GENERATOR_STEPS[0]]


def test_backup_hash_mismatch_stops_before_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, backup, _, _, _, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    entry = json.loads((backup / "baseline-manifest.json").read_text(encoding="utf-8"))["files"][0]
    (backup / entry["path"]).write_text("tampered", encoding="utf-8")
    calls = []
    monkeypatch.setattr(run_b_anomalies, "run_script", lambda *args: calls.append(args))

    with pytest.raises(RuntimeError, match="backup copy failed verification"):
        run_b_anomalies.run_b_anomalies(backup, staging_root / "new_run_b")
    assert calls == []
    assert not (staging_root / "new_run_b" / "reports" / "pre_generation_preservation_hashes.json").exists()


def test_45_unique_manifest_paths_pass_uniqueness_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, backup, _, _, _, _ = _preservation_runner_fixture(tmp_path, monkeypatch)
    manifest = json.loads((backup / "baseline-manifest.json").read_text(encoding="utf-8"))

    normalized = _normalized_manifest_paths(manifest)
    assert len(normalized) == 45
    assert len(set(normalized)) == 45


def test_45_manifest_entries_with_duplicate_path_are_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, backup, _, _, _, _ = _preservation_runner_fixture(tmp_path, monkeypatch)
    manifest_path = backup / "baseline-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][-1]["path"] = manifest["files"][0]["path"].replace("/", "\\")
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(RuntimeError, match="duplicate normalized file paths"):
        _normalized_manifest_paths(manifest)


def test_duplicate_manifest_paths_stop_runner_before_generator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, backup, _, _, _, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    manifest_path = backup / "baseline-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][-1]["path"] = manifest["files"][0]["path"]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    generator_calls = []
    backup_verification_calls = []
    monkeypatch.setattr(run_b_anomalies, "run_script", lambda *args: generator_calls.append(args))
    monkeypatch.setattr(run_b_anomalies, "verify_backup", lambda *args: backup_verification_calls.append(args))

    with pytest.raises(RuntimeError, match="duplicate normalized file paths"):
        run_b_anomalies.run_b_anomalies(backup, staging_root / "new_run_b")
    assert generator_calls == []
    assert backup_verification_calls == []


def test_missing_run_a_artifact_stops_before_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, backup, run_a, _, _, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    (run_a / "data" / "raw" / "allocations.csv").unlink()
    calls = []
    monkeypatch.setattr(run_b_anomalies, "run_script", lambda *args: calls.append(args))

    with pytest.raises(RuntimeError, match="inventory differs from the expected 17 artifacts"):
        run_b_anomalies.run_b_anomalies(backup, staging_root / "new_run_b")
    assert calls == []
    assert not (staging_root / "new_run_b" / "reports" / "pre_generation_preservation_hashes.json").exists()


def test_preservation_report_write_failure_stops_before_generator(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _, backup, _, _, _, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    calls = []

    def fail_report_write(*args, **kwargs):
        raise OSError("simulated report persistence failure")

    monkeypatch.setattr(run_b_anomalies, "write_pre_generation_preservation_report", fail_report_write)
    monkeypatch.setattr(run_b_anomalies, "run_script", lambda *args: calls.append(args))
    with pytest.raises(OSError, match="simulated report persistence failure"):
        run_b_anomalies.run_b_anomalies(backup, staging_root / "new_run_b")
    assert calls == []


def test_final_preservation_comparison_uses_captured_pre_generation_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, backup, run_a, run_a_db, original_db, staging_root = _preservation_runner_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(run_b_anomalies, "RUN_A_ROOT", run_a)
    monkeypatch.setattr(run_b_anomalies, "ORIGINAL_DATABASE", original_db)
    snapshot = run_b_anomalies.capture_pre_generation_preservation(backup, staging_root / "stage")
    report_path = staging_root / "stage" / "reports" / "pre_generation_preservation_hashes.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    run_b_anomalies.write_pre_generation_preservation_report(report_path, snapshot)

    assert run_b_anomalies.verify_preservation_after(backup, snapshot)["run_a_database_unchanged"] is True
    run_a_db.write_bytes(b"changed after snapshot")
    with pytest.raises(RuntimeError, match="Run A staged files changed"):
        run_b_anomalies.verify_preservation_after(backup, snapshot)
