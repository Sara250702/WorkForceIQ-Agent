
import pandas as pd
from pathlib import Path
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

PROCESSED_DIR = data_root(BASE_DIR) / "processed"

# Load datasets
demand = pd.read_csv(
    PROCESSED_DIR / "demand_forecast.csv"
)

talent = pd.read_csv(
    PROCESSED_DIR / "talent_discovery.csv"
)

print("=" * 50)
print("WORKFORCEIQ SKILL GAP ANALYSIS")
print("=" * 50)

print("\nDemand forecast records:", len(demand))
print("Talent discovery records:", len(talent))

# Convert date columns
demand["demand_week"] = pd.to_datetime(
    demand["demand_week"]
)

talent["availability_date"] = pd.to_datetime(
    talent["availability_date"]
)

# Use the skill-wise available hours calculated by talent discovery
talent = talent[
    (talent["is_qualified"] == True) &
    (talent["skill_available_hours"] > 0)
].copy()

# Aggregate available capacity by week and skill
available_talent = talent.groupby(
    ["availability_date", "skill_id"],
    as_index=False
).agg(
    available_hours=("skill_available_hours", "sum"),
    qualified_employees=("employee_id", "nunique")
)

# Rename date column
available_talent = available_talent.rename(
    columns={"availability_date": "demand_week"}
)

print("\nPrepared demand records:", len(demand))
print("Prepared talent records:", len(available_talent))

print("\nFirst five prepared talent records:")
print(available_talent.head())

# Combine demand across roles and departments
weekly_demand = demand.groupby(
    ["demand_week", "skill_id"],
    as_index=False
).agg(
    required_hours=("expected_hours", "sum"),
    committed_hours=("committed_hours", "sum"),
    proposed_hours=("proposed_hours", "sum")
)

# Match weekly demand with available talent
skill_gaps = weekly_demand.merge(
    available_talent,
    on=["demand_week", "skill_id"],
    how="left"
)

# Replace missing supply with zero
skill_gaps["available_hours"] = (
    skill_gaps["available_hours"].fillna(0)
)

skill_gaps["qualified_employees"] = (
    skill_gaps["qualified_employees"].fillna(0)
)

# Calculate shortage
skill_gaps["gap_hours"] = (
    skill_gaps["required_hours"] -
    skill_gaps["available_hours"]
).clip(lower=0)

# Identify skill gap status
skill_gaps["gap_status"] = skill_gaps["gap_hours"].apply(
    lambda x: "Shortage" if x > 0 else "Covered"
)

# Display results
print("\nSkill Gap Analysis Results:")
print("Total records:", len(skill_gaps))

print("\nGap Status Distribution:")
print(skill_gaps["gap_status"].value_counts())

print("\nTotal Required Hours:",
      round(skill_gaps["required_hours"].sum(), 2))

print("Total Available Hours:",
      round(skill_gaps["available_hours"].sum(), 2))

print("Total Skill Gap Hours:",
      round(skill_gaps["gap_hours"].sum(), 2))

# Save skill gap analysis results
output_file = PROCESSED_DIR / "skill_gap_analysis.csv"

skill_gaps.to_csv(output_file, index=False)

print("\nSkill Gap Analysis saved successfully!")
print("Records saved:", len(skill_gaps))
print("Output location:", output_file)
