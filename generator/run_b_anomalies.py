"""Generate and verify one isolated, anomaly-injected Run B staging tree.

This runner imports helper functions from generate_all.py but never calls its
two-run main() or generate_run() workflow.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
import posixpath
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import uuid

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from generator.anomaly_spec import ANOMALY_REFERENCE_DATE, ANOMALY_SEED
from generator.config import HORIZON_END, HORIZON_START, SEED
from generator.generate_all import (
    GENERATOR_STEPS,
    PROCESSING_STEPS,
    RAW_TABLES,
    collect_outputs,
    resolve_fresh_stage,
    run_module,
    run_script,
    run_validator,
    sha256,
    validate_database,
    verify_backup,
)
from generator.inject_anomalies import apply_injections


RUN_A_ROOT = BASE_DIR / "data" / "staging" / "phase12_run_a_modulepath_20261111_r4"
ORIGINAL_DATABASE = BASE_DIR / "data" / "workforceiq.db"
FORBIDDEN_RUN_B_ROOT = BASE_DIR / "data" / "staging" / "phase12_run_b_modulepath_20261111_r4"
EXPECTED_TABLES = {
    "roles", "employees", "skills", "employee_skills", "projects",
    "demand_plans", "allocations", "availability", "training",
    "gap_analysis", "exceptions", "audit_logs",
}
EXPECTED_RUN_A_CSV_PATHS = frozenset({
    "raw/allocations.csv",
    "raw/availability.csv",
    "raw/demand_plans.csv",
    "raw/employee_skills.csv",
    "raw/employees.csv",
    "raw/gap_analysis.csv",
    "raw/projects.csv",
    "raw/roles.csv",
    "raw/skills.csv",
    "raw/training.csv",
    "processed/capacity_analysis.csv",
    "processed/demand_forecast.csv",
    "processed/skill_gap_analysis.csv",
    "processed/skill_intelligence.csv",
    "processed/talent_discovery.csv",
    "processed/workforce_exceptions.csv",
    "processed/workforce_recommendations.csv",
})


def hash_tree(root: Path) -> dict[str, str]:
    root = Path(root).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Required preservation root does not exist: {root}")
    return {
        path.relative_to(root).as_posix(): sha256(path).strip().lower()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def hash_run_a_csvs(run_a_root: Path = RUN_A_ROOT) -> dict[str, str]:
    data_root = run_a_root / "data"
    csvs = {}
    for dataset_dir in (data_root / "raw", data_root / "processed"):
        if not dataset_dir.is_dir():
            raise FileNotFoundError(f"Run A dataset directory is missing: {dataset_dir}")
        for path in sorted(dataset_dir.glob("*.csv")):
            csvs[path.relative_to(data_root).as_posix()] = sha256(path).strip().lower()
    actual_paths = set(csvs)
    if actual_paths != EXPECTED_RUN_A_CSV_PATHS:
        missing = sorted(EXPECTED_RUN_A_CSV_PATHS - actual_paths)
        unexpected = sorted(actual_paths - EXPECTED_RUN_A_CSV_PATHS)
        raise RuntimeError(
            "Run A raw/processed CSV inventory mismatch. "
            f"Missing={missing}; unexpected={unexpected}."
        )
    return csvs


def _normalized_manifest_paths(manifest: dict) -> list[str]:
    """Require 45 distinct manifest paths after POSIX and Windows normalization."""
    entries = manifest.get("files")
    if not isinstance(entries, list):
        raise RuntimeError("Baseline manifest files must be a list.")
    normalized_paths = []
    for entry in entries:
        raw_path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise RuntimeError("Baseline manifest contains a missing or invalid file path.")
        normalized = posixpath.normpath(raw_path.strip().replace("\\", "/"))
        normalized_paths.append(normalized.casefold())
    if manifest.get("file_count") != 45 or len(normalized_paths) != 45:
        raise RuntimeError("Expected exactly 45 baseline manifest file entries.")
    if len(set(normalized_paths)) != 45:
        raise RuntimeError("Baseline manifest contains duplicate normalized file paths.")
    return normalized_paths


def _hash_run_a_data_artifacts(run_a_root: Path) -> dict[str, str]:
    """Hash every file below Run A raw and processed data directories."""
    data_root = Path(run_a_root) / "data"
    artifacts: dict[str, str] = {}
    for dataset_name in ("raw", "processed"):
        dataset_dir = data_root / dataset_name
        if not dataset_dir.is_dir():
            raise FileNotFoundError(f"Run A dataset directory is missing: {dataset_dir}")
        files = sorted(path for path in dataset_dir.rglob("*") if path.is_file())
        if not files:
            raise FileNotFoundError(f"Run A dataset directory contains no artifacts: {dataset_dir}")
        for path in files:
            artifacts[path.relative_to(run_a_root).as_posix()] = sha256(path).strip().lower()
    csv_hashes = {
        path.removeprefix("data/"): digest
        for path, digest in artifacts.items()
        if path.lower().endswith(".csv")
    }
    if len(csv_hashes) != 17 or csv_hashes != hash_run_a_csvs(Path(run_a_root)):
        raise RuntimeError("Run A raw/processed CSV inventory differs from the expected 17 artifacts.")
    return artifacts


def capture_pre_generation_preservation(baseline_backup: Path, stage_root: Path) -> dict:
    """Verify and capture all preservation hashes before any generator is invoked."""
    baseline_backup = Path(baseline_backup).resolve()
    manifest_path = baseline_backup / "baseline-manifest.json"
    manifest_before_verification = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    _normalized_manifest_paths(manifest_before_verification)
    manifest = verify_backup(baseline_backup)
    normalized_manifest_paths = _normalized_manifest_paths(manifest)
    manifest_hash = sha256(manifest_path).strip().lower()
    verified_backup_files = [
        {
            "path": str((baseline_backup / entry["path"]).resolve()),
            "sha256": sha256(baseline_backup / entry["path"]).strip().lower(),
        }
        for entry in manifest["files"]
    ]

    run_a_root = Path(RUN_A_ROOT).resolve()
    run_a_database = run_a_root / "database" / "workforceiq.db"
    if not run_a_database.is_file():
        raise FileNotFoundError(f"Run A database is missing: {run_a_database}")
    run_a_tree_hashes = hash_tree(run_a_root)
    run_a_artifact_hashes = _hash_run_a_data_artifacts(run_a_root)
    run_a_csv_hashes = hash_run_a_csvs(run_a_root)
    run_a_database_hash = sha256(run_a_database).strip().lower()

    original_database = Path(ORIGINAL_DATABASE).resolve()
    if not original_database.is_file():
        raise FileNotFoundError(f"Original project database is missing: {original_database}")
    original_database_hash = sha256(original_database).strip().lower()

    return {
        "report_type": "run_b_pre_generation_preservation_hashes",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "verification_status": "PASS",
        "stage_root": str(Path(stage_root).resolve()),
        "baseline_backup": {
            "path": str(baseline_backup),
            "file_count": len(normalized_manifest_paths),
            "files_verified": len(normalized_manifest_paths),
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": manifest_hash,
            "verified_files_sha256": verified_backup_files,
            "verification_status": "PASS",
        },
        "run_a_inventory_limitation": (
            "All 17 expected raw/processed CSV paths are explicitly required. The project has no "
            "documented expected non-CSV data-artifact inventory; existing non-CSV files are hashed "
            "recursively, but a non-CSV file already missing before capture cannot be identified."
        ),
        "run_a": {
            "root": str(run_a_root),
            "tree_file_count": len(run_a_tree_hashes),
            "tree_sha256_by_path": run_a_tree_hashes,
            "raw_processed_artifact_count": len(run_a_artifact_hashes),
            "raw_processed_sha256_by_path": run_a_artifact_hashes,
            "raw_processed_absolute_paths_by_relative_path": {
                relative: str((run_a_root / relative).resolve())
                for relative in run_a_artifact_hashes
            },
            "raw_processed_csv_count": len(run_a_csv_hashes),
            "raw_processed_csv_sha256_by_path": run_a_csv_hashes,
            "database_path": str(run_a_database.resolve()),
            "database_sha256": run_a_database_hash,
            "verification_status": "PASS",
        },
        "original_database": {
            "path": str(original_database),
            "sha256": original_database_hash,
            "verification_status": "PASS",
        },
    }


def write_pre_generation_preservation_report(report_path: Path, report: dict) -> Path:
    """Atomically persist and read back the complete pre-generation report."""
    report_path = Path(os.path.abspath(report_path))
    if report_path.exists():
        raise FileExistsError(f"Refusing to overwrite preservation report: {report_path}")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    if not report_path.parent.is_dir():
        raise OSError(f"Preservation report directory is unavailable: {report_path.parent}")
    temporary_path = report_path.with_name(f"p-{uuid.uuid4().hex[:8]}.tmp")
    try:
        with temporary_path.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        with temporary_path.open("r", encoding="utf-8") as stream:
            prepared_report = json.load(stream)
        if prepared_report != report:
            raise RuntimeError("Prepared preservation report failed its read-back comparison.")
        os.replace(temporary_path, report_path)
        with report_path.open("r", encoding="utf-8") as stream:
            committed_report = json.load(stream)
        if committed_report != report or committed_report.get("verification_status") != "PASS":
            raise RuntimeError("Committed preservation report failed its read-back verification.")
    except Exception:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass
        try:
            # The target was confirmed absent before this write, so remove any
            # unverified commit if its post-rename read-back failed.
            report_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return report_path


def verify_preservation_after(baseline_backup: Path, snapshot: dict) -> dict:
    """Compare current protected files with the exact pre-generation snapshot."""
    baseline_backup = Path(baseline_backup).resolve()
    baseline_manifest_after = verify_backup(baseline_backup)
    _normalized_manifest_paths(baseline_manifest_after)
    baseline_manifest_hash_after = sha256(
        baseline_backup / "baseline-manifest.json"
    ).strip().lower()
    if baseline_manifest_hash_after != snapshot["baseline_backup"]["manifest_sha256"]:
        raise RuntimeError("Baseline manifest changed during the Run B workflow.")

    run_a_root = Path(snapshot["run_a"]["root"])
    run_a_tree_after = hash_tree(run_a_root)
    run_a_artifacts_after = _hash_run_a_data_artifacts(run_a_root)
    run_a_csv_after = hash_run_a_csvs(run_a_root)
    run_a_database_after = sha256(Path(snapshot["run_a"]["database_path"])).strip().lower()
    if run_a_tree_after != snapshot["run_a"]["tree_sha256_by_path"]:
        raise RuntimeError("Run A staged files changed during the Run B workflow.")
    if run_a_artifacts_after != snapshot["run_a"]["raw_processed_sha256_by_path"]:
        raise RuntimeError("Run A raw/processed data artifacts changed during the Run B workflow.")
    if run_a_csv_after != snapshot["run_a"]["raw_processed_csv_sha256_by_path"]:
        raise RuntimeError("Run A raw/processed CSV hashes changed during the Run B workflow.")
    if run_a_database_after != snapshot["run_a"]["database_sha256"]:
        raise RuntimeError("Run A database changed during the Run B workflow.")

    original_database_after = sha256(Path(snapshot["original_database"]["path"])).strip().lower()
    if original_database_after != snapshot["original_database"]["sha256"]:
        raise RuntimeError("Original project database changed during the Run B workflow.")
    return {
        "baseline_backup_files_verified": len(baseline_manifest_after["files"]),
        "baseline_manifest_sha256": baseline_manifest_hash_after,
        "baseline_backup_unchanged": True,
        "run_a_tree_file_count": len(run_a_tree_after),
        "run_a_tree_unchanged": True,
        "run_a_raw_processed_artifact_count": len(run_a_artifacts_after),
        "run_a_raw_processed_artifacts_unchanged": True,
        "run_a_csv_count": len(run_a_csv_after),
        "run_a_csvs_unchanged": True,
        "run_a_database_sha256": run_a_database_after,
        "run_a_database_unchanged": True,
        "original_database_sha256": original_database_after,
        "original_database_unchanged": True,
    }


def validate_stage_target(stage_root: Path, staging_root: Path, run_a_root: Path = RUN_A_ROOT) -> Path:
    """Reject existing or nested staging paths, including all prior Run A/B roots."""
    staging_root = Path(staging_root).resolve()
    expected_staging_root = (BASE_DIR / "data" / "staging").resolve()
    if staging_root != expected_staging_root:
        raise ValueError(f"Staging parent must be the project staging directory: {expected_staging_root}")
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_root = resolve_fresh_stage(stage_root, staging_root)
    if stage_root == FORBIDDEN_RUN_B_ROOT.resolve():
        raise FileExistsError(f"Refusing the previously allocated Run B path: {stage_root}")
    for existing in Path(staging_root).iterdir():
        if not existing.is_dir():
            continue
        existing = existing.resolve()
        if existing in stage_root.parents or stage_root in existing.parents:
            raise ValueError(f"New Run B staging path must not be nested with an existing staging run: {existing}")
    run_a_root = Path(run_a_root).resolve()
    if stage_root == run_a_root or run_a_root in stage_root.parents or stage_root in run_a_root.parents:
        raise ValueError("Run B staging path must be separate from the verified Run A directory.")
    return stage_root


def verify_resolved_database_path(database_path: Path, env: dict[str, str]) -> Path:
    """Resolve through the project's connection helper and reject fallback paths."""
    expected = Path(database_path).resolve()
    if not env.get("WORKFORCEIQ_DATABASE_PATH"):
        raise RuntimeError("WORKFORCEIQ_DATABASE_PATH must be explicitly set before database scripts.")
    configured = Path(env["WORKFORCEIQ_DATABASE_PATH"]).resolve()
    if configured != expected or configured == ORIGINAL_DATABASE.resolve():
        raise RuntimeError(f"Configured database target is unsafe: {configured}")
    result = subprocess.run(
        [sys.executable, "-c", "from database.db_connection import DB_PATH; print(DB_PATH)"],
        cwd=BASE_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=True,
    )
    resolved = Path(result.stdout.strip().splitlines()[-1]).resolve()
    if resolved != expected or resolved == ORIGINAL_DATABASE.resolve():
        raise RuntimeError(
            f"database.db_connection resolved to {resolved}, expected isolated Run B path {expected}."
        )
    if resolved.exists():
        raise FileExistsError(f"Run B database already exists; refusing reuse: {resolved}")
    return resolved


def _csv_hashes(data_root: Path) -> dict[str, str]:
    result = {}
    for dataset_dir in (data_root / "raw", data_root / "processed"):
        for path in sorted(dataset_dir.glob("*.csv")):
            result[path.relative_to(data_root).as_posix()] = sha256(path).strip().lower()
    return result


def _validator_summary(log_path: Path) -> dict[str, object]:
    output = log_path.read_text(encoding="utf-8", errors="replace")
    failures = [line.strip() for line in output.splitlines() if re.search(r"(?:^|: )FAIL(?:$|\s+-)", line)]
    passes = sum(bool(re.search(r"(?:^|: )PASS(?:$|\s+-)", line)) for line in output.splitlines())
    return {"exit_code": 0, "passed_checks": passes, "failed_checks": len(failures), "failure_details": failures}


def _verify_expected_downstream(data_root: Path) -> None:
    demand = pd.read_csv(data_root / "raw" / "demand_plans.csv", dtype=str)
    duplicate = demand[demand["demand_id"] == "DEM-00041435"]
    if len(duplicate) != 1 or duplicate.iloc[0]["required_hours"] != "105.0":
        raise RuntimeError("Injected demand row is missing or changed before processing.")

    forecast = pd.read_csv(data_root / "processed" / "demand_forecast.csv")
    gaps = pd.read_csv(data_root / "processed" / "skill_gap_analysis.csv")
    recommendations = pd.read_csv(data_root / "processed" / "workforce_recommendations.csv")
    demand_week, skill_id = "2027-01-11", "SKL-000040"
    gap_rows = gaps[
        (pd.to_datetime(gaps["demand_week"]).dt.strftime("%Y-%m-%d") == demand_week)
        & (gaps["skill_id"] == skill_id)
    ]
    if len(gap_rows) != 1 or gap_rows.iloc[0]["gap_status"] != "Shortage" or float(gap_rows.iloc[0]["gap_hours"]) <= 0:
        raise RuntimeError("Demand double-count did not propagate to a weekly skill shortage.")
    recommendation_rows = recommendations[
        (pd.to_datetime(recommendations["demand_week"]).dt.strftime("%Y-%m-%d") == demand_week)
        & (recommendations["skill_id"] == skill_id)
    ]
    if recommendation_rows.empty:
        raise RuntimeError("Demand double-count shortage did not reach workforce recommendations.")

    talent = pd.read_csv(data_root / "processed" / "talent_discovery.csv", dtype={"employee_skill_id": str})
    stale_candidate = talent[talent["employee_skill_id"] == "ES-0000004"]
    if stale_candidate.empty:
        raise RuntimeError("Misclassified stale skill did not propagate to talent discovery.")

    capacity = pd.read_csv(data_root / "processed" / "capacity_analysis.csv", dtype={"availability_id": str})
    overallocated = capacity[capacity["availability_id"] == "AVAIL-00000002"]
    if len(overallocated) != 1 or overallocated.iloc[0]["utilization_status"] != "Overallocated":
        raise RuntimeError("Injected allocation did not propagate to capacity analysis.")

    # Also ensure the demand forecast contains the affected skill/week.
    forecast_rows = forecast[
        (pd.to_datetime(forecast["demand_week"]).dt.strftime("%Y-%m-%d") == demand_week)
        & (forecast["skill_id"] == skill_id)
    ]
    if forecast_rows.empty:
        raise RuntimeError("Demand duplicate did not propagate to the demand forecast.")


def _verify_database(database_path: Path, data_root: Path) -> dict[str, object]:
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        if tables != EXPECTED_TABLES:
            raise RuntimeError(
                f"Run B schema table mismatch. Missing={sorted(EXPECTED_TABLES - tables)} "
                f"Extra={sorted(tables - EXPECTED_TABLES)}"
            )
        table_counts = {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in sorted(tables)
        }
        fk_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if fk_errors:
        raise RuntimeError(f"Run B database foreign-key violations: {fk_errors[:20]}")

    csv_counts = {
        table: len(pd.read_csv(data_root / "raw" / f"{table}.csv"))
        for table in RAW_TABLES
    }
    csv_counts["exceptions"] = len(pd.read_csv(data_root / "processed" / "workforce_exceptions.csv"))
    if table_counts["audit_logs"] != 0:
        raise RuntimeError("Run B audit_logs table should be empty for a new isolated database.")
    mismatches = {
        table: {"csv": count, "database": table_counts.get(table)}
        for table, count in csv_counts.items()
        if table_counts.get(table) != count
    }
    if mismatches:
        raise RuntimeError(f"Run B CSV/database row-count mismatches: {mismatches}")
    validate_database(database_path, data_root)
    return {"tables": table_counts, "csv_row_counts": csv_counts, "foreign_key_errors": 0}


def run_b_anomalies(baseline_backup: Path, stage_arg: Path) -> dict:
    baseline_backup = Path(baseline_backup)
    if not baseline_backup.is_absolute():
        baseline_backup = BASE_DIR / baseline_backup
    baseline_backup = baseline_backup.resolve()

    staging_root = BASE_DIR / "data" / "staging"
    stage_root = validate_stage_target(stage_arg, staging_root)
    # Claim the fresh stage before preflight so the preservation report belongs
    # to this run. A failed preflight leaves the stage in place for diagnosis.
    stage_root.mkdir(parents=False, exist_ok=False)
    reports_root = stage_root / "reports"
    reports_root.mkdir()

    preservation_snapshot = capture_pre_generation_preservation(baseline_backup, stage_root)
    preservation_report_path = reports_root / "pre_generation_preservation_hashes.json"
    write_pre_generation_preservation_report(preservation_report_path, preservation_snapshot)
    baseline_manifest_hash = preservation_snapshot["baseline_backup"]["manifest_sha256"]
    original_db_before = preservation_snapshot["original_database"]["sha256"]
    run_a_tree_before = preservation_snapshot["run_a"]["tree_sha256_by_path"]
    run_a_csv_before = preservation_snapshot["run_a"]["raw_processed_csv_sha256_by_path"]

    data_root = stage_root / "data"
    (data_root / "raw").mkdir(parents=True)
    (data_root / "processed").mkdir()
    (stage_root / "database").mkdir()
    database_path = stage_root / "database" / "workforceiq.db"

    env = os.environ.copy()
    env["WORKFORCEIQ_DATA_ROOT"] = str(data_root.resolve())
    env["WORKFORCEIQ_BASELINE_DATA_ROOT"] = str((baseline_backup / "data").resolve())
    env["WORKFORCEIQ_DATABASE_PATH"] = str(database_path.resolve())

    print(f"Run B data root: {env['WORKFORCEIQ_DATA_ROOT']}")
    print(f"Run B database path: {env['WORKFORCEIQ_DATABASE_PATH']}")
    print(f"Verified baseline manifest SHA-256: {baseline_manifest_hash}")
    print(f"Seed: {SEED}; reference date: {ANOMALY_REFERENCE_DATE.isoformat()}")

    # Clean deterministic baseline pass; its findings and CSV hashes form the comparison point.
    for name in GENERATOR_STEPS:
        run_script(BASE_DIR / "generator" / name, env)
    for name in PROCESSING_STEPS:
        run_module(f"engine.{Path(name).stem}", env)

    baseline_findings_path = stage_root / "reports" / "pre_injection_findings.csv"
    env["WORKFORCEIQ_ANOMALY_DETECTIONS_PATH"] = str(baseline_findings_path.resolve())
    run_module("engine.anomaly_detection", env)
    baseline_findings = pd.read_csv(baseline_findings_path, dtype=str, keep_default_na=False)
    pre_injection_hashes = _csv_hashes(data_root)
    if len(pre_injection_hashes) != 17:
        raise RuntimeError(f"Expected 17 clean Run B raw/processed CSVs; found {len(pre_injection_hashes)}.")
    pre_hash_path = stage_root / "reports" / "pre_injection_csv_hashes.json"
    pre_hash_path.write_text(json.dumps(pre_injection_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    truth_path, selections = apply_injections(data_root, stage_root, ANOMALY_SEED, ANOMALY_REFERENCE_DATE)
    # Recompute raw gap analysis after demand mutation.
    run_script(BASE_DIR / "generator" / "generate_gap_analysis.py", env)

    # Recompute direct dependents. Keep the injected skill-intelligence status;
    # all of its consumers run after the mutation.
    for module_name in (
        "engine.capacity_analysis",
        "engine.demand_forecasting",
        "engine.talent_discovery",
        "engine.skill_gap_analysis",
        "engine.recommendation_engine",
        "engine.exception_detection",
    ):
        run_module(module_name, env)
    _verify_expected_downstream(data_root)

    detections_path = stage_root / "reports" / "anomaly_detections.csv"
    env["WORKFORCEIQ_ANOMALY_DETECTIONS_PATH"] = str(detections_path.resolve())
    run_module("engine.anomaly_detection", env)

    # The existing validator is invoked unchanged; no assertions are disabled or skipped.
    data_validation_log = stage_root / "reports" / "validation.log"
    run_validator("validation.validate_data", env, data_validation_log)
    env["WORKFORCEIQ_GROUND_TRUTH_PATH"] = str(truth_path.resolve())
    env["WORKFORCEIQ_PRE_INJECTION_FINDINGS_PATH"] = str(baseline_findings_path.resolve())
    anomaly_validation_log = stage_root / "reports" / "anomaly_validation.log"
    run_validator("validation.validate_anomalies", env, anomaly_validation_log)
    validation_results = {
        "existing_validator": _validator_summary(data_validation_log),
        "anomaly_validator": _validator_summary(anomaly_validation_log),
    }
    metrics_line = next(
        (line.split("=", 1)[1] for line in anomaly_validation_log.read_text(encoding="utf-8").splitlines()
         if line.startswith("ANOMALY_VALIDATION_METRICS=")),
        None,
    )
    if metrics_line is None:
        raise RuntimeError("Anomaly validator did not emit its machine-readable summary.")
    validation_results["anomaly_metrics"] = json.loads(metrics_line)

    # Explicitly verify the target through db_connection before the first DB script.
    resolved_db_path = verify_resolved_database_path(database_path, env)
    final_csv_hashes_before_db = _csv_hashes(data_root)
    run_script(BASE_DIR / "database" / "seed.py", env)
    run_script(BASE_DIR / "database" / "import_data.py", env)
    run_script(BASE_DIR / "database" / "import_exceptions.py", env)
    run_script(BASE_DIR / "database" / "verify_data.py", env)
    database_results = _verify_database(resolved_db_path, data_root)

    final_csv_hashes_after_db = _csv_hashes(data_root)
    if final_csv_hashes_before_db != final_csv_hashes_after_db:
        raise RuntimeError("Run B staged CSV hashes changed during database verification.")
    preservation_after = verify_preservation_after(baseline_backup, preservation_snapshot)
    original_db_after = preservation_after["original_database_sha256"]
    run_a_tree_after = hash_tree(RUN_A_ROOT)
    baseline_manifest_after = verify_backup(baseline_backup)
    baseline_manifest_hash_after = preservation_after["baseline_manifest_sha256"]

    outputs = collect_outputs(stage_root)
    selected_records = []
    truth_frame = pd.read_csv(truth_path, dtype=str, keep_default_na=False)
    for record in truth_frame.to_dict("records"):
        record["original_value"] = json.loads(record["original_value"])
        record["injected_value"] = json.loads(record["injected_value"])
        selected_records.append(record)
    manifest = {
        "run_type": "single_run_b_anomaly_injection",
        "baseline_backup": str(baseline_backup),
        "baseline_manifest_sha256": baseline_manifest_hash,
        "pre_generation_preservation_report": str(preservation_report_path.resolve()),
        "seed": SEED,
        "reference_date": ANOMALY_REFERENCE_DATE.isoformat(),
        "demand_horizon_inclusive": [HORIZON_START.isoformat(), HORIZON_END.isoformat()],
        "stage_root": str(stage_root),
        "data_root": str(data_root.resolve()),
        "database_path": str(resolved_db_path),
        "selected_anomaly_records": selected_records,
        "pre_injection_findings": {
            "path": baseline_findings_path.relative_to(stage_root).as_posix(),
            "sha256": sha256(baseline_findings_path),
            "count": len(baseline_findings),
            "finding_ids": baseline_findings["finding_id"].astype(str).tolist(),
        },
        "pre_injection_csv_hashes": pre_injection_hashes,
        "pre_injection_csv_hash_manifest_sha256": sha256(pre_hash_path),
        "selection_keys": selections,
        "validation_results": validation_results,
        "database_results": database_results,
        "preservation_checks": {
            **preservation_after,
            "original_database_sha256_before": original_db_before,
            "original_database_sha256_after": original_db_after,
            "run_a_tree_files": len(run_a_tree_before),
            "run_a_tree_unchanged": True,
            "run_a_csv_count": len(run_a_csv_before),
            "run_a_csvs_unchanged": True,
            "baseline_backup_files_verified_after": baseline_manifest_after["file_count"],
            "baseline_backup_unchanged": True,
            "baseline_manifest_unchanged": True,
        },
        "outputs": outputs,
        "staging_only": True,
        "promotion_performed": False,
    }
    manifest_path = stage_root / "run-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print("RUN B ANOMALY DATASET VERIFIED")
    print(f"Ground-truth labels: {len(selected_records)}")
    print(f"New canonical findings: {validation_results['anomaly_metrics']['new_canonical_findings']}")
    print(f"Database path: {resolved_db_path}")
    print(f"Manifest: {manifest_path}")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-backup", required=True, help="Verified 45-file recovery point")
    parser.add_argument("--stage", required=True, help="New, nonexistent Run B directory under data/staging")
    args = parser.parse_args()
    run_b_anomalies(Path(args.baseline_backup), Path(args.stage))


if __name__ == "__main__":
    main()

