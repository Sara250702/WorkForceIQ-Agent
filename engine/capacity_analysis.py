import pandas as pd
from pathlib import Path
import sys
from engine.decision_rules import get_utilization_status

# Locate project folders
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

DATA_DIR = data_root(BASE_DIR)
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Load datasets
employees = pd.read_csv(RAW_DIR / "employees.csv")
availability = pd.read_csv(RAW_DIR / "availability.csv")
allocations = pd.read_csv(RAW_DIR / "allocations.csv")

# Keep only active employees
employees = employees[
    employees["status"] == "active"
].copy()

# Add employee information to availability
capacity = availability.merge(
    employees[["employee_id", "employee_name",
               "employment_type", "role_id"]],
    on="employee_id",
    how="inner"
)

# Calculate weekly allocated hours
# An allocation is counted when its date range overlaps the week.
capacity["availability_date"] = pd.to_datetime(
    capacity["availability_date"]
)

allocations["allocation_start"] = pd.to_datetime(
    allocations["allocation_start"]
)

allocations["allocation_end"] = pd.to_datetime(
    allocations["allocation_end"]
)

# Filter active allocations
active_allocations = allocations[
    allocations["allocation_status"] == "active"
].copy()

# Calculate the end of each availability week
capacity["week_end"] = (
    capacity["availability_date"] +
    pd.Timedelta(days=6)
)

# Match employee availability records with their allocations
weekly = capacity[
    ["availability_id", "employee_id",
     "availability_date", "week_end"]
].merge(
    active_allocations[
        ["employee_id", "allocation_start",
         "allocation_end", "allocated_hours"]
    ],
    on="employee_id",
    how="left"
)

# Keep allocations overlapping each availability week
overlapping = weekly[
    (weekly["allocation_start"] <= weekly["week_end"]) &
    (weekly["allocation_end"] >= weekly["availability_date"])
]

# Calculate total allocated hours for each employee-week
weekly_totals = (
    overlapping.groupby("availability_id")["allocated_hours"]
    .sum()
)

# Attach allocated hours to the capacity dataset
capacity["allocated_hours"] = (
    capacity["availability_id"]
    .map(weekly_totals)
    .fillna(0)
)


# Calculate utilization
capacity["utilization_percentage"] = (
    capacity["allocated_hours"] /
    capacity["available_hours"].replace(0, pd.NA)
) * 100

capacity["utilization_percentage"] = (
    capacity["utilization_percentage"].fillna(0)
)

# Calculate remaining capacity
capacity["remaining_hours"] = (
    capacity["available_hours"] -
    capacity["allocated_hours"]
)



capacity["utilization_status"] = capacity.apply(
    get_utilization_status,
    axis=1
)

# Save results
output_file = PROCESSED_DIR / "capacity_analysis.csv"

capacity.to_csv(output_file, index=False)

print("=" * 50)
print("WORKFORCEIQ CAPACITY ANALYSIS ENGINE")
print("=" * 50)

print("\nTotal weekly employee records:", len(capacity))

print("\nTotal available hours:",
      capacity["available_hours"].sum())

print("Total allocated hours:",
      capacity["allocated_hours"].sum())

print("Total remaining hours:",
      capacity["remaining_hours"].sum())

print("\nUtilization status distribution:")
print(capacity["utilization_status"].value_counts())

print("\nFirst five records:")
print(capacity.head())

print("\nSaved at:", output_file)
