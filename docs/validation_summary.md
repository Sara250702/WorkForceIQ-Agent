# WorkForceIQ Run B Validation Summary

## Scope and evidence

This summary covers the sanitized public package at `data/staging/phase12_run_b_anomalies_20261112_public/`. The retained Run B logs and reports originated from the historical source package at `data/staging/phase12_run_b_anomalies_20261112_repro_01/`; historical source evidence is distinguished below from bounded checks performed on the sanitized copy. No generator or full anomaly validator was rerun for this summary.

Evidence reviewed:

- `reports/validation.log`
- `reports/anomaly_validation.log`
- `reports/anomaly_detections.csv`
- `reports/pre_injection_findings.csv`
- `ground_truth/anomaly_ground_truth.csv`
- `run-manifest.json`

The retained Run B manifest records seed `20261022`, reference date `2026-11-11`, the inclusive demand horizon `2026-11-11`–`2027-11-10`, 53 Monday-based periods, and output paths with row counts, sizes and SHA-256 hashes. Manifest output hashes describe the sanitized public files where updated; baseline hashes remain historical provenance.

## Results recorded in the logs

### Workforce data validation

The sanitized public-copy workforce validation record contains **113 lines containing `PASS` and zero lines containing `FAIL`**. The checks span raw and processed data integrity, including primary-ID duplicate checks, required values, date ordering, allowed values, foreign-key membership, gap calculations/status, capacity reconciliation, qualification and skill-status consistency, logical duplicate detection, recommendation traceability and strategy-simulation arithmetic.

### Run B anomaly validation

The historical source Run B `reports/anomaly_validation.log` records PASS for:

- Exactly four approved ground-truth records and agreement with injected values.
- Detector output matching independent recomputation.
- Exactly four new canonical findings, with no unexpected detection deltas.
- Preservation of all pre-injection finding fingerprints.

That historical log reports **4** ground-truth records, **3,931** baseline findings, **3,935** final findings and **4** new canonical findings. On the sanitized public copy, bounded checks confirmed **3,931 baseline findings preserved**, **3,935 stored detections**, and **4 new findings matching the four ground-truth records**. These checks compared stored results and preserved identifiers; they did not independently rerun the full anomaly detector on the sanitized copy. The four labelled cases are allocation exceeding availability, stale skill treated as current, demand double-count and overlapping projects.

## Coverage and limitations

The general validation script is `validation/validate_data.py`; the Run B-specific validator is `validation/validate_anomalies.py`. The first checks generated raw/processed data and derived calculations. The second validates truth-row structure and uniqueness, injected source values, independent detector output and preservation of baseline detections.

Independent full anomaly-detector recomputation on the sanitized public copy remains incomplete because of performance limitations; the interrupted recomputation is not a successful validation. The bounded checks above do not establish that every possible input defect is tested, that all schema constraints are enforced directly by CSV files, or that future dataset changes will pass. Ground truth applies only to this isolated Run B package and is intentionally stored outside the CSV input directories. This summary is not a validation of the separate default `data/` tree or a claim of production monitoring.
