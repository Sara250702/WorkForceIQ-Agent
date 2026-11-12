"""Generate two deterministic, isolated Phase 1/2 runs for review.

This command only writes beneath the two explicitly selected staging roots. It
never copies staged files to the project's live data directories or database.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import re

import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import HORIZON_END, HORIZON_START, REFERENCE_DATE, SEED


GENERATOR_STEPS = [
    "generate_roles.py",
    "generate_skills.py",
    "generate_employees.py",
    "generate_projects.py",
    "generate_demand.py",
    "generate_availability.py",
    "generate_allocations.py",
    "generate_employee_skills.py",
    "generate_training.py",
    "generate_gap_analysis.py",
]

PROCESSING_STEPS = [
    "capacity_analysis.py",
    "demand_forecasting.py",
    "skill_intelligence.py",
    "talent_discovery.py",
    "skill_gap_analysis.py",
    "recommendation_engine.py",
    "exception_detection.py",
]

RAW_TABLES = [
    "roles", "skills", "employees", "employee_skills", "projects",
    "demand_plans", "allocations", "availability", "training", "gap_analysis",
]


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_backup(backup_root):
    manifest_path = backup_root / "baseline-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("file_count") != len(manifest.get("files", [])):
        raise RuntimeError("Baseline manifest file count is inconsistent.")
    for entry in manifest["files"]:
        copy_path = backup_root / entry["path"]
        calculated_hash = sha256(copy_path).strip().lower() if copy_path.is_file() else ""
        expected_backup_hash = str(entry["sha256_backup"]).strip().lower()
        expected_original_hash = str(entry["sha256_original"]).strip().lower()
        if not copy_path.is_file() or calculated_hash != expected_backup_hash:
            raise RuntimeError(f"Baseline backup copy failed verification: {entry['path']}")
        if expected_backup_hash != expected_original_hash:
            raise RuntimeError(f"Baseline manifest has unequal original/backup hashes: {entry['path']}")
        if len(expected_backup_hash) != 64:
            raise RuntimeError(f"Baseline manifest contains an invalid SHA-256: {entry['path']}")
        if entry["path"].startswith("data/"):
            original_path = BASE_DIR / entry["path"]
            calculated_original_hash = sha256(original_path).strip().lower() if original_path.is_file() else ""
            if not original_path.is_file() or calculated_original_hash != expected_original_hash:
                raise RuntimeError(f"Live baseline data differs from verified recovery point: {entry['path']}")
    return manifest


def resolve_fresh_stage(path_arg, staging_root):
    stage = Path(path_arg)
    if not stage.is_absolute():
        stage = BASE_DIR / stage
    stage = stage.resolve()
    try:
        stage.relative_to(staging_root.resolve())
    except ValueError as error:
        raise ValueError(f"Staging path must be inside {staging_root}: {stage}") from error
    if stage == staging_root.resolve():
        raise ValueError("A run directory must be a child of data/staging.")
    if stage.exists():
        raise FileExistsError(f"Refusing to reuse or overwrite staging directory: {stage}")
    return stage


def run_script(script_path, env):
    print(f"\n>>> {script_path.relative_to(BASE_DIR)}")
    subprocess.run(
        [sys.executable, str(script_path)],
        cwd=BASE_DIR,
        env=env,
        check=True,
    )


def run_module(module_name, env):
    print(f"\n>>> python -m {module_name}")
    subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=BASE_DIR,
        env=env,
        check=True,
    )


def run_validator(module_name, env, log_path):
    print(f"\n>>> python -m {module_name}")
    result = subprocess.run(
        [sys.executable, "-m", module_name],
        cwd=BASE_DIR,
        env=env,
        text=True,
        capture_output=True,
    )
    output = (result.stdout or "") + (result.stderr or "")
    log_path.write_text(output, encoding="utf-8")
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, result.args, output=output)
    failures = [line for line in output.splitlines() if re.search(r"(?:^|: )FAIL(?:$|\s+-)", line)]
    if failures:
        print("Validator failures detected:")
        print("\n".join(failures))
        raise RuntimeError(f"Validator reported {len(failures)} failing check(s); see {log_path}.")
    passed = sum("PASS" in line for line in output.splitlines())
    print(f"Validator checks passing: {passed}; failures: 0. Log: {log_path}")


def association_pairs(frame, columns):
    if frame.empty:
        return set()
    return set(map(tuple, frame[columns].astype(str).itertuples(index=False, name=None)))


def make_association_report(baseline_root, staged_data_root, report_path):
    baseline_skills = pd.read_csv(baseline_root / "raw" / "skills.csv")
    staged_skills = pd.read_csv(staged_data_root / "raw" / "skills.csv")
    baseline_ids = set(baseline_skills["skill_id"].astype(str))
    baseline_ids_ordered = baseline_skills["skill_id"].astype(str).tolist()
    staged_by_id = staged_skills.set_index("skill_id")
    if not baseline_ids.issubset(set(staged_by_id.index.astype(str))):
        raise RuntimeError("One or more original skill IDs are missing from staging.")
    for row in baseline_skills.itertuples(index=False):
        staged_row = staged_by_id.loc[row.skill_id]
        if (str(staged_row["skill_name"]) != str(row.skill_name)
                or str(staged_row["skill_category"]) != str(row.skill_category)):
            raise RuntimeError(f"Original skill changed: {row.skill_id}")

    relationship_specs = {
        "employee_skills": ("employee_skills.csv", ["employee_id", "skill_id"]),
        "demand_plans": ("demand_plans.csv", ["project_id", "role_id", "skill_id"]),
        "training": ("training.csv", ["employee_id", "skill_id"]),
        "gap_analysis": ("gap_analysis.csv", ["project_id", "skill_id"]),
    }
    source_frames = {}
    for name, (filename, _) in relationship_specs.items():
        source_frames[("baseline", name)] = pd.read_csv(baseline_root / "raw" / filename)
        source_frames[("staged", name)] = pd.read_csv(staged_data_root / "raw" / filename)

    rows = []
    for skill in baseline_skills.itertuples(index=False):
        row = {
            "skill_id": skill.skill_id,
            "skill_name": skill.skill_name,
            "skill_category": skill.skill_category,
        }
        for name, (filename, key_columns) in relationship_specs.items():
            before = source_frames[("baseline", name)]
            after = source_frames[("staged", name)]
            before_skill = before[before["skill_id"].astype(str) == str(skill.skill_id)]
            after_skill = after[after["skill_id"].astype(str) == str(skill.skill_id)]
            before_pairs = association_pairs(before_skill, key_columns)
            after_pairs = association_pairs(after_skill, key_columns)
            missing_pairs = before_pairs - after_pairs
            if missing_pairs:
                raise RuntimeError(
                    f"Original {name} associations were lost for {skill.skill_id}: "
                    f"{len(missing_pairs)} pair(s)."
                )
            row[f"{name}_baseline_rows"] = len(before_skill)
            row[f"{name}_staged_rows"] = len(after_skill)
            row[f"{name}_baseline_associations"] = len(before_pairs)
            row[f"{name}_staged_associations"] = len(after_pairs)
        rows.append(row)
    report = pd.DataFrame(rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(report_path, index=False)
    return report, baseline_ids_ordered


def validate_skill_catalog(data_root):
    skills = pd.read_csv(data_root / "raw" / "skills.csv")
    if len(skills) != 300:
        raise RuntimeError(f"Expected exactly 300 skills, found {len(skills)}.")
    if skills["skill_id"].nunique() != 300 or skills["skill_name"].str.casefold().nunique() != 300:
        raise RuntimeError("Skill IDs and names must each be unique.")
    if not skills["skill_id"].astype(str).tolist() == [f"SKL-{i:06d}" for i in range(1, 301)]:
        raise RuntimeError("Skill IDs are not the expected sequential SKL-000001..SKL-000300 series.")


def validate_database(database_path, data_root):
    with sqlite3.connect(database_path) as connection:
        foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_errors:
            raise RuntimeError(f"Staged database foreign-key failures: {foreign_key_errors[:10]}")
        for table in RAW_TABLES:
            expected = len(pd.read_csv(data_root / "raw" / f"{table}.csv"))
            actual = connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if actual != expected:
                raise RuntimeError(f"Database row count mismatch for {table}: CSV {expected}, DB {actual}.")
        expected_exceptions = len(pd.read_csv(data_root / "processed" / "workforce_exceptions.csv"))
        actual_exceptions = connection.execute("SELECT COUNT(*) FROM exceptions").fetchone()[0]
        if actual_exceptions != expected_exceptions:
            raise RuntimeError("Database exception row count differs from staged CSV.")


def collect_outputs(stage_root):
    records = []
    for path in sorted(p for p in stage_root.rglob("*") if p.is_file() and p.name != "run-manifest.json"):
        relative = path.relative_to(stage_root).as_posix()
        rows = None
        if path.suffix.lower() == ".csv":
            rows = max(0, sum(1 for _ in path.open("r", encoding="utf-8-sig", newline="")) - 1)
        records.append({"path": relative, "rows": rows, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return records


def generate_run(stage_root, baseline_root, baseline_manifest):
    if not stage_root.is_dir() or any(stage_root.iterdir()):
        raise FileExistsError(f"Expected a newly created empty staging directory: {stage_root}")
    data_root = stage_root / "data"
    (data_root / "raw").mkdir(parents=True)
    (data_root / "processed").mkdir()
    (stage_root / "database").mkdir()
    (stage_root / "reports").mkdir()
    database_path = stage_root / "database" / "workforceiq.db"

    env = os.environ.copy()
    env["WORKFORCEIQ_DATA_ROOT"] = str(data_root)
    env["WORKFORCEIQ_BASELINE_DATA_ROOT"] = str(baseline_root / "data")
    env["WORKFORCEIQ_DATABASE_PATH"] = str(database_path)

    for name in GENERATOR_STEPS:
        run_script(BASE_DIR / "generator" / name, env)
    for name in PROCESSING_STEPS:
        run_module(f"engine.{Path(name).stem}", env)
    run_validator(
        "validation.validate_data",
        env,
        stage_root / "reports" / "validation.log",
    )

    report_path = stage_root / "reports" / "legacy_skill_association_comparison.csv"
    association_report, _ = make_association_report(baseline_root / "data", data_root, report_path)
    validate_skill_catalog(data_root)

    run_script(BASE_DIR / "database" / "seed.py", env)
    run_script(BASE_DIR / "database" / "import_data.py", env)
    run_script(BASE_DIR / "database" / "import_exceptions.py", env)
    run_script(BASE_DIR / "database" / "verify_data.py", env)
    validate_database(database_path, data_root)

    outputs = collect_outputs(stage_root)
    run_manifest = {
        "seed": SEED,
        "reference_date": REFERENCE_DATE.isoformat(),
        "demand_horizon_inclusive": [HORIZON_START.isoformat(), HORIZON_END.isoformat()],
        "monday_based_period_count": 53,
        "opening_period": {"start": "2026-11-11", "end": "2026-11-15", "hour_factor": "5/7, further clipped to project activity"},
        "closing_period": {"start": "2027-11-08", "end": "2027-11-10", "hour_factor": "3/7, further clipped to project activity"},
        "baseline_manifest_sha256": sha256(baseline_root / "baseline-manifest.json"),
        "staging_only": True,
        "promotion_performed": False,
        "outputs": outputs,
        "legacy_skill_association_rows": len(association_report),
    }
    (stage_root / "run-manifest.json").write_text(
        json.dumps(run_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return run_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-backup", required=True, help="Verified Phase 1/2 backup folder")
    parser.add_argument("--stage-a", required=True, help="New run directory inside data/staging")
    parser.add_argument("--stage-b", required=True, help="Different new run directory inside data/staging")
    args = parser.parse_args()

    backup_root = Path(args.baseline_backup)
    if not backup_root.is_absolute():
        backup_root = BASE_DIR / backup_root
    backup_root = backup_root.resolve()
    baseline_manifest = verify_backup(backup_root)
    if baseline_manifest["file_count"] != 45:
        raise RuntimeError("Expected the verified 45-file baseline recovery point.")

    staging_root = BASE_DIR / "data" / "staging"
    stage_a = resolve_fresh_stage(args.stage_a, staging_root)
    stage_b = resolve_fresh_stage(args.stage_b, staging_root)
    if stage_a == stage_b or stage_a in stage_b.parents or stage_b in stage_a.parents:
        raise ValueError("Reproducibility runs must use two separate sibling staging directories.")

    # Create both unique run roots before starting either run. Existing paths
    # cause a hard failure; no stage is ever reused or promoted.
    staging_root.mkdir(parents=True, exist_ok=True)
    stage_a.mkdir(parents=False, exist_ok=False)
    stage_b.mkdir(parents=False, exist_ok=False)
    try:
        run_a = generate_run(stage_a, backup_root, baseline_manifest)
        run_b = generate_run(stage_b, backup_root, baseline_manifest)
    except Exception:
        print("A staged run failed. Partial output remains isolated in its new staging directory; no promotion was attempted.")
        raise

    files_a = {item["path"]: item["sha256"] for item in run_a["outputs"]}
    files_b = {item["path"]: item["sha256"] for item in run_b["outputs"]}
    if files_a != files_b:
        differences = sorted(set(files_a) ^ set(files_b))
        differences += sorted(path for path in set(files_a) & set(files_b) if files_a[path] != files_b[path])
        raise RuntimeError(f"Two-run checksum comparison failed: {differences[:30]}")

    print("\nREPRODUCIBILITY CHECK PASSED")
    print(f"Run A: {stage_a}")
    print(f"Run B: {stage_b}")
    print(f"Identical staged artifacts: {len(files_a)}")
    print("No staged data or database was promoted.")


if __name__ == "__main__":
    main()

