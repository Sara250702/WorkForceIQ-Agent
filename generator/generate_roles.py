
import pandas as pd
from pathlib import Path

# Project directory
BASE_DIR = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

OUTPUT_DIR = data_root(BASE_DIR) / "raw"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Company job roles
roles = [
    ("Software Developer", "Engineering"),
    ("Senior Software Developer", "Engineering"),
    ("Data Scientist", "Data & AI"),
    ("Machine Learning Engineer", "Data & AI"),
    ("Data Analyst", "Data & AI"),
    ("AI Engineer", "Data & AI"),
    ("Project Manager", "Management"),
    ("Business Analyst", "Management"),
    ("HR Manager", "Human Resources"),
    ("Recruiter", "Human Resources"),
    ("DevOps Engineer", "IT Operations"),
    ("Cloud Engineer", "IT Operations"),
    ("Cybersecurity Analyst", "IT Operations"),
    ("UI/UX Designer", "Design"),
    ("QA Engineer", "Quality Assurance")
]

# Create records
data = []

for index, (role_name, department) in enumerate(roles, start=1):
    data.append({
        "role_id": f"ROLE-{index:06d}",
        "role_name": role_name,
        "department": department,
        "description": f"{role_name} in {department}"
    })

# Convert to DataFrame
df = pd.DataFrame(data)

# Save as CSV
output_file = OUTPUT_DIR / "roles.csv"
df.to_csv(output_file, index=False)

print(f"Successfully generated {len(df)} roles!")
print(f"Saved at: {output_file}")
print(df.head())
