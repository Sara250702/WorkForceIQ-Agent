# Public Copy Validation Summary

This summary separates validation of the original Run B source from checks performed on its sanitized public copy. No data was regenerated for these checks.

## Historical source Run B evidence

The original `anomaly_validation.log` output copied below this report's scope note records five passing checks, including detector recomputation. Those results belong to the original Run B source run. They do not establish that independent detector recomputation completed against the sanitized public copy. The manifest's `validation_results` also records source-run results; see `public_copy_validation` for public-copy scope.

## Sanitized public-copy checks

- Workforce data validation: **113 PASS lines, 0 FAIL lines** (`reports/validation.log`).
- Bounded comparison of stored anomaly artifacts: **3,931 baseline findings preserved**, **3,935 stored detections**, and **four new findings matching all four ground-truth records**.
- This bounded artifact comparison is not a successful run of the full anomaly validator.
- Independent full anomaly detector recomputation: **incomplete**. `validation.validate_anomalies` exceeded five minutes and was interrupted because of performance limitations. No pass is claimed for this check.

The stored anomaly log includes historical source-run output and a scope note identifying it as such. The manifest's `public_copy_validation` records the same distinction and bounded results.
