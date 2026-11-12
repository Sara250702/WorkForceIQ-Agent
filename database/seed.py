
from pathlib import Path
from db_connection import get_connection

# Locate the SQL schema file
BASE_DIR = Path(__file__).resolve().parent.parent
SCHEMA_PATH = BASE_DIR / "database" / "schema.sql"

# Read the schema
with open(SCHEMA_PATH, "r", encoding="utf-8") as file:
    schema = file.read()

# Create database tables
connection = get_connection()
connection.executescript(schema)

# Verify the tables
tables = connection.execute("""
    SELECT name
    FROM sqlite_master
    WHERE type = 'table'
    ORDER BY name
""").fetchall()

connection.close()

print("WorkforceIQ database created successfully!")
print("\nTables created:")

for table in tables:
    print("-", table[0])
