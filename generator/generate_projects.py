
import pandas as pd
import random
from faker import Faker
from pathlib import Path
from datetime import date, timedelta
import sys

# Reproducible data
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, SEED, data_root

random.seed(SEED)
fake = Faker()
Faker.seed(SEED)

RAW_DIR = data_root(BASE_DIR) / "raw"

NUM_PROJECTS = 500

departments = [
    "Engineering",
    "Data & AI",
    "Management",
    "Human Resources",
    "IT Operations",
    "Design",
    "Quality Assurance"
]

project_statuses = [
    "planned",
    "active",
    "completed",
    "on_hold"
]

status_weights = [0.25, 0.45, 0.20, 0.10]

today = REFERENCE_DATE
projects = []

for i in range(1, NUM_PROJECTS + 1):

    start_date = today + timedelta(
        days=random.randint(-180, 180)
    )

    end_date = start_date + timedelta(
        days=random.randint(60, 540)
    )

    projects.append({
        "project_id": f"PRJ-2026-{i:06d}",
        "project_name": fake.catch_phrase(),
        "department": random.choice(departments),
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "project_status": random.choices(
            project_statuses,
            weights=status_weights
        )[0],
        "approval_probability": round(
            random.uniform(0.40, 1.00), 2
        )
    })

df = pd.DataFrame(projects)

output_file = RAW_DIR / "projects.csv"
df.to_csv(output_file, index=False)

print(f"Successfully generated {len(df)} projects!")
print("Unique project IDs:", df["project_id"].nunique())

print("\nProject status distribution:")
print(df["project_status"].value_counts())

print("\nDepartment distribution:")
print(df["department"].value_counts())

print("\nFirst five projects:")
print(df.head())
