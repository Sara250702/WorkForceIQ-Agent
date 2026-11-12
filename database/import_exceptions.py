
import pandas as pd
from pathlib import Path
import sys
import os
from db_connection import get_connection

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE, data_root

PROCESSED_DIR = data_root(BASE_DIR) / "processed"

# Load exception report
exceptions = pd.read_csv(
    PROCESSED_DIR / "workforce_exceptions.csv"
)

# Map CSV columns to database columns
exceptions = exceptions.rename(
    columns={
        "exception_type": "issue_type",
        "employee_id": "affected_entity_id",
        "description": "actual_value"
    }
)

# Add expected values
exceptions["expected_value"] = None

# Keep existing default-import behavior; staged runs use the fixed reference date.
if os.environ.get("WORKFORCEIQ_DATA_ROOT"):
    exceptions["detected_at"] = f"{REFERENCE_DATE.isoformat()} 00:00:00"
else:
    exceptions["detected_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")

# Add resolution notes
exceptions["resolution_notes"] = None

# Select database columns in the correct order
exceptions = exceptions[
    [
        "exception_id",
        "issue_type",
        "affected_entity_id",
        "detected_at",
        "severity",
        "expected_value",
        "actual_value",
        "resolution_status",
        "resolution_notes"
    ]
]

# Import into SQLite
connection = get_connection()

try:
    exceptions.to_sql(
        "exceptions",
        connection,
        if_exists="append",
        index=False
    )

    connection.commit()

    print("Exception records imported successfully!")
    print("Total imported records:", len(exceptions))

except Exception as error:
    connection.rollback()
    print("Import failed:", error)

finally:
    connection.close()
