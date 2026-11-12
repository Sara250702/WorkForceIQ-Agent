from db_connection import get_connection

connection = get_connection()

tables = [
    "roles",
    "skills",
    "employees",
    "employee_skills",
    "projects",
    "demand_plans",
    "allocations",
    "availability",
    "training",
    "gap_analysis"
]

print("WORKFORCEIQ DATABASE VERIFICATION")
print("-" * 45)

for table in tables:
    result = connection.execute(
        f"SELECT COUNT(*) FROM {table}"
    ).fetchone()

    print(f"{table:<20} {result[0]:>10} records")

# Check foreign key relationships
foreign_key_errors = connection.execute(
    "PRAGMA foreign_key_check"
).fetchall()

print("\nForeign Key Check:")

if not foreign_key_errors:
    print("All foreign key relationships are valid!")
else:
    print("Foreign key errors found:")
    print(foreign_key_errors)

connection.close()