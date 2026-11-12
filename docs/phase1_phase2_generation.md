# Reproducible Phase 1/2 data generation

## Fixed configuration

- Seed: `20261022`.
- Reference date: `2026-11-11`.
- Demand horizon: inclusive `2026-11-11` through `2027-11-10` (12 calendar months).
- Demand periods: 53 Monday-based weekly buckets. The opening bucket is clipped to
  Nov 11–15, 2026 (5 days); the closing bucket is clipped to Nov 8–10, 2027
  (3 days); the other 51 buckets cover seven days each.
- Demand required hours are prorated by the active calendar days in an edge
  bucket divided by seven. Project activity further clips the edge period. Thus a
  fully active opening week gets `5/7` of its normal weekly hours and a fully
  active closing week gets `3/7`. Required employee counts remain the staffing
  level for those active days. The ordinary full-week demand-hour calculation is
  otherwise unchanged.

## Skill taxonomy

The original 84 skill IDs, names, and category assignments remain first and
unchanged. IDs `SKL-000085` through `SKL-000300` add 216 unique skills. Final
category counts are:

| Category | Skills |
|---|---:|
| Programming | 30 |
| AI and Machine Learning | 30 |
| Data Analytics | 22 |
| Database | 18 |
| Cloud and DevOps | 24 |
| Web Development | 24 |
| Project Management | 16 |
| Design | 12 |
| Cybersecurity | 20 |
| Data Engineering | 20 |
| Business and Finance | 16 |
| Enterprise Platforms | 16 |
| HR and Workforce | 14 |
| Operations and Supply Chain | 14 |
| Quality Assurance and Testing | 12 |
| Product Management | 12 |
| **Total** | **300** |

New employee-skill, demand, and training relationships use the category-to-
department applicability map in `generator/skill_role_mapping.py`. Original
employee-skill and training records are retained from the verified baseline;
existing demand relationships are retained and the closing period is added.
`legacy_skill_association_comparison.csv` reports baseline and staged counts per
original skill, and the orchestrator fails if an original association is lost.

## Run order and staging safety

The orchestrator runs roles, skills, employees, projects, demand, availability,
allocations, employee skills, training, and raw gap analysis; then capacity,
forecast, skill intelligence, talent discovery, weekly skill gaps,
recommendations, and exceptions. It validates the staged CSVs, creates and
checks a separate staged SQLite database, and records row counts and SHA-256
checksums.

Example (both run directories must be new and distinct):

```powershell
python generator/generate_all.py `
  --baseline-backup backups/phase12_preimplementation_20261111_202316_014 `
  --stage-a data/staging/phase12_run_a `
  --stage-b data/staging/phase12_run_b
```

All outputs remain in the two selected staging directories. The orchestrator
refuses to reuse an existing run directory and has no promotion or overwrite
step. Existing dashboard paths and the existing database remain the defaults.

## Isolated Run B anomaly dataset

The two-run command above is a reproducibility workflow. It does not inject
anomalies. To create the separate hackathon anomaly dataset, use the Run B-only
runner with a **new, nonexistent** staging directory. Do not use Run A, the
previous empty `phase12_run_b_modulepath_20261111_r4` directory, or another
existing staging directory.

```powershell
python -m generator.run_b_anomalies `
  --baseline-backup backups/phase12_preimplementation_20261111_202316_014 `
  --stage data/staging/phase12_run_b_anomalies_<unique-suffix>
```

The runner verifies the 45-file baseline manifest, uses seed `20261022` and
reference date `2026-11-11`, and writes only beneath the selected Run B root.
It never invokes the two-run orchestrator and never copies Run A. It records
clean pre-injection finding fingerprints and raw/processed CSV hashes, validates
all four approved candidates before an atomic staged-file replacement, and
stores labels at `ground_truth/anomaly_ground_truth.csv`, outside the normal
`data/raw` and `data/processed` inputs. The anomaly detector reads workforce
data only; the separate anomaly validator compares its findings with ground
truth.

The four deterministic cases are an over-allocation for `EMP-000001`, a stale
`ES-0000004` skill classified as current, a repeated committed demand key for
`PRJ-2026-000002` / `ROLE-000005` / `SKL-000040` in week `2027-01-11`, and a
one-day overlapping assignment for `EMP-000004`. Candidate IDs, source values,
dates, and capacity preconditions are enforced in code; the runner aborts before
injection if regenerated staged inputs do not match those preconditions.

The Run B-only runner runs the existing data validator without changing its
assertions, then checks the four labels against independent canonical findings.
It verifies a separate Run B database path before database scripts run, checks
all 12 schema tables, CSV row counts and foreign keys, and compares Run A plus
the original database hashes before and after. A second full anomaly run is not
started automatically; use a new staging path for any approved replay.

The anomaly detector derives over-allocation directly from raw availability,
employee status, and active allocation rows. It follows the capacity engine's
inclusive week-overlap rule and counts an allocation's full hours in every
availability week it overlaps; it does not trust `capacity_analysis.csv` to
decide whether an employee is over capacity. Both overlap detection and injection
preconditions consider active allocations only. The injector also verifies that
the existing overlap allocation's project is present in the project catalog.

The injector prepares all replacement files before the first staged-file
replacement. If a commit fails, it attempts to restore every replaced file. If
restoration itself fails, it reports both errors and preserves the transaction
directory and its recovery copies. The anomaly validator compares complete,
canonicalized finding-row fingerprints as well as finding IDs, so a baseline
finding cannot silently change its evidence while retaining its ID. After the
workflow, the runner verifies all 45 baseline backup file hashes again. If
`data/staging` does not exist, preflight creates only that parent directory;
the selected run directory must still be new and is never reused.
