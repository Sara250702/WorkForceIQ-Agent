
import pandas as pd
import random
from pathlib import Path
from datetime import date, timedelta
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import SEED, data_root

random.seed(SEED)
RAW_DIR = data_root(BASE_DIR) / "raw"

employees_df = pd.read_csv(RAW_DIR / "employees.csv")
projects_df = pd.read_csv(RAW_DIR / "projects.csv")
roles_df = pd.read_csv(RAW_DIR / "roles.csv")

# Keep only active employees
active_employees = employees_df[
    employees_df["status"] == "active"
]

# Add department information to employees
active_employees = active_employees.merge(
    roles_df[["role_id", "department"]],
    on="role_id",
    how="left"
)

allocation_records = []
allocation_number = 1

for _, project in projects_df.iterrows():

    # Find employees belonging to the project's department
    department_employees = active_employees[
        active_employees["department"] == project["department"]
    ]

    if department_employees.empty:
        continue

    # Select employees for this project
    selected_employees = department_employees.sample(
        n=min(random.randint(3, 8), len(department_employees)),
        random_state=SEED + allocation_number
    )

    project_start = date.fromisoformat(project["start_date"])
    project_end = date.fromisoformat(project["end_date"])

    for _, employee in selected_employees.iterrows():

        allocation_start = project_start

        allocation_end = min(
            project_end,
            project_start + timedelta(days=random.randint(30, 120))
        )

        allocated_hours = random.choice([10, 15, 20, 30, 40])

        allocation_records.append({
            "allocation_id": f"ALLOC-2026-{allocation_number:06d}",
            "employee_id": employee["employee_id"],
            "project_id": project["project_id"],
            "allocation_start": allocation_start.isoformat(),
            "allocation_end": allocation_end.isoformat(),
            "allocated_hours": allocated_hours,
            "allocation_status": "active"
        })

        allocation_number += 1

df = pd.DataFrame(allocation_records)

output_file = RAW_DIR / "allocations.csv"
df.to_csv(output_file, index=False)

print("Employee allocations generated successfully!")
print("Total allocation records:", len(df))
print("Unique allocation IDs:", df["allocation_id"].nunique())
print("Unique employees allocated:", df["employee_id"].nunique())
print("Unique projects allocated:", df["project_id"].nunique())
print("Total allocated hours:", df["allocated_hours"].sum())

print("\nFirst five allocation records:")
print(df.head())
