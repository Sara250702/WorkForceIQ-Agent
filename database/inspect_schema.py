import sqlite3
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "workforceiq.db"
RAW_DIR = BASE_DIR / "data" / "raw"

connection = sqlite3.connect(DB_PATH)

files = [
    "roles.csv",
    "skills.csv",
    "employees.csv",
    "employee_skills.csv",
    "projects.csv",
    "demand_plans.csv",
    "allocations.csv",
    "availability.csv",
    "training.csv",
    "gap_analysis.csv"
]

for filename in files:
    table_name = filename.replace(".csv", "")

    df = pd.read_csv(RAW_DIR / filename, nrows=0)

    columns = connection.execute(
        f"PRAGMA table_info({table_name})"
    ).fetchall()

    database_columns = [column[1] for column in columns]

    print(f"\n--- {table_name.upper()} ---")
    print("CSV columns:     ", df.columns.tolist())
    print("Database columns:", database_columns)

connection.close()