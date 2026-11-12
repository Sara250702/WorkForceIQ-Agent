
import pandas as pd
from pathlib import Path
import sys

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

DATA_DIR = data_root(BASE_DIR)
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"

# Load workforce datasets
capacity = pd.read_csv(
    PROCESSED_DIR / "capacity_analysis.csv"
)

skills = pd.read_csv(
    PROCESSED_DIR / "skill_intelligence.csv"
)

allocations = pd.read_csv(
    RAW_DIR / "allocations.csv"
)

allocations["allocation_start"] = pd.to_datetime(
    allocations["allocation_start"]
)

allocations["allocation_end"] = pd.to_datetime(
    allocations["allocation_end"]
)

print("=" * 60)
print("WORKFORCEIQ EXCEPTION DETECTION ENGINE")
print("=" * 60)

print("\nDatasets loaded successfully!")

print("Capacity records:", len(capacity))
print("Skill records:", len(skills))
print("Allocation records:", len(allocations))


# Detect employees whose allocated hours exceed available hours

overallocated = capacity[
    capacity["utilization_status"] == "Overallocated"
].copy()

print("\nOVERALLOCATION EXCEPTIONS")
print("-" * 60)

print("Total overallocated employee-week records:", len(overallocated))

print(
    overallocated[
        [
            "employee_id",
            "availability_date",
            "available_hours",
            "allocated_hours",
            "utilization_percentage"
        ]
    ].head(10).to_string(index=False)
)

# Detect stale and expired employee skills

skill_exceptions = skills[
    skills["skill_status"].isin(["Stale", "Expired"])
].copy()

print("\nSTALE AND EXPIRED SKILL EXCEPTIONS")
print("-" * 60)

print("Total skill exceptions:", len(skill_exceptions))

print("\nException distribution:")
print(
    skill_exceptions["skill_status"].value_counts().to_string()
)

print("\nFirst 10 skill exceptions:")

print(
    skill_exceptions[
        [
            "employee_id",
            "skill_name",
            "proficiency_level",
            "days_since_verified",
            "skill_status"
        ]
    ].head(10).to_string(index=False)
)

# Detect overlapping project assignments

allocations["allocation_start"] = pd.to_datetime(
    allocations["allocation_start"]
)

allocations["allocation_end"] = pd.to_datetime(
    allocations["allocation_end"]
)

overlap_exceptions = []

# Compare allocations belonging to the same employee
for employee_id, employee_allocations in allocations.groupby("employee_id"):

    employee_allocations = employee_allocations.sort_values("allocation_start")

    records = employee_allocations.to_dict("records")

    for i in range(len(records)):

        for j in range(i + 1, len(records)):

            first = records[i]
            second = records[j]

            if second["allocation_start"] > first["allocation_end"]:
                break

            if first["project_id"] != second["project_id"]:

                overlap_exceptions.append({
                    "employee_id": employee_id,
                    "first_project": first["project_id"],
                    "second_project": second["project_id"],
                    "first_start": first["allocation_start"],
                    "first_end": first["allocation_end"],
                    "second_start": second["allocation_start"],
                    "second_end": second["allocation_end"]
                })

print("\nOVERLAPPING PROJECT ASSIGNMENTS")
print("-" * 60)

print("Total overlapping assignment pairs:", len(overlap_exceptions))

if overlap_exceptions:

    overlap_df = pd.DataFrame(overlap_exceptions)

    print(
        overlap_df.head(10).to_string(index=False)
    )
else:
    print("No overlapping project assignments detected.")


# Combine all detected exceptions into one report

all_exceptions = []

# 1. Over-allocation exceptions
for _, row in overallocated.iterrows():

    all_exceptions.append({
        "exception_type": "Over-allocation",
        "employee_id": row["employee_id"],
        "affected_entity": row["availability_date"],
        "description": (
            f"Allocated {row['allocated_hours']} hours "
            f"but only {row['available_hours']} hours available."
        ),
        "severity": "High",
        "resolution_status": "Open"
    })


# 2. Stale and expired skill exceptions
for _, row in skill_exceptions.iterrows():

    all_exceptions.append({
        "exception_type": row["skill_status"] + " Skill",
        "employee_id": row["employee_id"],
        "affected_entity": row["skill_name"],
        "description": (
            f"Skill proficiency: {row['proficiency_level']}. "
            f"Days since verification: {row['days_since_verified']}."
        ),
        "severity": "Medium",
        "resolution_status": "Open"
    })


# 3. Overlapping project assignment exceptions
for row in overlap_exceptions:

    all_exceptions.append({
        "exception_type": "Overlapping Projects",
        "employee_id": row["employee_id"],
        "affected_entity": (
            row["first_project"] + " / " + row["second_project"]
        ),
        "description": (
            f"Project assignments overlap between "
            f"{row['second_start'].date()} and "
            f"{min(row['first_end'], row['second_end']).date()}."
        ),
        "severity": "High",
        "resolution_status": "Open"
    })


# Convert exceptions into a DataFrame
exceptions_df = pd.DataFrame(all_exceptions)

print("\nCONSOLIDATED WORKFORCE EXCEPTION REPORT")
print("=" * 70)

print("Total detected exceptions:", len(exceptions_df))

print("\nException type distribution:")
print(exceptions_df["exception_type"].value_counts().to_string())

# Save consolidated exception report

output_path = PROCESSED_DIR / "workforce_exceptions.csv"

exceptions_df.insert(
    0,
    "exception_id",
    [f"EXC-{i:08d}" for i in range(1, len(exceptions_df) + 1)]
)

exceptions_df.to_csv(output_path, index=False)

print("\nException report saved successfully!")
print("File location:", output_path)
