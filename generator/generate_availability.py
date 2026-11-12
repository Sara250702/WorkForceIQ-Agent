
import pandas as pd
import random
from pathlib import Path
from datetime import date, timedelta
import sys

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import HORIZON_END, HORIZON_START, SEED, data_root

random.seed(SEED)
RAW_DIR = data_root(BASE_DIR) / "raw"

# Load employee data
employees_df = pd.read_csv(RAW_DIR / "employees.csv")

# Generate weekly availability for every period overlapping the fixed horizon.
current_week = HORIZON_START - timedelta(days=HORIZON_START.weekday())
last_week = HORIZON_END - timedelta(days=HORIZON_END.weekday())
number_of_weeks = ((last_week - current_week).days // 7) + 1

availability_records = []
record_number = 1

for _, employee in employees_df.iterrows():

    # Set weekly working capacity
    if employee["employment_type"] == "Part-time":
        standard_hours = 20
    else:
        standard_hours = 40

    for week in range(number_of_weeks):

        week_start = current_week + timedelta(weeks=week)

        # Generate leave hours
        leave_hours = random.choices(
            [0, 4, 8, 16, 20],
            weights=[0.65, 0.10, 0.12, 0.08, 0.05]
        )[0]

        # Leave cannot exceed standard working hours
        leave_hours = min(leave_hours, standard_hours)

        available_hours = standard_hours - leave_hours

        availability_records.append({
            "availability_id": f"AVAIL-{record_number:08d}",
            "employee_id": employee["employee_id"],
            "availability_date": week_start.isoformat(),
            "standard_hours": standard_hours,
            "leave_hours": leave_hours,
            "available_hours": available_hours
        })

        record_number += 1

# Create DataFrame
df = pd.DataFrame(availability_records)

# Save dataset
output_file = RAW_DIR / "availability.csv"
df.to_csv(output_file, index=False)

print("Employee availability generated successfully!")
print("Total availability records:", len(df))
print("Unique employees:", df["employee_id"].nunique())
print("Total standard hours:", df["standard_hours"].sum())
print("Total leave hours:", df["leave_hours"].sum())
print("Total available hours:", df["available_hours"].sum())

print("\nFirst five records:")
print(df.head())
