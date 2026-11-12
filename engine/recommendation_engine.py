
import pandas as pd
from pathlib import Path
import sys
from engine.decision_rules import (
    choose_recommendation,
    explain_recommendation
)

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

DATA_DIR = data_root(BASE_DIR)
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"

# Load datasets
skill_gaps = pd.read_csv(
    PROCESSED_DIR / "skill_gap_analysis.csv"
)

talent = pd.read_csv(
    PROCESSED_DIR / "talent_discovery.csv"
)

skill_intelligence = pd.read_csv(
    PROCESSED_DIR / "skill_intelligence.csv"
)

skills = pd.read_csv(
    RAW_DIR / "skills.csv"
)

print("=" * 55)
print("WORKFORCEIQ RECOMMENDATION ENGINE")
print("=" * 55)

print("\nDatasets loaded successfully!")

print("Skill gap records:", len(skill_gaps))
print("Talent records:", len(talent))
print("Skill intelligence records:", len(skill_intelligence))

# Keep only skills that have shortages
shortages = skill_gaps[
    skill_gaps["gap_status"] == "Shortage"
].copy()

# Find total shortage hours for each skill
shortage_summary = shortages.groupby(
    "skill_id",
    as_index=False
).agg(
    total_gap_hours=("gap_hours", "sum"),
    shortage_weeks=("demand_week", "nunique")
)

# Add readable skill names
shortage_summary = shortage_summary.merge(
    skills[["skill_id", "skill_name", "skill_category"]],
    on="skill_id",
    how="left"
)

shortage_summary = shortage_summary.sort_values(
    "total_gap_hours",
    ascending=False
)

print("\nSkills requiring attention:")
print(shortage_summary.head(10).to_string(index=False))




# Find internal employees who can help fill skill shortages

qualified_talent = talent[
    (talent["is_qualified"] == True) &
    (talent["skill_available_hours"] > 0)
].copy()

# Prepare weekly shortage records
shortage_details = shortages.copy()

# Match employee capacity to shortages without double-counting
internal_assignments = []

# Process each week separately
for demand_week, weekly_shortages in shortage_details.groupby("demand_week"):

    # Track how many hours each employee still has available
    employee_capacity = {}

    weekly_talent = qualified_talent[
        qualified_talent["availability_date"] == demand_week
    ].copy()

    for _, employee in weekly_talent.iterrows():
        employee_id = employee["employee_id"]

        if employee_id not in employee_capacity:
            employee_capacity[employee_id] = employee["remaining_hours"]

    # Process the largest shortages first
    weekly_shortages = weekly_shortages.sort_values(
        "gap_hours",
        ascending=False
    )

    for _, shortage in weekly_shortages.iterrows():

        required_skill = shortage["skill_id"]
        remaining_gap = shortage["gap_hours"]

        # Find employees qualified in this skill
        candidates = weekly_talent[
            weekly_talent["skill_id"] == required_skill
        ].copy()

        assigned_employees = 0
        assigned_hours = 0

        # Assign available employee hours
        for _, candidate in candidates.iterrows():

            employee_id = candidate["employee_id"]

            available_hours = employee_capacity.get(
                employee_id, 0
            )

            if available_hours <= 0 or remaining_gap <= 0:
                continue

            hours_to_assign = min(
                available_hours,
                candidate["skill_available_hours"],
                remaining_gap
            )

            employee_capacity[employee_id] -= hours_to_assign
            remaining_gap -= hours_to_assign
            assigned_hours += hours_to_assign
            assigned_employees += 1

        internal_assignments.append({
            "demand_week": demand_week,
            "skill_id": required_skill,
            "internal_employees": assigned_employees,
            "internal_available_hours": assigned_hours,
            "remaining_gap": remaining_gap
        })

# Convert allocation results into a DataFrame
internal_talent = pd.DataFrame(internal_assignments)

# Match allocation results with shortage records
shortage_details = shortage_details.merge(
    internal_talent,
    on=["demand_week", "skill_id"],
    how="left"
)

# Add readable skill names
shortage_details = shortage_details.merge(
    skills[["skill_id", "skill_name", "skill_category"]],
    on="skill_id",
    how="left"
)

print("\nINTERNAL REALLOCATION COVERAGE")
print("-" * 60)

print(
    "Total original shortage hours:",
    round(shortage_details["gap_hours"].sum(), 2)
)

print(
    "Total assigned internal hours:",
    round(shortage_details["internal_available_hours"].sum(), 2)
)

print(
    "Total remaining shortage hours:",
    round(shortage_details["remaining_gap"].sum(), 2)
)

print(
    "Total estimated internal available hours:",
    round(shortage_details["internal_available_hours"].sum(), 2)
)

print(
    "Total remaining shortage hours:",
    round(shortage_details["remaining_gap"].sum(), 2)
)

# Display weekly recommendations data
shortage_details = shortage_details.sort_values(
    "gap_hours",
    ascending=False
)




# Identify potential employees for skill training

training_candidates = skill_intelligence[
    (skill_intelligence["skill_status"] == "Current") &
    (skill_intelligence["proficiency_level"] < 3)
].copy()

# Count potential training candidates for each skill
training_summary = training_candidates.groupby(
    "skill_id",
    as_index=False
).agg(
    potential_trainees=("employee_id", "nunique")
)

# Add training candidate information to recommendations
shortage_details = shortage_details.merge(
    training_summary,
    on="skill_id",
    how="left"
)

shortage_details["potential_trainees"] = (
    shortage_details["potential_trainees"].fillna(0)
)
# Compare internal reallocation, training and hiring options


shortage_details["recommendation"] = (
    shortage_details.apply(choose_recommendation, axis=1)
)

# Explain why each recommendation was selected



shortage_details["recommendation_reason"] = shortage_details.apply(
    explain_recommendation,
    axis=1
)

print("\nPOTENTIAL TRAINING CANDIDATES")
print("-" * 55)

print(
    shortage_details[
        [
            "skill_name",
            "potential_trainees"
        ]
    ].drop_duplicates().to_string(index=False)
)

# Save updated recommendations
output_file = PROCESSED_DIR / "workforce_recommendations.csv"

shortage_details.to_csv(output_file, index=False)

print("\nUpdated recommendations saved successfully!")
print("Output location:", output_file)

print("\nWEEKLY INTERNAL TALENT AVAILABILITY")
print("-" * 65)

print(
    shortage_details[
        [
            "demand_week",
            "skill_name",
            "gap_hours",
            "internal_employees",
            "internal_available_hours"
        ]
    ].head(15).to_string(index=False)
)




print("\nWORKFORCE RECOMMENDATIONS")
print("-" * 65)

print(
    shortage_details[
        [
            "skill_name",
            "demand_week",
            "gap_hours",
            "internal_available_hours",
            "remaining_gap",
            "recommendation"
        ]
    ].head(15).to_string(index=False)
)

# Save workforce recommendations

output_file = PROCESSED_DIR / "workforce_recommendations.csv"

shortage_details.to_csv(output_file, index=False)

print("\nRecommendations saved successfully!")
print("Total recommendations:", len(shortage_details))
print("Saved at:", output_file)

# Existing code that saves recommendations
# (Keep your existing code here)

# Display explainable recommendations

print("\nEXPLAINABLE WORKFORCE RECOMMENDATIONS")
print("=" * 70)

print(
    shortage_details[
        [
            "skill_name",
            "gap_hours",
            "internal_available_hours",
            "remaining_gap",
            "recommendation",
            "recommendation_reason"
        ]
    ].head(10).to_string(index=False)
)

