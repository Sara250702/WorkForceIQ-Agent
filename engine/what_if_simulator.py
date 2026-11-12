
import pandas as pd
from pathlib import Path
import math
import sys

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

DATA_DIR = data_root(BASE_DIR)
PROCESSED_DIR = DATA_DIR / "processed"
RAW_DIR = DATA_DIR / "raw"


def get_data_root():
    """Resolve the configured data root when a simulation loads its inputs."""
    return data_root(BASE_DIR)

# Cost assumptions (illustrative)
TRAINING_COST_PER_EMPLOYEE = 15000
HIRING_COST_PER_EMPLOYEE = 75000
WEEKLY_WORKING_HOURS = 40


# Load datasets required for simulation
def load_data():

    selected_root = get_data_root()
    processed_dir = selected_root / "processed"
    raw_dir = selected_root / "raw"

    recommendations = pd.read_csv(
        processed_dir / "workforce_recommendations.csv"
    )

    talent = pd.read_csv(
        processed_dir / "talent_discovery.csv"
    )

    skills = pd.read_csv(
        processed_dir / "skill_intelligence.csv"
    )

    capacity = pd.read_csv(
        processed_dir / "capacity_analysis.csv"
    )

    training = pd.read_csv(
        raw_dir / "training.csv"
    )

    return {
        "recommendations": recommendations,
        "talent": talent,
        "skills": skills,
        "capacity": capacity,
        "training": training
    }

def simulate_internal_reallocation(data, demand_week, skill_id):

    recommendations = data["recommendations"]
    talent = data["talent"]

    # Find the original shortage for the selected week and skill
    shortage = recommendations[
        (recommendations["demand_week"] == demand_week)
        & (recommendations["skill_id"] == skill_id)
    ]

    if shortage.empty:
        print("No shortage found for the selected week and skill.")
        return None

    required_gap = float(shortage.iloc[0]["gap_hours"])

    # Find qualified employees with available skill capacity
    candidates = talent[
        (talent["availability_date"] == demand_week)
        & (talent["skill_id"] == skill_id)
        & (talent["is_qualified"] == True)
        & (talent["skill_available_hours"] > 0)
    ].copy()

    # Calculate how much capacity can be reallocated
    internal_capacity = candidates["skill_available_hours"].sum()

    # Do not allocate more hours than the original shortage
    allocated_hours = min(internal_capacity, required_gap)

    remaining_gap = max(0, required_gap - allocated_hours)

    # Calculate shortage resolution percentage
    resolved_percentage = (
        (allocated_hours / required_gap) * 100
        if required_gap > 0 else 100
    )

    return {
        "scenario": "Internal Reallocation",
        "demand_week": demand_week,
        "skill_id": skill_id,
        "original_gap_hours": round(required_gap, 2),
        "eligible_employees": candidates["employee_id"].nunique(),
        "available_internal_hours": round(internal_capacity, 2),
        "allocated_hours": round(allocated_hours, 2),
        "remaining_gap_hours": round(remaining_gap, 2),
        "shortage_resolved_percentage": round(resolved_percentage, 2)
    }


def find_training_candidates(data, demand_week, skill_id):

    skills = data["skills"]
    capacity = data["capacity"]
    training = data["training"]
    talent = data["talent"]

    # Training assumptions based on historical training data
    TRAINING_HOURS = 30
    TRAINING_DURATION_DAYS = 33

    demand_date = pd.to_datetime(demand_week)

    # Start training five weeks before the demand week
    training_start = demand_date - pd.Timedelta(days=35)

    training_end = training_start + pd.Timedelta(
        days=TRAINING_DURATION_DAYS
    )

    # Find employees with foundational knowledge
    candidates = skills[
        (skills["skill_id"] == skill_id)
        & (skills["proficiency_level"].isin([1, 2]))
        & (skills["skill_status"] == "Current")
    ].copy()

    candidates = candidates[
        ["employee_id", "proficiency_level"]
    ].drop_duplicates("employee_id")

    # Convert dates for comparison
    capacity = capacity.copy()
    capacity["availability_date"] = pd.to_datetime(
        capacity["availability_date"]
    )

    training = training.copy()
    training["training_start_date"] = pd.to_datetime(
        training["training_start_date"]
    )
    training["training_end_date"] = pd.to_datetime(
        training["training_end_date"]
    )

    # Get weekly capacity during the training period
    training_capacity = capacity[
        (capacity["availability_date"] >= training_start)
        & (capacity["availability_date"] <= training_end)
        & (capacity["remaining_hours"] > 0)
    ]

    training_capacity = (
        training_capacity.groupby("employee_id")["remaining_hours"]
        .sum()
        .reset_index()
    )

    training_capacity = training_capacity.rename(
    columns={
        "remaining_hours": "training_capacity_hours"
    }
)

    candidates = candidates.merge(
        training_capacity,
        on="employee_id",
        how="inner"
    )

    # Require enough capacity to complete the training
    candidates = candidates[
        candidates["training_capacity_hours"] >= TRAINING_HOURS
    ]

    # Exclude employees with overlapping training in the same skill
    active_training = training[
        (training["training_status"].isin(
            ["in_progress", "planned"]
        ))
        & (training["training_start_date"] <= training_end)
        & (training["training_end_date"] >= training_start)
    ]

    candidates = candidates[
        ~candidates["employee_id"].isin(
            active_training["employee_id"]
        )
    ]

    # Get capacity in the actual demand week
    target_capacity = capacity[
        capacity["availability_date"] == demand_date
    ][["employee_id", "remaining_hours"]]

    candidates = candidates.merge(
        target_capacity,
        on="employee_id",
        how="inner"
    )

    # Count existing qualified skills in the demand week
    qualified_counts = talent[
        talent["availability_date"] == demand_week
    ][["employee_id", "qualified_skill_count"]].drop_duplicates(
        "employee_id"
    )

    candidates = candidates.merge(
        qualified_counts,
        on="employee_id",
        how="left"
    )

    candidates["qualified_skill_count"] = (
        candidates["qualified_skill_count"].fillna(0)
    )

    # Estimate weekly capacity for the newly acquired skill
    candidates["estimated_skill_hours_after_training"] = (
        candidates["remaining_hours"]
        / (candidates["qualified_skill_count"] + 1)
    )

    return candidates


def simulate_employee_training(data, demand_week, skill_id):

    recommendations = data["recommendations"]

    shortage = recommendations[
        (recommendations["demand_week"] == demand_week)
        & (recommendations["skill_id"] == skill_id)
    ]

    if shortage.empty:
        print("No shortage found for the selected week and skill.")
        return None

    required_gap = float(shortage.iloc[0]["gap_hours"])

    candidates = find_training_candidates(
        data,
        demand_week,
        skill_id
    )

    candidates = candidates.sort_values(
        by="estimated_skill_hours_after_training",
        ascending=False
    ).copy()

    selected_employees = []
    training_capacity = 0

    for _, candidate in candidates.iterrows():

        if training_capacity >= required_gap:
            break

        employee_capacity = candidate[
            "estimated_skill_hours_after_training"
        ]

        selected_employees.append(candidate["employee_id"])
        training_capacity += employee_capacity

    allocated_hours = min(training_capacity, required_gap)

    remaining_gap = max(
        0,
        required_gap - allocated_hours
    )

    employees_trained = len(selected_employees)

    training_cost = (
        employees_trained * TRAINING_COST_PER_EMPLOYEE
    )

    resolved_percentage = (
        allocated_hours / required_gap * 100
        if required_gap > 0 else 100
    )

    return {
        "scenario": "Employee Training",
        "demand_week": demand_week,
        "skill_id": skill_id,
        "original_gap_hours": round(required_gap, 2),
        "eligible_training_candidates": len(candidates),
        "employees_selected_for_training": employees_trained,
        "estimated_training_capacity_hours": round(
            training_capacity, 2
        ),
        "productive_hours_after_training": round(
            allocated_hours, 2
        ),
        "remaining_gap_hours": round(remaining_gap, 2),
        "training_cost": training_cost,
        "shortage_resolved_percentage": round(
            resolved_percentage, 2
        )
    }

def simulate_external_hiring(data, demand_week, skill_id):

    recommendations = data["recommendations"]

    # Find the original shortage
    shortage = recommendations[
        (recommendations["demand_week"] == demand_week)
        & (recommendations["skill_id"] == skill_id)
    ]

    if shortage.empty:
        print("No shortage found for the selected week and skill.")
        return None

    required_gap = float(shortage.iloc[0]["gap_hours"])

    # Calculate required new employees
    employees_required = math.ceil(
        required_gap / WEEKLY_WORKING_HOURS
    )

    # Calculate total hiring capacity
    hiring_capacity = (
        employees_required * WEEKLY_WORKING_HOURS
    )

    # Calculate productive hours needed
    allocated_hours = min(
        hiring_capacity,
        required_gap
    )

    remaining_gap = max(
        0,
        required_gap - allocated_hours
    )

    # Calculate hiring cost
    hiring_cost = (
        employees_required * HIRING_COST_PER_EMPLOYEE
    )

    # Calculate shortage resolution percentage
    resolved_percentage = (
        allocated_hours / required_gap * 100
        if required_gap > 0 else 100
    )

    return {
        "scenario": "External Hiring",
        "demand_week": demand_week,
        "skill_id": skill_id,
        "original_gap_hours": round(required_gap, 2),
        "employees_required": employees_required,
        "hiring_capacity_hours": hiring_capacity,
        "productive_hours_needed": round(allocated_hours, 2),
        "remaining_gap_hours": round(remaining_gap, 2),
        "hiring_cost": hiring_cost,
        "shortage_resolved_percentage": round(
            resolved_percentage, 2
        )
    }


def simulate_combined_strategy(
    data,
    demand_week,
    skill_id,
    max_internal_reallocation_pct=50,
    max_training_budget=75000
):

    recommendations = data["recommendations"]
    talent = data["talent"]

    # Find original shortage
    shortage = recommendations[
        (recommendations["demand_week"] == demand_week)
        & (recommendations["skill_id"] == skill_id)
    ]

    if shortage.empty:
        print("No shortage found for the selected week and skill.")
        return None

    original_gap = float(shortage.iloc[0]["gap_hours"])
    remaining_gap = original_gap

    # STEP 1: Internal reallocation

    internal_candidates = talent[
        (talent["availability_date"] == demand_week)
        & (talent["skill_id"] == skill_id)
        & (talent["is_qualified"] == True)
        & (talent["skill_available_hours"] > 0)
    ].copy()

    internal_capacity = internal_candidates[
        "skill_available_hours"
    ].sum()

    max_internal_hours = (
        original_gap * max_internal_reallocation_pct / 100
    )

    internal_hours = min(
        internal_capacity,
        remaining_gap,
        max_internal_hours
    )

    remaining_gap -= internal_hours

    # STEP 2: Employee training

    training_candidates = find_training_candidates(
        data,
        demand_week,
        skill_id
    )

    training_candidates = training_candidates.sort_values(
        by="estimated_skill_hours_after_training",
        ascending=False
    )

    selected_training_employees = []
    training_capacity = 0

    for _, candidate in training_candidates.iterrows():

        if training_capacity >= remaining_gap:
            break

        if (
            len(selected_training_employees) + 1
        ) * TRAINING_COST_PER_EMPLOYEE > max_training_budget:
            break

        employee_capacity = candidate[
            "estimated_skill_hours_after_training"
        ]

        selected_training_employees.append(
            candidate["employee_id"]
        )

        training_capacity += employee_capacity

    training_hours = min(
        training_capacity,
        remaining_gap
    )

    remaining_gap -= training_hours

    training_cost = (
        len(selected_training_employees)
        * TRAINING_COST_PER_EMPLOYEE
    )

    # STEP 3: External hiring

    employees_hired = (
        math.ceil(remaining_gap / WEEKLY_WORKING_HOURS)
        if remaining_gap > 0 else 0
    )

    hiring_capacity = (
        employees_hired * WEEKLY_WORKING_HOURS
    )

    hiring_hours = min(
        hiring_capacity,
        remaining_gap
    )

    remaining_gap -= hiring_hours

    hiring_cost = (
        employees_hired * HIRING_COST_PER_EMPLOYEE
    )

    # FINAL SCENARIO CALCULATIONS

    total_cost = training_cost + hiring_cost

    total_resolved = (
        internal_hours + training_hours + hiring_hours
    )

    resolved_percentage = (
        total_resolved / original_gap * 100
        if original_gap > 0 else 100
    )

    return {
        "scenario": "Combined Workforce Strategy",
        "demand_week": demand_week,
        "skill_id": skill_id,
        "original_gap_hours": round(original_gap, 2),
        "internal_employees_available": internal_candidates[
            "employee_id"
        ].nunique(),
        "internal_hours_allocated": round(internal_hours, 2),
        "employees_selected_for_training": len(
            selected_training_employees
        ),
        "training_hours_contributed": round(training_hours, 2),
        "employees_hired": employees_hired,
        "hiring_hours_contributed": round(hiring_hours, 2),
        "remaining_gap_hours": round(max(0, remaining_gap), 2),
        "training_cost": training_cost,
        "hiring_cost": hiring_cost,
        "total_cost": total_cost,
        "shortage_resolved_percentage": round(
            resolved_percentage, 2
        )
    }


def compare_scenarios(data, demand_week, skill_id):

    internal = simulate_internal_reallocation(
        data, demand_week, skill_id
    )

    training = simulate_employee_training(
        data, demand_week, skill_id
    )

    hiring = simulate_external_hiring(
        data, demand_week, skill_id
    )

    combined = simulate_combined_strategy(
        data, demand_week, skill_id
    )

    comparison = pd.DataFrame([
        {
            "strategy": "Internal Reallocation",
            "hours_resolved": internal["allocated_hours"],
            "remaining_gap": internal["remaining_gap_hours"],
            "estimated_cost": 0
        },
        {
            "strategy": "Employee Training",
            "hours_resolved": training["productive_hours_after_training"],
            "remaining_gap": training["remaining_gap_hours"],
            "estimated_cost": training["training_cost"]
        },
        {
            "strategy": "External Hiring",
            "hours_resolved": hiring["productive_hours_needed"],
            "remaining_gap": hiring["remaining_gap_hours"],
            "estimated_cost": hiring["hiring_cost"]
        },
        {
            "strategy": "Combined Strategy",
            "hours_resolved": (
                combined["internal_hours_allocated"]
                + combined["training_hours_contributed"]
                + combined["hiring_hours_contributed"]
            ),
            "remaining_gap": combined["remaining_gap_hours"],
            "estimated_cost": combined["total_cost"]
        }
    ])

    comparison["estimated_cost"] = comparison[
        "estimated_cost"
    ].astype(int)

    return comparison





if __name__ == "__main__":

    data = load_data()

    print("=" * 60)
    print("WORKFORCEIQ WHAT-IF SIMULATOR")
    print("=" * 60)

    for dataset_name, dataset in data.items():
        print(
            f"{dataset_name}: {len(dataset)} records loaded"
        )

    print("\nAll simulator datasets loaded successfully!")

    # Test internal reallocation using the first shortage record
    first_shortage = data["recommendations"].iloc[0]

    result = simulate_internal_reallocation(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nINTERNAL REALLOCATION SCENARIO")
    print("-" * 60)

    if result:
        for key, value in result.items():
            print(f"{key}: {value}")

    
    
    # Test employee training candidate selection
    training_candidates = find_training_candidates(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nEMPLOYEE TRAINING CANDIDATES")
    print("-" * 60)

    print(
        "Eligible training candidates:",
        training_candidates["employee_id"].nunique()
    )

    print(
        "Total remaining hours in demand week:",
        round(training_candidates["remaining_hours"].sum(), 2)
    )

    print(
        "Total training-period capacity:",
        round(training_candidates["training_capacity_hours"].sum(), 2)
    )

    print("\nFirst five candidates:")

    print(
        training_candidates[
            [
                "employee_id",
                "proficiency_level",
                "training_capacity_hours",
                "remaining_hours",
                "estimated_skill_hours_after_training"
            ]
        ].head().to_string(index=False)
    )

    # Test employee training scenario
    training_result = simulate_employee_training(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nEMPLOYEE TRAINING SCENARIO")
    print("-" * 60)

    if training_result:
        for key, value in training_result.items():
            print(f"{key}: {value}")


    
    # Test external hiring scenario
    hiring_result = simulate_external_hiring(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nEXTERNAL HIRING SCENARIO")
    print("-" * 60)

    if hiring_result:
        for key, value in hiring_result.items():
            print(f"{key}: {value}")

        # Test combined workforce strategy
    combined_result = simulate_combined_strategy(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nCOMBINED WORKFORCE STRATEGY")
    print("-" * 60)

    if combined_result:
        for key, value in combined_result.items():
            print(f"{key}: {value}")

        # Compare all workforce strategies

    comparison = compare_scenarios(
        data,
        demand_week=first_shortage["demand_week"],
        skill_id=first_shortage["skill_id"]
    )

    print("\nWORKFORCE STRATEGY COMPARISON")
    print("=" * 65)

    print(comparison.to_string(index=False))

    best_strategy = comparison.loc[
        comparison["estimated_cost"].idxmin()
    ]

    print("\nMOST COST-EFFECTIVE STRATEGY")
    print("-" * 65)

    print("Strategy:", best_strategy["strategy"])
    print("Estimated Cost: ₹", best_strategy["estimated_cost"])
    print("Remaining Gap:", best_strategy["remaining_gap"])

    # Test multiple shortage scenarios

    print("\nMULTIPLE SHORTAGE SCENARIO TEST")
    print("=" * 65)

    for index, row in data["recommendations"].head(5).iterrows():

        print(
            f"\nTesting: {row['skill_name']} | "
            f"Week: {row['demand_week']}"
        )

        result = compare_scenarios(
            data,
            demand_week=row["demand_week"], 
            skill_id=row["skill_id"]
        )

        print(result.to_string(index=False))


