
import pandas as pd
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

RAW_DIR = data_root(BASE_DIR) / "raw"

# Load existing datasets
demand_df = pd.read_csv(RAW_DIR / "demand_plans.csv")
employee_skills_df = pd.read_csv(RAW_DIR / "employee_skills.csv")
employees_df = pd.read_csv(RAW_DIR / "employees.csv")

# Keep only active employees
active_employees = employees_df[
    employees_df["status"] == "active"
]

# Get skills belonging to active employees
active_skills = employee_skills_df.merge(
    active_employees[["employee_id"]],
    on="employee_id",
    how="inner"
)

# Count qualified employees for each skill
# Proficiency 3 or above is considered qualified
qualified_skills = active_skills[
    active_skills["proficiency_level"] >= 3
]

available_skill_counts = (
    qualified_skills.groupby("skill_id")["employee_id"]
    .nunique()
    .to_dict()
)

gap_records = []
gap_number = 1

# Aggregate weekly demand by project and skill
grouped_demand = demand_df.groupby(
    ["project_id", "skill_id"],
    as_index=False
)["required_hours"].sum()

for _, demand in grouped_demand.iterrows():

    required_hours = float(demand["required_hours"])

    # Find the number of employees qualified in this skill
    qualified_count = available_skill_counts.get(
        demand["skill_id"], 0
    )

    # Estimate available hours using 40 hours per employee
    available_hours = qualified_count * 40

    gap_hours = max(
        required_hours - available_hours,
        0
    )

    if gap_hours == 0:
        gap_status = "covered"
    else:
        gap_status = "shortage"

    gap_records.append({
        "gap_id": f"GAP-{gap_number:08d}",
        "project_id": demand["project_id"],
        "skill_id": demand["skill_id"],
        "required_hours": required_hours,
        "available_hours": available_hours,
        "gap_hours": gap_hours,
        "gap_status": gap_status
    })

    gap_number += 1

# Create DataFrame
df = pd.DataFrame(gap_records)

# Save gap analysis
output_file = RAW_DIR / "gap_analysis.csv"
df.to_csv(output_file, index=False)

print("Gap analysis generated successfully!")
print("Total gap records:", len(df))
print("Covered records:", (df["gap_status"] == "covered").sum())
print("Shortage records:", (df["gap_status"] == "shortage").sum())

print("\nTotal required hours:", df["required_hours"].sum())
print("Total available hours:", df["available_hours"].sum())
print("Total skill gap hours:", df["gap_hours"].sum())

print("\nFirst five records:")
print(df.head())
