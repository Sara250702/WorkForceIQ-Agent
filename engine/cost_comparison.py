import pandas as pd
from pathlib import Path

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"

# Load workforce recommendations
# Estimated workforce costs (illustrative assumptions)

TRAINING_COST_PER_EMPLOYEE = 15000
HIRING_COST_PER_EMPLOYEE = 75000
WEEKLY_WORKING_HOURS = 40

print("\nCOST ASSUMPTIONS")
print("-" * 60)

print("Training cost per employee: ₹", TRAINING_COST_PER_EMPLOYEE)
print("External hiring cost per employee: ₹", HIRING_COST_PER_EMPLOYEE)
print("Weekly working hours per employee:", WEEKLY_WORKING_HOURS)
recommendations = pd.read_csv(
    PROCESSED_DIR / "workforce_recommendations.csv"
)

print("=" * 60)
print("WORKFORCEIQ HIRING VS TRAINING COST COMPARISON")
print("=" * 60)

print("\nRecommendations loaded successfully!")
print("Total recommendation records:", len(recommendations))

# Estimate employees required for each remaining shortage

import math

# Estimate employees required if internal reallocation is unavailable
recommendations["employees_required"] = (
    recommendations["gap_hours"] / WEEKLY_WORKING_HOURS
).apply(math.ceil)

recommendations["employees_required_after_reallocation"] = (
    recommendations["remaining_gap"] / WEEKLY_WORKING_HOURS
).apply(math.ceil)

print("\nEMPLOYEE REQUIREMENT ANALYSIS")
print("-" * 60)

print(
    recommendations[
        [
            "skill_name",
            "demand_week",
            "gap_hours",
            "employees_required"
        ]
    ].head(15).to_string(index=False)
)


# Calculate peak employee requirements for each skill

skill_cost_summary = recommendations.groupby(
    "skill_name",
    as_index=False
).agg(
    employees_before_reallocation=("employees_required", "max"),
    employees_after_reallocation=(
        "employees_required_after_reallocation",
        "max"
    )
)

# Calculate costs before internal reallocation
skill_cost_summary["training_cost_before"] = (
    skill_cost_summary["employees_before_reallocation"] *
    TRAINING_COST_PER_EMPLOYEE
)

skill_cost_summary["hiring_cost_before"] = (
    skill_cost_summary["employees_before_reallocation"] *
    HIRING_COST_PER_EMPLOYEE
)

# Calculate costs after internal reallocation
skill_cost_summary["training_cost_after"] = (
    skill_cost_summary["employees_after_reallocation"] *
    TRAINING_COST_PER_EMPLOYEE
)

skill_cost_summary["hiring_cost_after"] = (
    skill_cost_summary["employees_after_reallocation"] *
    HIRING_COST_PER_EMPLOYEE
)

# Calculate total costs
total_training_before = skill_cost_summary["training_cost_before"].sum()
total_hiring_before = skill_cost_summary["hiring_cost_before"].sum()

total_training_after = skill_cost_summary["training_cost_after"].sum()
total_hiring_after = skill_cost_summary["hiring_cost_after"].sum()

potential_savings = total_hiring_before - total_training_before


print("\nPEAK WORKFORCE REQUIREMENT BY SKILL")
print("=" * 60)

print(skill_cost_summary.to_string(index=False))

print("\nCOST COMPARISON BEFORE INTERNAL REALLOCATION")
print("=" * 60)

print(f"Estimated training cost: ₹{total_training_before:,.2f}")
print(f"Estimated hiring cost: ₹{total_hiring_before:,.2f}")
print(f"Potential savings through training: ₹{potential_savings:,.2f}")

print("\nCOST COMPARISON AFTER INTERNAL REALLOCATION")
print("=" * 60)

print(f"Estimated training cost: ₹{total_training_after:,.2f}")
print(f"Estimated hiring cost: ₹{total_hiring_after:,.2f}")

print("\nCOST-BASED RECOMMENDATION")
print("=" * 60)

if total_training_before < total_hiring_before:
    cost_recommendation = "Training is more cost-effective than external hiring."
elif total_hiring_before < total_training_before:
    cost_recommendation = "External hiring is more cost-effective than training."
else:
    cost_recommendation = "Both options have equal estimated costs."

print(cost_recommendation)

print("\nNOTE")
print("-" * 60)
print("These are illustrative estimates based on the project's cost assumptions.")
print("Actual costs may vary depending on employee skills, training duration,")
print("hiring requirements, and project conditions.")