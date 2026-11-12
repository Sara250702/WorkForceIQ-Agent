
import pandas as pd
import random
from pathlib import Path
from datetime import date, timedelta
import sys
import os

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, SEED, baseline_data_root, data_root
from generator.skill_role_mapping import CATEGORY_DEPARTMENTS

random.seed(SEED)
RAW_DIR = data_root(BASE_DIR) / "raw"
BASELINE_RAW_DIR = baseline_data_root(BASE_DIR) / "raw"

# Load existing datasets
employees_df = pd.read_csv(RAW_DIR / "employees.csv")
skills_df = pd.read_csv(RAW_DIR / "skills.csv")
roles_df = pd.read_csv(RAW_DIR / "roles.csv")
employees_df = employees_df.merge(roles_df[["role_id", "department"]], on="role_id", how="left")

training_records = []
training_number = 1

today = REFERENCE_DATE

# Select employees for training
selected_employees = employees_df.sample(
    n=2000,
    random_state=SEED
)

baseline_path = BASELINE_RAW_DIR / "training.csv"
if os.environ.get("WORKFORCEIQ_BASELINE_DATA_ROOT") and baseline_path.exists():
    baseline = pd.read_csv(baseline_path)
    legacy_skill_ids = set(pd.read_csv(BASELINE_RAW_DIR / "skills.csv")["skill_id"].astype(str))
    training_records.extend(baseline.to_dict("records"))
    next_number = int(baseline["training_id"].astype(str).str.extract(r"TRN-\d+-(\d+)")[0].astype(int).max()) + 1
    eligible_employees = employees_df
    added_skills = skills_df[~skills_df["skill_id"].astype(str).isin(legacy_skill_ids)]
    for _, skill in added_skills.iterrows():
        departments = CATEGORY_DEPARTMENTS.get(skill["skill_category"], set())
        candidates = eligible_employees[eligible_employees["department"].isin(departments)].sort_values("employee_id")
        if candidates.empty:
            raise ValueError(f"No eligible training employees for {skill['skill_id']}.")
        selected = candidates.sample(n=min(5, len(candidates)), random_state=SEED + int(skill["skill_id"][-6:]))
        for _, employee in selected.iterrows():
            start_date = today - timedelta(days=random.randint(0, 180))
            training_duration = random.choice([15, 20, 30, 40, 60])
            completion_date = start_date + timedelta(days=random.randint(7, 60))
            if completion_date < today:
                training_status = "completed"
            else:
                training_status = "planned"
            training_records.append({
                "training_id": f"TRN-2026-{next_number:06d}",
                "employee_id": employee["employee_id"],
                "skill_id": skill["skill_id"],
                "training_start_date": start_date.isoformat(),
                "training_end_date": completion_date.isoformat(),
                "training_hours": training_duration,
                "training_status": training_status,
            })
            next_number += 1
else:
    for _, employee in selected_employees.iterrows():

        applicable_categories = [
            category for category, departments in CATEGORY_DEPARTMENTS.items()
            if employee.get("department") in departments
        ]
        candidates = skills_df[skills_df["skill_category"].isin(applicable_categories)]
        skill = candidates.sample(n=1, random_state=SEED + training_number).iloc[0]

        start_date = today - timedelta(days=random.randint(0, 180))

        training_duration = random.choice([15, 20, 30, 40, 60])
        completion_date = start_date + timedelta(days=random.randint(7, 60))

    # Determine training status
        if completion_date < today:
            training_status = random.choice(["completed", "completed", "in_progress"])
        else:
            training_status = random.choice(["in_progress", "planned"])

        training_records.append({
            "training_id": f"TRN-2026-{training_number:06d}",
            "employee_id": employee["employee_id"],
            "skill_id": skill["skill_id"],
            "training_start_date": start_date.isoformat(),
            "training_end_date": completion_date.isoformat(),
            "training_hours": training_duration,
            "training_status": training_status
        })

        training_number += 1

# Create DataFrame
df = pd.DataFrame(training_records)

# Save training records
output_file = RAW_DIR / "training.csv"
df.to_csv(output_file, index=False)

print("Employee training data generated successfully!")
print("Total training records:", len(df))
print("Unique employees trained:", df["employee_id"].nunique())
print("Total training hours:", df["training_hours"].sum())

print("\nTraining status distribution:")
print(df["training_status"].value_counts())

print("\nFirst five records:")
print(df.head())
