import pandas as pd
from pathlib import Path

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_DIR = BASE_DIR / "data" / "processed"
EXPORTS_DIR = BASE_DIR / "data" / "exports"

# Create exports folder if it does not exist
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

print("Scenario reporting module initialized successfully!")

from what_if_simulator import (
    load_data,
    compare_scenarios
)

def generate_scenario_report(data, demand_week, skill_id):

    # Compare all workforce strategies
    comparison = compare_scenarios(
        data,
        demand_week,
        skill_id
    )

    # Get the skill name
    skills = data["skills"]

    skill_details = skills[
    skills["skill_id"] == skill_id
    ]

    skill_name = (
    skill_details.iloc[0]["skill_name"]
    if not skill_details.empty
    else skill_id
)

    print("\nWORKFORCE SCENARIO REPORT")
    print("=" * 60)

    print("Demand Week:", demand_week)
    print("Skill Name:", skill_name)
    print("Skill ID:", skill_id)

    print("\nStrategy Comparison:")
    print(comparison.to_string(index=False))

    # Identify the most cost-effective strategy
    best_strategy = comparison.sort_values(
    by=["estimated_cost", "remaining_gap"]
    ).iloc[0]

    print("\nRECOMMENDED WORKFORCE STRATEGY")
    print("-" * 60)
    print("Strategy:", best_strategy["strategy"])
    print("Estimated Cost: ₹", best_strategy["estimated_cost"])
    print("Remaining Gap:", best_strategy["remaining_gap"], "hours")

    return comparison


def export_scenario_report(comparison, demand_week, skill_id):

    # Create comparison report filename
    filename = f"scenario_report_{demand_week}_{skill_id}.csv"

    file_path = EXPORTS_DIR / filename

    # Save all strategy comparisons
    comparison.to_csv(file_path, index=False)

    # Identify the best strategy
    best_strategy = comparison.sort_values(
        by=["estimated_cost", "remaining_gap"]
    ).iloc[0]

    # Create recommendation report
    recommendation = pd.DataFrame([{
        "demand_week": demand_week,
        "skill_id": skill_id,
        "recommended_strategy": best_strategy["strategy"],
        "estimated_cost": best_strategy["estimated_cost"],
        "remaining_gap": best_strategy["remaining_gap"],
        "hours_resolved": best_strategy["hours_resolved"]
    }])

    recommendation_file = EXPORTS_DIR / (
        f"recommendation_{demand_week}_{skill_id}.csv"
    )

    recommendation.to_csv(recommendation_file, index=False)

    print("\nReports exported successfully!")
    print("Comparison report:", file_path)
    print("Recommendation report:", recommendation_file)

    return file_path, recommendation_file

if __name__ == "__main__":

    print("=" * 60)
    print("WORKFORCEIQ SCENARIO REPORTING")
    print("=" * 60)

    # Load simulator datasets
    data = load_data()

    # Select a shortage scenario
    recommendations = data["recommendations"]
    shortage = recommendations.iloc[0]

    demand_week = shortage["demand_week"]
    skill_id = shortage["skill_id"]

    # Generate comparison report
    comparison = generate_scenario_report(
        data,
        demand_week,
        skill_id
    )

    # Export both reports
    export_scenario_report(
        comparison,
        demand_week,
        skill_id
    )
    