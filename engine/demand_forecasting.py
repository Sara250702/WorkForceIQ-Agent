import pandas as pd
from pathlib import Path
import sys

# Locate project folders
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

DATA_DIR = data_root(BASE_DIR)
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Load demand and project data
demand = pd.read_csv(RAW_DIR / "demand_plans.csv")
projects = pd.read_csv(RAW_DIR / "projects.csv")

# Get project approval probabilities
demand = demand.merge(
    projects[["project_id", "department", "approval_probability"]],
    on="project_id",
    how="left"
)

# Calculate expected demand
# Committed projects count at 100%
# Proposed projects are weighted by approval probability

demand["expected_hours"] = demand.apply(
    lambda row: (
        row["required_hours"]
        if row["demand_type"] == "committed"
        else row["required_hours"] * row["approval_probability"]
    ),
    axis=1
)

# Separate committed and proposed demand
demand["committed_hours"] = demand.apply(
    lambda row: (
        row["required_hours"]
        if row["demand_type"] == "committed"
        else 0
    ),
    axis=1
)

demand["proposed_hours"] = demand.apply(
    lambda row: (
        row["required_hours"]
        if row["demand_type"] == "proposed"
        else 0
    ),
    axis=1
)

# Group demand by week, department, role and skill
forecast = demand.groupby(
    ["demand_week", "department", "role_id", "skill_id"],
    as_index=False
).agg(
    committed_hours=("committed_hours", "sum"),
    proposed_hours=("proposed_hours", "sum"),
    expected_hours=("expected_hours", "sum")
)

# Save forecast results
output_file = PROCESSED_DIR / "demand_forecast.csv"

forecast.to_csv(output_file, index=False)

# Display results
print("=" * 50)
print("WORKFORCEIQ DEMAND FORECASTING ENGINE")
print("=" * 50)

print("\nForecast generated successfully!")

print("Total forecast records:", len(forecast))
print("Committed demand hours:", forecast["committed_hours"].sum())
print("Proposed demand hours:", forecast["proposed_hours"].sum())
print("Expected demand hours:", round(forecast["expected_hours"].sum(), 2))

print("\nFirst five forecast records:")
print(forecast.head())

print("\nSaved at:", output_file)
