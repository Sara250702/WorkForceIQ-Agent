"""Approved, deterministic Run B anomaly scenarios."""

from generator.config import REFERENCE_DATE, SEED


ANOMALY_SEED = SEED
ANOMALY_REFERENCE_DATE = REFERENCE_DATE

EXPECTED_ANOMALIES = {
    "over_allocation": {
        "anomaly_id": "ANOM-2026-0001",
        "anomaly_type": "Allocation Exceeds Availability",
        "expected_detection": "Allocation Exceeds Availability",
        "severity": "High",
        "allocation_id": "ALLOC-2026-002717",
        "employee_id": "EMP-000001",
        "project_id": "PRJ-2026-000046",
        "availability_id": "AVAIL-00000002",
        "allocation_start": "2026-11-16",
        "allocation_end": "2026-11-22",
        "available_hours": 40.0,
        "allocated_hours_before": 0.0,
        "allocated_hours_injected": 41.0,
    },
    "stale_skill_current": {
        "anomaly_id": "ANOM-2026-0002",
        "anomaly_type": "Stale Skill Treated as Current",
        "expected_detection": "Stale Skill Treated as Current",
        "severity": "Medium",
        "employee_skill_id": "ES-0000004",
        "employee_id": "EMP-000001",
        "skill_id": "SKL-000007",
        "proficiency_level": 4,
        "last_verified_date": "2025-06-08",
        "expiry_date": "2028-08-05",
        "days_since_verified": 521,
        "skill_status_before": "Stale",
        "skill_status_injected": "Current",
        "is_qualified_before": False,
        "is_qualified_injected": True,
    },
    "demand_double_count": {
        "anomaly_id": "ANOM-2026-0003",
        "anomaly_type": "Demand Double Count",
        "expected_detection": "Demand Double Count",
        "severity": "High",
        "source_demand_id": "DEM-00000094",
        "injected_demand_id": "DEM-00041435",
        "project_id": "PRJ-2026-000002",
        "role_id": "ROLE-000005",
        "skill_id": "SKL-000040",
        "demand_week": "2027-01-11",
        "demand_type": "committed",
        "required_employees": 3,
        "required_hours": 105.0,
    },
    "overlapping_projects": {
        "anomaly_id": "ANOM-2026-0004",
        "anomaly_type": "Overlapping Projects",
        "expected_detection": "Overlapping Projects",
        "severity": "High",
        "allocation_id": "ALLOC-2026-002718",
        "existing_allocation_id": "ALLOC-2026-001701",
        "employee_id": "EMP-000004",
        "project_id": "PRJ-2026-000089",
        "existing_project_id": "PRJ-2026-000312",
        "allocation_start": "2027-03-25",
        "allocation_end": "2027-03-25",
        "allocated_hours": 1.0,
        "availability_id": "AVAIL-00000179",
        "available_hours": 32.0,
        "allocated_hours_before": 30.0,
        "allocated_hours_after": 31.0,
    },
}

GROUND_TRUTH_COLUMNS = [
    "anomaly_id",
    "anomaly_type",
    "affected_entity_id",
    "affected_record_key",
    "source_dataset",
    "original_value",
    "injected_value",
    "expected_detection",
    "severity",
    "injection_seed",
    "canonical_key",
]
