import pandas as pd
from pathlib import Path
import sys
import os

# Locate the raw data folder
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, data_root

DATA_DIR = data_root(BASE_DIR)
RAW_DIR = DATA_DIR / "raw"

# Load datasets
employees = pd.read_csv(RAW_DIR / "employees.csv")
skills = pd.read_csv(RAW_DIR / "skills.csv")
projects = pd.read_csv(RAW_DIR / "projects.csv")
demand = pd.read_csv(RAW_DIR / "demand_plans.csv")
allocations = pd.read_csv(RAW_DIR / "allocations.csv")
availability = pd.read_csv(RAW_DIR / "availability.csv")
training = pd.read_csv(RAW_DIR / "training.csv")

print("=" * 50)
print("WORKFORCEIQ DATA VALIDATION")
print("=" * 50)

# 1. Check duplicate primary IDs
datasets = {
    "Employees": (employees, "employee_id"),
    "Skills": (skills, "skill_id"),
    "Projects": (projects, "project_id"),
    "Demand Plans": (demand, "demand_id"),
    "Allocations": (allocations, "allocation_id"),
    "Availability": (availability, "availability_id"),
    "Training": (training, "training_id")
}

print("\n1. PRIMARY KEY VALIDATION")

for name, (df, column) in datasets.items():
    duplicates = df[column].duplicated().sum()

    if duplicates == 0:
        print(f"{name}: PASS - No duplicate IDs")
    else:
        print(f"{name}: FAIL - {duplicates} duplicate IDs")

# 2. Check missing values
print("\n2. MISSING VALUE VALIDATION")

for name, (df, column) in datasets.items():
    missing = df.isnull().sum().sum()

    if missing == 0:
        print(f"{name}: PASS - No missing values")
    else:
        print(f"{name}: FAIL - {missing} missing values")

# 3. Check availability calculations
print("\n3. AVAILABILITY VALIDATION")

availability["calculated_hours"] = (
    availability["standard_hours"] -
    availability["leave_hours"]
)

invalid_availability = (
    availability["available_hours"] !=
    availability["calculated_hours"]
).sum()

if invalid_availability == 0:
    print("PASS - Available hours are calculated correctly")
else:
    print(f"FAIL - {invalid_availability} incorrect records")

# 4. Check date ranges
print("\n4. DATE VALIDATION")

projects["start_date"] = pd.to_datetime(projects["start_date"])
projects["end_date"] = pd.to_datetime(projects["end_date"])

invalid_projects = (
    projects["end_date"] < projects["start_date"]
).sum()

if invalid_projects == 0:
    print("PASS - All project date ranges are valid")
else:
    print(f"FAIL - {invalid_projects} invalid project dates")

allocations["allocation_start"] = pd.to_datetime(
    allocations["allocation_start"]
)
allocations["allocation_end"] = pd.to_datetime(
    allocations["allocation_end"]
)

invalid_allocations = (
    allocations["allocation_end"] <
    allocations["allocation_start"]
).sum()

if invalid_allocations == 0:
    print("PASS - All allocation date ranges are valid")
else:
    print(f"FAIL - {invalid_allocations} invalid allocation dates")

print("\n" + "=" * 50)
print("INITIAL DATA VALIDATION COMPLETED")
print("=" * 50)

# 5. BUSINESS RULE VALIDATION

print("\n5. BUSINESS RULE VALIDATION")

# Employee employment types
valid_employment_types = [
    "Full-time", "Part-time", "Contract"
]

invalid_employment = (
    ~employees["employment_type"].isin(valid_employment_types)
).sum()

print(
    "Employment types:",
    "PASS" if invalid_employment == 0
    else f"FAIL - {invalid_employment} invalid records"
)

# Employee statuses
valid_employee_statuses = [
    "active", "on_leave", "inactive"
]

invalid_employee_status = (
    ~employees["status"].isin(valid_employee_statuses)
).sum()

print(
    "Employee statuses:",
    "PASS" if invalid_employee_status == 0
    else f"FAIL - {invalid_employee_status} invalid records"
)

# Skill proficiency levels
employee_skills = pd.read_csv(RAW_DIR / "employee_skills.csv")

invalid_proficiency = (
    ~employee_skills["proficiency_level"].between(1, 5)
).sum()

print(
    "Skill proficiency:",
    "PASS" if invalid_proficiency == 0
    else f"FAIL - {invalid_proficiency} invalid records"
)

# Project statuses
valid_project_statuses = [
    "planned", "active", "completed", "on_hold"
]

invalid_project_status = (
    ~projects["project_status"].isin(valid_project_statuses)
).sum()

print(
    "Project statuses:",
    "PASS" if invalid_project_status == 0
    else f"FAIL - {invalid_project_status} invalid records"
)

# Demand types
valid_demand_types = ["committed", "proposed"]

invalid_demand_types = (
    ~demand["demand_type"].isin(valid_demand_types)
).sum()

print(
    "Demand types:",
    "PASS" if invalid_demand_types == 0
    else f"FAIL - {invalid_demand_types} invalid records"
)

# Non-negative hours
invalid_demand_hours = (demand["required_hours"] < 0).sum()
invalid_allocation_hours = (
    allocations["allocated_hours"] < 0
).sum()

print(
    "Demand hours:",
    "PASS" if invalid_demand_hours == 0
    else f"FAIL - {invalid_demand_hours} invalid records"
)

print(
    "Allocation hours:",
    "PASS" if invalid_allocation_hours == 0
    else f"FAIL - {invalid_allocation_hours} invalid records"
)

# Training status and dates
training["training_start_date"] = pd.to_datetime(
    training["training_start_date"]
)
training["training_end_date"] = pd.to_datetime(
    training["training_end_date"]
)

valid_training_statuses = [
    "planned", "in_progress", "completed"
]

invalid_training_status = (
    ~training["training_status"].isin(valid_training_statuses)
).sum()

invalid_training_dates = (
    training["training_end_date"] <
    training["training_start_date"]
).sum()

print(
    "Training statuses:",
    "PASS" if invalid_training_status == 0
    else f"FAIL - {invalid_training_status} invalid records"
)

print(
    "Training dates:",
    "PASS" if invalid_training_dates == 0
    else f"FAIL - {invalid_training_dates} invalid records"
)

# 6. CSV RELATIONSHIP VALIDATION

print("\n6. CSV RELATIONSHIP VALIDATION")

roles = pd.read_csv(RAW_DIR / "roles.csv")
employee_skills = pd.read_csv(RAW_DIR / "employee_skills.csv")

# Employee -> Role
invalid_employee_roles = (
    ~employees["role_id"].isin(roles["role_id"])
).sum()

# Employee Skill -> Employee
invalid_skill_employees = (
    ~employee_skills["employee_id"].isin(employees["employee_id"])
).sum()

# Employee Skill -> Skill
invalid_skill_ids = (
    ~employee_skills["skill_id"].isin(skills["skill_id"])
).sum()

# Demand -> Project, Role and Skill
invalid_demand_projects = (
    ~demand["project_id"].isin(projects["project_id"])
).sum()

invalid_demand_roles = (
    ~demand["role_id"].isin(roles["role_id"])
).sum()

invalid_demand_skills = (
    ~demand["skill_id"].isin(skills["skill_id"])
).sum()

# Allocation -> Employee and Project
invalid_allocation_employees = (
    ~allocations["employee_id"].isin(employees["employee_id"])
).sum()

invalid_allocation_projects = (
    ~allocations["project_id"].isin(projects["project_id"])
).sum()

checks = {
    "Employee -> Role": invalid_employee_roles,
    "Employee Skill -> Employee": invalid_skill_employees,
    "Employee Skill -> Skill": invalid_skill_ids,
    "Demand -> Project": invalid_demand_projects,
    "Demand -> Role": invalid_demand_roles,
    "Demand -> Skill": invalid_demand_skills,
    "Allocation -> Employee": invalid_allocation_employees,
    "Allocation -> Project": invalid_allocation_projects
}

for name, errors in checks.items():
    if errors == 0:
        print(f"{name}: PASS")
    else:
        print(f"{name}: FAIL - {errors} invalid references")

# 7. GAP ANALYSIS VALIDATION

print("\n7. GAP ANALYSIS VALIDATION")

gap_analysis = pd.read_csv(RAW_DIR / "gap_analysis.csv")

# Recalculate expected gap hours
gap_analysis["calculated_gap"] = (
    gap_analysis["required_hours"] -
    gap_analysis["available_hours"]
).clip(lower=0)

# Compare calculated and stored gap hours
invalid_gaps = (
    gap_analysis["gap_hours"] !=
    gap_analysis["calculated_gap"]
).sum()

if invalid_gaps == 0:
    print("Gap hours: PASS")
else:
    print(f"Gap hours: FAIL - {invalid_gaps} incorrect records")

# Check gap status
gap_analysis["calculated_status"] = gap_analysis[
    "calculated_gap"
].apply(
    lambda x: "covered" if x == 0 else "shortage"
)

invalid_status = (
    gap_analysis["gap_status"] !=
    gap_analysis["calculated_status"]
).sum()

if invalid_status == 0:
    print("Gap status: PASS")
else:
    print(f"Gap status: FAIL - {invalid_status} incorrect records")

print("\nGap Analysis Summary")
print("Total records:", len(gap_analysis))
print("Covered:", (gap_analysis["gap_status"] == "covered").sum())
print("Shortages:", (gap_analysis["gap_status"] == "shortage").sum())
print("Total gap hours:", gap_analysis["gap_hours"].sum())
# 8. REMAINING RELATIONSHIP VALIDATION

print("\n8. REMAINING RELATIONSHIP VALIDATION")

availability = pd.read_csv(RAW_DIR / "availability.csv")
training = pd.read_csv(RAW_DIR / "training.csv")

remaining_checks = {
    "Availability -> Employee": (
        ~availability["employee_id"].isin(employees["employee_id"])
    ).sum(),

    "Training -> Employee": (
        ~training["employee_id"].isin(employees["employee_id"])
    ).sum(),

    "Training -> Skill": (
        ~training["skill_id"].isin(skills["skill_id"])
    ).sum(),

    "Gap Analysis -> Project": (
        ~gap_analysis["project_id"].isin(projects["project_id"])
    ).sum(),

    "Gap Analysis -> Skill": (
        ~gap_analysis["skill_id"].isin(skills["skill_id"])
    ).sum()
}

for name, errors in remaining_checks.items():
    print(
        f"{name}: PASS" if errors == 0
        else f"{name}: FAIL - {errors} invalid references"
    )


# 9. PROCESSED DATASET VALIDATION

print("\n9. PROCESSED DATASET VALIDATION")

PROCESSED_DIR = DATA_DIR / "processed"

processed_files = [
    "capacity_analysis.csv",
    "demand_forecast.csv",
    "skill_gap_analysis.csv",
    "skill_intelligence.csv",
    "talent_discovery.csv",
    "workforce_exceptions.csv",
    "workforce_recommendations.csv"
]

for filename in processed_files:

    file_path = PROCESSED_DIR / filename

    if file_path.exists():
        df = pd.read_csv(file_path)

        print(
            f"{filename}: PASS - "
            f"{len(df)} records, "
            f"{len(df.columns)} columns"
        )

        if filename in [
            "skill_intelligence.csv",
            "talent_discovery.csv"
        ]:
            unexpected_missing = (
                df.drop(columns=["expiry_date"]).isnull().sum().sum()
            )
        else:
            unexpected_missing = df.isnull().sum().sum()

        if unexpected_missing == 0:
            print("  Missing value check: PASS")
        else:
            print(
                "  Missing value check: FAIL -",
                unexpected_missing,
                "unexpected missing values"
            )

    else:
        print(f"{filename}: FAIL - File not found")


# 10. CAPACITY BUSINESS RULE VALIDATION

print("\n10. CAPACITY BUSINESS RULE VALIDATION")

capacity = pd.read_csv(
    PROCESSED_DIR / "capacity_analysis.csv"
)

# Available hours cannot be negative
invalid_available = (capacity["available_hours"] < 0).sum()

# Allocated hours cannot be negative
invalid_allocated = (capacity["allocated_hours"] < 0).sum()

# Verify remaining hours calculation
expected_remaining = (
    capacity["available_hours"] - capacity["allocated_hours"]
)

incorrect_remaining = (
    (capacity["remaining_hours"] - expected_remaining).abs() > 0.01
).sum()

print(
    "Available hours:",
    "PASS" if invalid_available == 0 else f"FAIL - {invalid_available} invalid records"
)

print(
    "Allocated hours:",
    "PASS" if invalid_allocated == 0 else f"FAIL - {invalid_allocated} invalid records"
)

print(
    "Remaining hours calculation:",
    "PASS" if incorrect_remaining == 0 else f"FAIL - {incorrect_remaining} incorrect records"
)

print(
    "Negative remaining hours:",
    (capacity["remaining_hours"] < 0).sum(),
    "(Allowed - indicates over-allocation)"
)


# 11. DEMAND FORECAST VALIDATION

print("\n11. DEMAND FORECAST VALIDATION")

forecast = pd.read_csv(
    PROCESSED_DIR / "demand_forecast.csv"
)

negative_committed = (
    forecast["committed_hours"] < 0
).sum()

negative_proposed = (
    forecast["proposed_hours"] < 0
).sum()

negative_expected = (
    forecast["expected_hours"] < 0
).sum()

invalid_lower_bound = (
    forecast["expected_hours"]
    < forecast["committed_hours"] - 0.01
).sum()

invalid_upper_bound = (
    forecast["expected_hours"]
    > forecast["committed_hours"]
    + forecast["proposed_hours"] + 0.01
).sum()

print(
    "Committed hours:",
    "PASS" if negative_committed == 0 else "FAIL"
)

print(
    "Proposed hours:",
    "PASS" if negative_proposed == 0 else "FAIL"
)

print(
    "Expected hours:",
    "PASS" if negative_expected == 0 else "FAIL"
)

print(
    "Expected demand lower bound:",
    "PASS" if invalid_lower_bound == 0 else "FAIL"
)

print(
    "Expected demand upper bound:",
    "PASS" if invalid_upper_bound == 0 else "FAIL"
)


# 12. SKILL GAP ANALYSIS VALIDATION

print("\n12. SKILL GAP ANALYSIS VALIDATION")

skill_gaps = pd.read_csv(
    PROCESSED_DIR / "skill_gap_analysis.csv"
)

negative_required = (
    skill_gaps["required_hours"] < 0
).sum()

negative_available = (
    skill_gaps["available_hours"] < 0
).sum()

negative_gap = (
    skill_gaps["gap_hours"] < 0
).sum()

expected_gap = (
    skill_gaps["required_hours"]
    - skill_gaps["available_hours"]
).clip(lower=0)

incorrect_gap = (
    (skill_gaps["gap_hours"] - expected_gap).abs() > 0.01
).sum()

expected_status = skill_gaps["gap_hours"].apply(
    lambda x: "Shortage" if x > 0 else "Covered"
)

incorrect_status = (
    skill_gaps["gap_status"] != expected_status
).sum()

print(
    "Required hours:",
    "PASS" if negative_required == 0 else "FAIL"
)

print(
    "Available hours:",
    "PASS" if negative_available == 0 else "FAIL"
)

print(
    "Gap hours:",
    "PASS" if negative_gap == 0 else "FAIL"
)

print(
    "Gap calculation:",
    "PASS" if incorrect_gap == 0 else "FAIL"
)

print(
    "Gap status:",
    "PASS" if incorrect_status == 0 else "FAIL"
)


# 13. WORKFORCE RECOMMENDATION VALIDATION

print("\n13. WORKFORCE RECOMMENDATION VALIDATION")

recommendations = pd.read_csv(
    PROCESSED_DIR / "workforce_recommendations.csv"
)

negative_gap = (
    recommendations["gap_hours"] < 0
).sum()

negative_internal_hours = (
    recommendations["internal_available_hours"] < 0
).sum()

negative_remaining = (
    recommendations["remaining_gap"] < 0
).sum()

incorrect_balance = (
    (
        recommendations["gap_hours"]
        - recommendations["internal_available_hours"]
        - recommendations["remaining_gap"]
    ).abs() > 0.01
).sum()

invalid_recommendations = (
    ~recommendations["recommendation"].isin([
        "Internal Reallocation",
        "Training",
        "External Hiring"
    ])
).sum()

print(
    "Original shortage hours:",
    "PASS" if negative_gap == 0 else "FAIL"
)

print(
    "Internal assigned hours:",
    "PASS" if negative_internal_hours == 0 else "FAIL"
)

print(
    "Remaining shortage hours:",
    "PASS" if negative_remaining == 0 else "FAIL"
)

print(
    "Shortage allocation balance:",
    "PASS" if incorrect_balance == 0 else "FAIL"
)

print(
    "Recommendation categories:",
    "PASS" if invalid_recommendations == 0 else "FAIL"
)

print("\nRecommendation Distribution:")
print(recommendations["recommendation"].value_counts())


# 14. SKILL INTELLIGENCE VALIDATION

print("\n14. SKILL INTELLIGENCE VALIDATION")

skill_data = pd.read_csv(
    PROCESSED_DIR / "skill_intelligence.csv"
)

today = (
    pd.Timestamp(REFERENCE_DATE)
    if os.environ.get("WORKFORCEIQ_DATA_ROOT")
    else pd.Timestamp.today().normalize()
)

skill_data["last_verified_date"] = pd.to_datetime(
    skill_data["last_verified_date"]
)

skill_data["expiry_date"] = pd.to_datetime(
    skill_data["expiry_date"],
    errors="coerce"
)

# Check valid skill status categories
invalid_status = (
    ~skill_data["skill_status"].isin([
        "Current",
        "Stale",
        "Expired"
    ])
).sum()

# Check qualification logic
expected_qualified = (
    (skill_data["proficiency_level"] >= 3) &
    (skill_data["skill_status"] == "Current")
)

incorrect_qualification = (
    skill_data["is_qualified"] != expected_qualified
).sum()

# Check that only active employees are included
inactive_employees = (
    skill_data["employment_status"] != "active"
).sum() if "employment_status" in skill_data.columns else 0

# Check proficiency range
invalid_proficiency = (
    ~skill_data["proficiency_level"].between(1, 5)
).sum()

print(
    "Skill status categories:",
    "PASS" if invalid_status == 0 else "FAIL"
)

print(
    "Qualification logic:",
    "PASS" if incorrect_qualification == 0 else "FAIL"
)

print(
    "Proficiency range:",
    "PASS" if invalid_proficiency == 0 else "FAIL"
)

print(
    "Inactive employee records:",
    "PASS" if inactive_employees == 0 else "FAIL"
)

print("\nSkill Status Distribution:")
print(skill_data["skill_status"].value_counts())

print("\nQualification Distribution:")
print(skill_data["is_qualified"].value_counts())


# 15. TALENT DISCOVERY VALIDATION

print("\n15. TALENT DISCOVERY VALIDATION")

talent_data = pd.read_csv(
    PROCESSED_DIR / "talent_discovery.csv"
)

# Check that all discovered employees have qualified skills
unqualified_records = (
    talent_data["is_qualified"] != True
).sum()

# Check that remaining capacity is positive
invalid_remaining = (
    talent_data["remaining_hours"] <= 0
).sum()

# Check that skill counts are valid
invalid_skill_count = (
    talent_data["qualified_skill_count"] <= 0
).sum()

# Verify skill capacity calculation
expected_skill_hours = (
    talent_data["remaining_hours"] /
    talent_data["qualified_skill_count"]
)

incorrect_skill_hours = (
    (
        talent_data["skill_available_hours"]
        - expected_skill_hours
    ).abs() > 0.01
).sum()

# Check that skill available hours are positive
invalid_skill_hours = (
    talent_data["skill_available_hours"] <= 0
).sum()

print(
    "Qualified employee records:",
    "PASS" if unqualified_records == 0 else "FAIL"
)

print(
    "Positive remaining capacity:",
    "PASS" if invalid_remaining == 0 else "FAIL"
)

print(
    "Qualified skill count:",
    "PASS" if invalid_skill_count == 0 else "FAIL"
)

print(
    "Skill capacity calculation:",
    "PASS" if incorrect_skill_hours == 0 else "FAIL"
)

print(
    "Positive skill available hours:",
    "PASS" if invalid_skill_hours == 0 else "FAIL"
)

# 16. WORKFORCE EXCEPTION VALIDATION

print("\n16. WORKFORCE EXCEPTION VALIDATION")

exceptions = pd.read_csv(
    PROCESSED_DIR / "workforce_exceptions.csv"
)

# Load source datasets
capacity_data = pd.read_csv(
    PROCESSED_DIR / "capacity_analysis.csv"
)

skill_data = pd.read_csv(
    PROCESSED_DIR / "skill_intelligence.csv"
)

allocation_data = pd.read_csv(
    RAW_DIR / "allocations.csv"
)

employee_data = pd.read_csv(
    RAW_DIR / "employees.csv"
)

# 1. Check exception IDs
duplicate_exception_ids = (
    exceptions["exception_id"].duplicated().sum()
)

# 2. Check valid exception types
valid_types = [
    "Over-allocation",
    "Stale Skill",
    "Expired Skill",
    "Overlapping Projects"
]

invalid_types = (
    ~exceptions["exception_type"].isin(valid_types)
).sum()

# 3. Check severity values
valid_severities = ["High", "Medium"]

invalid_severity = (
    ~exceptions["severity"].isin(valid_severities)
).sum()

# 4. Check resolution status
invalid_status = (
    exceptions["resolution_status"] != "Open"
).sum()

# 5. Check required fields
required_columns = [
    "exception_id",
    "exception_type",
    "employee_id",
    "affected_entity",
    "description",
    "severity",
    "resolution_status"
]

missing_columns = [
    column for column in required_columns
    if column not in exceptions.columns
]

# 6. Check employee relationships
valid_employee_ids = set(employee_data["employee_id"])

invalid_employee_references = (
    ~exceptions["employee_id"].isin(valid_employee_ids)
).sum()

# 7. Check expected over-allocation exceptions
expected_overallocations = (
    capacity_data["utilization_status"] == "Overallocated"
).sum()

actual_overallocations = (
    exceptions["exception_type"] == "Over-allocation"
).sum()

# 8. Check expected skill exceptions
expected_skill_exceptions = (
    skill_data["skill_status"].isin(["Stale", "Expired"])
).sum()

actual_skill_exceptions = exceptions[
    exceptions["exception_type"].isin(
        ["Stale Skill", "Expired Skill"]
    )
].shape[0]

# 9. Independently count overlapping project assignments
allocation_data["allocation_start"] = pd.to_datetime(
    allocation_data["allocation_start"]
)

allocation_data["allocation_end"] = pd.to_datetime(
    allocation_data["allocation_end"]
)

expected_overlaps = 0

for employee_id, group in allocation_data.groupby("employee_id"):

    group = group.sort_values("allocation_start")
    records = group.to_dict("records")

    for i in range(len(records)):
        for j in range(i + 1, len(records)):

            first = records[i]
            second = records[j]

            if second["allocation_start"] > first["allocation_end"]:
                break

            if first["project_id"] != second["project_id"]:
                expected_overlaps += 1

actual_overlaps = (
    exceptions["exception_type"] == "Overlapping Projects"
).sum()

# 10. Check severity rules
severity_rules = {
    "Over-allocation": "High",
    "Overlapping Projects": "High",
    "Stale Skill": "Medium",
    "Expired Skill": "Medium"
}

incorrect_severity = sum(
    (
        exceptions.loc[
            exceptions["exception_type"] == exception_type,
            "severity"
        ] != expected_severity
    ).sum()
    for exception_type, expected_severity in severity_rules.items()
)

# Display validation results
print(
    "Unique exception IDs:",
    "PASS" if duplicate_exception_ids == 0 else "FAIL"
)

print(
    "Required columns:",
    "PASS" if len(missing_columns) == 0 else "FAIL"
)

print(
    "Valid exception types:",
    "PASS" if invalid_types == 0 else "FAIL"
)

print(
    "Valid severity values:",
    "PASS" if invalid_severity == 0 else "FAIL"
)

print(
    "Valid resolution statuses:",
    "PASS" if invalid_status == 0 else "FAIL"
)

print(
    "Employee relationships:",
    "PASS" if invalid_employee_references == 0 else "FAIL"
)

print(
    "Over-allocation exception count:",
    "PASS" if expected_overallocations == actual_overallocations else "FAIL"
)

print(
    "Skill exception count:",
    "PASS" if expected_skill_exceptions == actual_skill_exceptions else "FAIL"
)

print(
    "Overlapping project exception count:",
    "PASS" if expected_overlaps == actual_overlaps else "FAIL"
)

print(
    "Severity business rules:",
    "PASS" if incorrect_severity == 0 else "FAIL"
)

print("\nEXCEPTION SUMMARY")
print("Total exceptions:", len(exceptions))
print("Expected over-allocations:", expected_overallocations)
print("Expected skill exceptions:", expected_skill_exceptions)
print("Expected overlapping projects:", expected_overlaps)
print("\nActual exception distribution:")
print(exceptions["exception_type"].value_counts())




# 17. PROCESSED DATASET DUPLICATE VALIDATION

print("\n17. PROCESSED DATASET DUPLICATE VALIDATION")

# Load processed datasets
capacity_data = pd.read_csv(PROCESSED_DIR / "capacity_analysis.csv")
forecast_data = pd.read_csv(PROCESSED_DIR / "demand_forecast.csv")
gap_data = pd.read_csv(PROCESSED_DIR / "skill_gap_analysis.csv")
skill_data = pd.read_csv(PROCESSED_DIR / "skill_intelligence.csv")
talent_data = pd.read_csv(PROCESSED_DIR / "talent_discovery.csv")
recommendation_data = pd.read_csv(PROCESSED_DIR / "workforce_recommendations.csv")
exception_data = pd.read_csv(PROCESSED_DIR / "workforce_exceptions.csv")

# Check duplicate records using their logical identifiers
duplicate_checks = {
    "Capacity": capacity_data.duplicated(
        subset=["employee_id", "availability_date"]
    ).sum(),

    "Demand Forecast": forecast_data.duplicated(
        subset=["demand_week", "department", "role_id", "skill_id"]
    ).sum(),

    "Skill Gap": gap_data.duplicated(
        subset=["demand_week", "skill_id"]
    ).sum(),

    "Skill Intelligence": skill_data.duplicated(
        subset=["employee_skill_id"]
    ).sum(),

    "Talent Discovery": talent_data.duplicated(
        subset=["employee_skill_id", "availability_date"]
    ).sum(),

    "Workforce Recommendations": recommendation_data.duplicated(
        subset=["demand_week", "skill_id"]
    ).sum(),

    "Workforce Exceptions": exception_data.duplicated(
        subset=["exception_id"]
    ).sum()
}

for dataset, duplicates in duplicate_checks.items():

    print(
        dataset + ":",
        "PASS" if duplicates == 0 else "FAIL",
        "- Duplicate records:",
        duplicates
    )


# 18. CROSS-DATASET CONSISTENCY VALIDATION

print("\n18. CROSS-DATASET CONSISTENCY VALIDATION")

# Load required datasets
capacity_data = pd.read_csv(PROCESSED_DIR / "capacity_analysis.csv")
forecast_data = pd.read_csv(PROCESSED_DIR / "demand_forecast.csv")
gap_data = pd.read_csv(PROCESSED_DIR / "skill_gap_analysis.csv")
skill_data = pd.read_csv(PROCESSED_DIR / "skill_intelligence.csv")
talent_data = pd.read_csv(PROCESSED_DIR / "talent_discovery.csv")
recommendation_data = pd.read_csv(
    PROCESSED_DIR / "workforce_recommendations.csv"
)

master_skills = pd.read_csv(RAW_DIR / "skills.csv")
master_employees = pd.read_csv(RAW_DIR / "employees.csv")

# 1. Talent employees must exist in Skill Intelligence
skill_employee_ids = set(skill_data["employee_id"])

invalid_talent_employees = (
    ~talent_data["employee_id"].isin(skill_employee_ids)
).sum()

# 2. Talent employee-skill combinations must exist in Skill Intelligence
valid_employee_skills = set(
    zip(skill_data["employee_id"], skill_data["skill_id"])
)

invalid_talent_skill_pairs = sum(
    (employee_id, skill_id) not in valid_employee_skills
    for employee_id, skill_id in zip(
        talent_data["employee_id"],
        talent_data["skill_id"]
    )
)

# 3. Skill Gap Analysis skills must exist in master Skills
valid_skill_ids = set(master_skills["skill_id"])

invalid_gap_skills = (
    ~gap_data["skill_id"].isin(valid_skill_ids)
).sum()

# 4. Recommendation skills must exist in master Skills
invalid_recommendation_skills = (
    ~recommendation_data["skill_id"].isin(valid_skill_ids)
).sum()

# 5. Capacity employees must exist in master Employees
valid_employee_ids = set(master_employees["employee_id"])

invalid_capacity_employees = (
    ~capacity_data["employee_id"].isin(valid_employee_ids)
).sum()

# 6. Forecast skills must exist in master Skills
invalid_forecast_skills = (
    ~forecast_data["skill_id"].isin(valid_skill_ids)
).sum()

# Display results
print(
    "Talent employee relationships:",
    "PASS" if invalid_talent_employees == 0 else "FAIL"
)

print(
    "Talent employee-skill relationships:",
    "PASS" if invalid_talent_skill_pairs == 0 else "FAIL"
)

print(
    "Skill Gap -> Master Skills:",
    "PASS" if invalid_gap_skills == 0 else "FAIL"
)

print(
    "Recommendations -> Master Skills:",
    "PASS" if invalid_recommendation_skills == 0 else "FAIL"
)

print(
    "Capacity -> Master Employees:",
    "PASS" if invalid_capacity_employees == 0 else "FAIL"
)

print(
    "Demand Forecast -> Master Skills:",
    "PASS" if invalid_forecast_skills == 0 else "FAIL"
)


# --------------------------------------------------
# 19. RECOMMENDATION LOGIC VALIDATION
# --------------------------------------------------

print("\n19. RECOMMENDATION LOGIC VALIDATION")

# Check whether recommendations match actual shortages

recommendation_keys = set(
    zip(
        recommendations["demand_week"],
        recommendations["skill_id"]
    )
)

shortage_keys = set(
    zip(
        skill_gaps.loc[
            skill_gaps["gap_status"] == "Shortage",
            "demand_week"
        ],
        skill_gaps.loc[
            skill_gaps["gap_status"] == "Shortage",
            "skill_id"
        ]
    )
)

print(
    "Recommendations match actual shortages:",
    "PASS" if recommendation_keys.issubset(shortage_keys) else "FAIL"
)

# Check original shortage hours against skill gap analysis

expected_gaps = skill_gaps[
    skill_gaps["gap_status"] == "Shortage"
][["demand_week", "skill_id", "gap_hours"]]

gap_comparison = recommendations.merge(
    expected_gaps,
    on=["demand_week", "skill_id"],
    how="left",
    suffixes=("_recommendation", "_source")
)

gap_match = (
    gap_comparison["gap_hours_recommendation"]
    - gap_comparison["gap_hours_source"]
).abs() < 0.01

print(
    "Original shortage hours match:",
    "PASS" if gap_match.all() else "FAIL"
)

# Check recommendation decision rules

expected_recommendations = []

for _, row in recommendations.iterrows():

    if row["remaining_gap"] <= 0:
        expected_recommendations.append("Internal Reallocation")

    elif row["potential_trainees"] > 0:
        expected_recommendations.append("Training")

    else:
        expected_recommendations.append("External Hiring")

logic_match = (
    recommendations["recommendation"].tolist()
    == expected_recommendations
)

print(
    "Recommendation decision logic:",
    "PASS" if logic_match else "FAIL"
)

# Check recommendation explanations

valid_explanations = (
    recommendations["recommendation_reason"].notna()
    & recommendations["recommendation_reason"].astype(str).str.strip().ne("")
)

print(
    "Recommendation explanations:",
    "PASS" if valid_explanations.all() else "FAIL"
)

print("\nRecommendation Logic Summary")
print("-" * 55)

print("Total recommendations:", len(recommendations))
print("Matching shortage records:", gap_match.sum())
print("Valid decision rules:", logic_match)
print("Recommendations with explanations:", valid_explanations.sum())


# --------------------------------------------------
# 20. SCENARIO SIMULATION VALIDATION
# --------------------------------------------------

from engine.what_if_simulator import (
    load_data as load_simulator_data,
    simulate_internal_reallocation,
    simulate_employee_training,
    simulate_external_hiring,
    simulate_combined_strategy
)

print("\n20. SCENARIO SIMULATION VALIDATION")

simulator_data = load_simulator_data()

# Test up to five distinct shortage scenarios with positive original gap.
scenario_gap_column = next(
    (column for column in ("original_gap_hours", "gap_hours")
     if column in recommendations.columns),
    None,
)
scenario_test_rows = recommendations.copy()
if scenario_gap_column is not None:
    scenario_test_rows[scenario_gap_column] = pd.to_numeric(
        scenario_test_rows[scenario_gap_column], errors="coerce"
    )
    scenario_test_rows = scenario_test_rows[
        scenario_test_rows[scenario_gap_column] > 0
    ]

scenario_key_columns = [
    column for column in ("demand_week", "skill_id")
    if column in scenario_test_rows.columns
]
if len(scenario_key_columns) == 2:
    scenario_test_rows = scenario_test_rows.dropna(
        subset=scenario_key_columns
    )
    if scenario_gap_column is not None:
        scenario_test_rows = scenario_test_rows.sort_values(
            scenario_gap_column, ascending=False, kind="stable"
        )
    scenario_test_rows = scenario_test_rows.drop_duplicates(
        subset=scenario_key_columns, keep="first"
    )
scenario_test_rows = scenario_test_rows.head(5).copy()

internal_checks = []
training_checks = []
hiring_checks = []
combined_checks = []

for _, row in scenario_test_rows.iterrows():

    demand_week = row["demand_week"]
    skill_id = row["skill_id"]

    internal = simulate_internal_reallocation(
        simulator_data, demand_week, skill_id
    )

    training = simulate_employee_training(
        simulator_data, demand_week, skill_id
    )

    hiring = simulate_external_hiring(
        simulator_data, demand_week, skill_id
    )

    combined = simulate_combined_strategy(
        simulator_data, demand_week, skill_id
    )

    if any(result is None for result in [
        internal, training, hiring, combined
    ]):
        internal_checks.append(False)
        training_checks.append(False)
        hiring_checks.append(False)
        combined_checks.append(False)
        continue

    # Internal reallocation checks
    internal_checks.extend([
        abs(
            internal["allocated_hours"]
            + internal["remaining_gap_hours"]
            - internal["original_gap_hours"]
        ) <= 0.05,

        internal["allocated_hours"]
        <= internal["available_internal_hours"] + 0.05
    ])

    # Employee training checks
    training_checks.extend([
        abs(
            training["productive_hours_after_training"]
            + training["remaining_gap_hours"]
            - training["original_gap_hours"]
        ) <= 0.05,

        training["productive_hours_after_training"]
        <= training["estimated_training_capacity_hours"] + 0.05,

        training["training_cost"]
        == training["employees_selected_for_training"] * 15000
    ])

    # External hiring checks
    hiring_checks.extend([
        abs(
            hiring["productive_hours_needed"]
            + hiring["remaining_gap_hours"]
            - hiring["original_gap_hours"]
        ) <= 0.05,

        hiring["productive_hours_needed"]
        <= hiring["hiring_capacity_hours"] + 0.05,

        hiring["hiring_cost"]
        == hiring["employees_required"] * 75000
    ])

    # Combined strategy checks
    combined_resolved = (
        combined["internal_hours_allocated"]
        + combined["training_hours_contributed"]
        + combined["hiring_hours_contributed"]
    )

    combined_checks.extend([
        abs(
            combined_resolved
            + combined["remaining_gap_hours"]
            - combined["original_gap_hours"]
        ) <= 0.05,

        abs(
            combined["total_cost"]
            - combined["training_cost"]
            - combined["hiring_cost"]
        ) <= 0.05,

        combined["internal_hours_allocated"]
        <= combined["original_gap_hours"] * 0.50 + 0.05,

        combined["training_cost"] <= 75000
    ])

print(
    "Scenarios tested:",
    len(scenario_test_rows)
)

print(
    "Internal Reallocation calculations:",
    "PASS" if internal_checks and all(internal_checks) else "FAIL"
)

print(
    "Employee Training calculations:",
    "PASS" if training_checks and all(training_checks) else "FAIL"
)

print(
    "External Hiring calculations:",
    "PASS" if hiring_checks and all(hiring_checks) else "FAIL"
)

print(
    "Combined Strategy calculations:",
    "PASS" if combined_checks and all(combined_checks) else "FAIL"
)
