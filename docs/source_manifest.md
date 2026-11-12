# WorkForceIQ Synthetic Dataset Source Manifest

## Dataset package

| Item | Verified value |
|---|---|
| Dataset | Run B staged workforce dataset with four injected anomaly cases |
| Sanitized public dataset location | `data/staging/phase12_run_b_anomalies_20261112_public/` |
| Application data root inside package | `data/` (`raw/` and `processed/` subdirectories) |
| Ground truth | `ground_truth/anomaly_ground_truth.csv`, separate from model/input data directories |
| Run manifest | `run-manifest.json` at the package root |
| Generator | `generator/generate_all.py`; anomaly runner `generator/run_b_anomalies.py` |
| Fixed seed | `20261022` |
| Reference date | `2026-11-11` |
| Demand horizon | Inclusive `2026-11-11` through `2027-11-10` |
| Demand periods | 53 Monday-based weekly buckets, with clipped opening and closing periods |

The run manifest records the seed, reference date, demand horizon, period count, baseline-manifest hash, output paths, row counts, byte sizes and SHA-256 hashes. The manifest marks the workflow as staging-only and indicates no promotion was performed.

The public package is the sanitized copy of the historical Run B output, originally produced under `data/staging/phase12_run_b_anomalies_20261112_repro_01/`. Historical Run B provenance and source validation evidence are retained separately from checks performed on the sanitized public copy. SQLite database files are excluded from the public submission; the generator's ability to create a staged database does not mean one is included.

## Provenance and generation

`generator/config.py` defines the fixed seed and date horizon. The employee and project generators use seeded Faker data and deterministic sequence-based IDs; other generator steps use the same configured seed and local generated inputs. `generator/generate_all.py` creates a staged package, derives processed workforce datasets, runs validation, creates/verifies a staged SQLite database and records checksums. `generator/run_b_anomalies.py` and `generator/inject_anomalies.py` apply the separate Run B anomaly scenario set and emit the ground-truth labels.

The documented workflow retains verified baseline records for original skill associations, employee skills, training and demand relationships while extending the skill catalog and demand horizon. Therefore the package is synthetic/generated but also inherits selected records from a local baseline backup; it is not wholly generated from scratch in the Run B workflow.

## External dataset statement

The inspected generator code reads local CSVs and uses Faker; no HTTP/download or remote dataset ingestion path was found in the generator workflow. However, the original provenance of the local baseline backup is not established by the inspected generator code, Run B manifest or generation guide. **It cannot be verified from these artifacts whether that inherited baseline originally used any external dataset.** This manifest therefore does not claim that no external data was ever used.

## Run B anomaly labels

Ground truth is stored at `ground_truth/anomaly_ground_truth.csv`, outside `data/raw/` and `data/processed/`. It contains four rows with `anomaly_id`, `anomaly_type`, affected record identifiers, source dataset, original/injected values, expected detection, severity, injection seed and canonical key. The four labels are:

- `Allocation Exceeds Availability`
- `Stale Skill Treated as Current`
- `Demand Double Count`
- `Overlapping Projects`

Employee names, email addresses and other personal employee values are intentionally omitted from this manifest.

## Evidence files

- `docs/phase1_phase2_generation.md` — documented generation settings, commands, staging workflow and anomaly definitions.
- `generator/config.py` — seed, reference date, horizon and configured data-root selection.
- `generator/generate_all.py` — staging, validation, database checks and run-manifest generation.
- `generator/anomaly_spec.py` and `generator/inject_anomalies.py` — approved anomaly definitions and separate truth-row construction.
- Run B `run-manifest.json` and `ground_truth/anomaly_ground_truth.csv` — generated run metadata and labels.
