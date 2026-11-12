import pandas as pd
from pathlib import Path
import sys
from db_connection import get_connection

# Locate project folders
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import data_root

RAW_DIR = data_root(BASE_DIR) / "raw"

# Import order matters because some tables depend on others
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

# Connect to the database
connection = get_connection()

try:
    for filename in files:

        table_name = filename.replace(".csv", "")
        file_path = RAW_DIR / filename

        # Read CSV file
        df = pd.read_csv(file_path)

        # Insert records into SQLite
        df.to_sql(
            table_name,
            connection,
            if_exists="append",
            index=False
        )

        print(f"{table_name}: {len(df)} records imported")

    connection.commit()
    print("\nAll datasets imported successfully!")

except Exception as error:
    connection.rollback()
    print("\nImport failed:", error)

finally:
    connection.close()
