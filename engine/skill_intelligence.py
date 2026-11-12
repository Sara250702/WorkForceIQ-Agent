import pandas as pd
from pathlib import Path
import sys
import os
from engine.decision_rules import get_skill_status

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, data_root

DATA_DIR = data_root(BASE_DIR)
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"

PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

# Load employee and skill datasets
employees = pd.read_csv(RAW_DIR / "employees.csv")
employee_skills = pd.read_csv(RAW_DIR / "employee_skills.csv")
skills = pd.read_csv(RAW_DIR / "skills.csv")

print("=" * 50)
print("WORKFORCEIQ SKILL INTELLIGENCE ENGINE")
print("=" * 50)

print("\nEmployees loaded:", len(employees))
print("Employee skill records loaded:", len(employee_skills))
print("Skills loaded:", len(skills))

print("\nEmployee skill columns:")
print(employee_skills.columns.tolist())
print("\nSkills dataset columns:")
print(skills.columns.tolist())

# Convert date columns into datetime format
employee_skills["last_verified_date"] = pd.to_datetime(
    employee_skills["last_verified_date"]
)

employee_skills["expiry_date"] = pd.to_datetime(
    employee_skills["expiry_date"],
    errors="coerce"
)

# Get today's date
today = (
    pd.Timestamp(REFERENCE_DATE)
    if os.environ.get("WORKFORCEIQ_DATA_ROOT")
    else pd.Timestamp.today().normalize()
)

# Calculate how old the skill verification is
employee_skills["days_since_verified"] = (
    today - employee_skills["last_verified_date"]
).dt.days

# Identify skill status


employee_skills["skill_status"] = employee_skills.apply(
    get_skill_status,
    axis=1
)

# Display skill status distribution
print("\nSkill Status Distribution:")
print(employee_skills["skill_status"].value_counts())

# Identify qualified employees
employee_skills["is_qualified"] = (
    (employee_skills["proficiency_level"] >= 3) &
    (employee_skills["skill_status"] == "Current")
)

print("\nQualified Skill Records:")
print(employee_skills["is_qualified"].value_counts())

# Keep only active employees
active_employees = employees[
    employees["status"] == "active"
].copy()

# Merge skill records with employee information
skill_intelligence = employee_skills.merge(
    active_employees[
        ["employee_id", "employee_name", "role_id", "employment_type"]
    ],
    on="employee_id",
    how="inner"
)

# Merge with skill names
skill_intelligence = skill_intelligence.merge(
    skills[["skill_id", "skill_name", "skill_category"]],
    on="skill_id",
    how="left"
)

print("\nSkill Intelligence Records:", len(skill_intelligence))

print("\nFirst five records:")
print(
    skill_intelligence[
        ["employee_name", "skill_name", "proficiency_level",
         "skill_status", "is_qualified", "employment_type"]
    ].head()
)
# Save skill intelligence dataset
output_file = PROCESSED_DIR / "skill_intelligence.csv"

skill_intelligence.to_csv(output_file, index=False)

print("\nSkill Intelligence dataset saved successfully!")
print("Total records saved:", len(skill_intelligence))
print("Output location:", output_file)
