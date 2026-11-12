
import pandas as pd
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

PROCESSED_DIR = data_root(BASE_DIR) / "processed"

# Load processed datasets
skills = pd.read_csv(
    PROCESSED_DIR / "skill_intelligence.csv"
)

capacity = pd.read_csv(
    PROCESSED_DIR / "capacity_analysis.csv"
)

print("=" * 50)
print("WORKFORCEIQ INTERNAL TALENT DISCOVERY")
print("=" * 50)

print("\nSkill intelligence records:", len(skills))
print("Capacity records:", len(capacity))

print("\nSkill dataset columns:")
print(skills.columns.tolist())

print("\nCapacity dataset columns:")
print(capacity.columns.tolist())

# Keep only employees with qualified skills
qualified_skills = skills[
    skills["is_qualified"] == True
].copy()

# Select the capacity information we need
capacity_details = capacity[
    [
        "employee_id",
        "availability_date",
        "available_hours",
        "allocated_hours",
        "remaining_hours",
        "utilization_status"
    ]
].copy()

# Match qualified employees with their weekly capacity
talent_pool = qualified_skills.merge(
    capacity_details,
    on="employee_id",
    how="inner"
)

# Keep employees who have some remaining capacity
talent_pool = talent_pool[
    talent_pool["remaining_hours"] > 0
].copy()

# Count qualified skills for each employee in each week
talent_pool["qualified_skill_count"] = (
    talent_pool.groupby(
        ["employee_id", "availability_date"]
    )["skill_id"].transform("nunique")
)

# Divide remaining capacity across qualified skills
talent_pool["skill_available_hours"] = (
    talent_pool["remaining_hours"] /
    talent_pool["qualified_skill_count"]
)

print("\nQualified employee-skill capacity records:", len(talent_pool))

print("\nFirst five talent matches:")
print(
    talent_pool[
        [
            "employee_id",
            "employee_name",
            "skill_name",
            "qualified_skill_count",
            "remaining_hours",
            "skill_available_hours"
        ]
    ].head(10).to_string(index=False)
)

# Save internal talent discovery results
output_file = PROCESSED_DIR / "talent_discovery.csv"

talent_pool.to_csv(output_file, index=False)

print("\nTalent Discovery dataset saved successfully!")
print("Total records saved:", len(talent_pool))
print("Output location:", output_file)

print("\nSKILL DISTRIBUTION FOR FIRST EMPLOYEE")
print("-" * 50)

print(
    talent_pool[
        talent_pool["employee_id"] == "EMP-000001"
    ][
        [
            "skill_name",
            "qualified_skill_count",
            "remaining_hours",
            "skill_available_hours"
        ]
    ].drop_duplicates("skill_name").to_string(index=False)
)
