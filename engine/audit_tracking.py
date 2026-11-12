import sqlite3
import pandas as pd
import uuid
from pathlib import Path
from datetime import datetime

# Project directories
BASE_DIR = Path(__file__).resolve().parent.parent
EXPORTS_DIR = BASE_DIR / "data" / "exports"

# Database connection
from database.db_connection import get_connection

# Create exports folder if missing
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)

def generate_audit_id():
    """Generate a unique audit log ID."""
    return f"AUD-{uuid.uuid4().hex[:10].upper()}"

def record_audit(
    entity_type,
    entity_id,
    action,
    old_value=None,
    new_value=None,
    changed_by="System"
):
    """Record an action in the audit_logs table."""

    connection = get_connection()

    try:
        cursor = connection.cursor()

        cursor.execute(
            """
            INSERT INTO audit_logs (
                audit_id,
                entity_type,
                entity_id,
                action,
                old_value,
                new_value,
                changed_by
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                generate_audit_id(),
                entity_type,
                entity_id,
                action,
                str(old_value) if old_value is not None else None,
                str(new_value) if new_value is not None else None,
                changed_by
            )
        )

        connection.commit()

        print("Audit record saved successfully!")

    except sqlite3.Error as error:
        connection.rollback()
        print("Audit recording failed:", error)

    finally:
        connection.close()
def get_audit_history(entity_type=None, entity_id=None):

    """Retrieve audit history from the database."""

    connection = get_connection()

    try:
        query = "SELECT * FROM audit_logs WHERE 1=1"
        parameters = []

        if entity_type:
            query += " AND entity_type = ?"
            parameters.append(entity_type)

        if entity_id:
            query += " AND entity_id = ?"
            parameters.append(entity_id)

        query += " ORDER BY changed_at DESC"

        history = pd.read_sql_query(
            query,
            connection,
            params=parameters
        )

        return history

    finally:
        connection.close()

def export_audit_history():

    """Export all audit records to a CSV file."""

    history = get_audit_history()

    filename = (
        f"audit_history_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    )

    file_path = EXPORTS_DIR / filename

    history.to_csv(file_path, index=False)

    print("\nAudit history exported successfully!")
    print("Total records:", len(history))
    print("Export location:", file_path)

    return file_path

if __name__ == "__main__":

    print("=" * 60)
    print("WORKFORCEIQ AUDIT TRACKING")
    print("=" * 60)

    # Record a sample workforce scenario
    record_audit(
        entity_type="scenario",
        entity_id="SCN-001",
        action="Scenario Created",
        old_value=None,
        new_value="Internal Reallocation",
        changed_by="System"
    )

    # Retrieve audit history
    history = get_audit_history()

    print("\nAUDIT HISTORY")
    print("-" * 60)
    print(history.to_string(index=False))

    # Export audit history
    export_audit_history()