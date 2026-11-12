
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

employees_df = pd.read_csv(RAW_DIR / "employees.csv")
skills_df = pd.read_csv(RAW_DIR / "skills.csv")
roles_df = pd.read_csv(RAW_DIR / "roles.csv")
employees_df = employees_df.merge(roles_df[["role_id", "department"]], on="role_id", how="left")

skill_ids = skills_df["skill_id"].tolist()

employee_skills = []
record_number = 1

today = REFERENCE_DATE

baseline_path = BASELINE_RAW_DIR / "employee_skills.csv"
if os.environ.get("WORKFORCEIQ_BASELINE_DATA_ROOT") and baseline_path.exists():
    baseline = pd.read_csv(baseline_path)
    if not set(baseline["employee_id"]).issubset(set(employees_df["employee_id"])):
        raise ValueError("Regenerated employees do not preserve all baseline employee IDs.")
    legacy_skill_ids = set(pd.read_csv(BASELINE_RAW_DIR / "skills.csv")["skill_id"].astype(str))
    if not legacy_skill_ids.issubset(set(skills_df["skill_id"].astype(str))):
        raise ValueError("The regenerated taxonomy dropped an existing skill ID.")
    employee_skills.extend(baseline.to_dict("records"))
    next_number = int(baseline["employee_skill_id"].astype(str).str.extract(r"ES-(\d+)")[0].astype(int).max()) + 1
    added_skills = skills_df[~skills_df["skill_id"].astype(str).isin(legacy_skill_ids)]
    for _, skill in added_skills.iterrows():
        departments = CATEGORY_DEPARTMENTS.get(skill["skill_category"], set())
        candidates = employees_df[employees_df["department"].isin(departments)].sort_values("employee_id")
        if candidates.empty:
            raise ValueError(f"No eligible employees for skill {skill['skill_id']} ({skill['skill_name']}).")
        selected = candidates.sample(n=min(20, len(candidates)), random_state=SEED + int(skill["skill_id"][-6:]))
        for _, employee in selected.iterrows():
            last_verified = today - timedelta(days=random.randint(0, 700))
            expiry_date = None
            if random.random() < 0.15:
                expiry_date = (today + timedelta(days=random.randint(30, 730))).isoformat()
            employee_skills.append({
                "employee_skill_id": f"ES-{next_number:07d}",
                "employee_id": employee["employee_id"],
                "skill_id": skill["skill_id"],
                "proficiency_level": random.randint(1, 5),
                "last_verified_date": last_verified.isoformat(),
                "expiry_date": expiry_date,
            })
            next_number += 1
else:
    for _, employee in employees_df.iterrows():

        # Each employee gets 3 to 10 role-relevant skills.
        number_of_skills = random.randint(3, 10)

        applicable_categories = [
            category for category, departments in CATEGORY_DEPARTMENTS.items()
            if employee["department"] in departments
        ]
        eligible_ids = skills_df[skills_df["skill_category"].isin(applicable_categories)]["skill_id"].tolist()
        selected_skills = random.sample(eligible_ids, min(number_of_skills, len(eligible_ids)))

        for skill_id in selected_skills:

            last_verified = today - timedelta(days=random.randint(0, 700))

            # Some skills have expiry dates
            expiry_date = None

            if random.random() < 0.15:
                expiry_date = (today + timedelta(days=random.randint(30, 730))).isoformat()

            employee_skills.append({
                "employee_skill_id": f"ES-{record_number:07d}",
                "employee_id": employee["employee_id"],
                "skill_id": skill_id,
                "proficiency_level": random.randint(1, 5),
                "last_verified_date": last_verified.isoformat(),
                "expiry_date": expiry_date
            })

            record_number += 1

df = pd.DataFrame(employee_skills)

output_file = RAW_DIR / "employee_skills.csv"
df.to_csv(output_file, index=False)

print("Employee skills generated successfully!")
print("Total employee-skill records:", len(df))
print("Unique employees:", df["employee_id"].nunique())
print("Unique skills:", df["skill_id"].nunique())

print("\nProficiency distribution:")
print(df["proficiency_level"].value_counts().sort_index())

print("\nFirst five records:")
print(df.head())
