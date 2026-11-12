
import pandas as pd
import random
from faker import Faker
from pathlib import Path
from datetime import datetime
import sys

# Reproducible synthetic data
# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, SEED, data_root

random.seed(SEED)
fake = Faker()
Faker.seed(SEED)
RAW_DIR = data_root(BASE_DIR) / "raw"

# Number of employees
NUM_EMPLOYEES = 5000

# Read available roles
roles_df = pd.read_csv(RAW_DIR / "roles.csv")

role_ids = roles_df["role_id"].tolist()

# Employment details
employment_types = ["Full-time", "Part-time", "Contract"]
employment_weights = [0.75, 0.15, 0.10]

statuses = ["active", "on_leave", "inactive"]
status_weights = [0.90, 0.06, 0.04]

employees = []

for i in range(1, NUM_EMPLOYEES + 1):

    role_id = random.choice(role_ids)

    employees.append({
        "employee_id": f"EMP-{i:06d}",
        "employee_name": fake.name(),
        "email": f"employee{i}@workforceiq.com",
        "role_id": role_id,
        "employment_type": random.choices(
            employment_types,
            weights=employment_weights
        )[0],
        "joining_date": fake.date_between(
            start_date=REFERENCE_DATE.replace(year=REFERENCE_DATE.year - 10),
            end_date=REFERENCE_DATE
        ).isoformat(),
        "status": random.choices(
            statuses,
            weights=status_weights
        )[0]
    })

# Create DataFrame
df = pd.DataFrame(employees)

# Save employee data
output_file = RAW_DIR / "employees.csv"
df.to_csv(output_file, index=False)

print(f"Successfully generated {len(df)} employees!")
print(f"Unique employee IDs: {df['employee_id'].nunique()}")
print(f"Unique emails: {df['email'].nunique()}")
print("\nEmployment type distribution:")
print(df["employment_type"].value_counts())
print("\nFirst five employees:")
print(df.head())
