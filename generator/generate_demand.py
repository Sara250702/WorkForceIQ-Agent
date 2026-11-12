
import pandas as pd
import random
from pathlib import Path
from datetime import date, timedelta
import sys
import os

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import (
    HORIZON_END, HORIZON_START, SEED, baseline_data_root, data_root,
)
from generator.skill_role_mapping import CATEGORY_DEPARTMENTS, categories_for_department

random.seed(SEED)
RAW_DIR = data_root(BASE_DIR) / "raw"
BASELINE_RAW_DIR = baseline_data_root(BASE_DIR) / "raw"

# Read existing datasets
projects_df = pd.read_csv(RAW_DIR / "projects.csv")
roles_df = pd.read_csv(RAW_DIR / "roles.csv")
skills_df = pd.read_csv(RAW_DIR / "skills.csv")

current_week = HORIZON_START - timedelta(days=HORIZON_START.weekday())
last_week = HORIZON_END - timedelta(days=HORIZON_END.weekday())
number_of_weeks = ((last_week - current_week).days // 7) + 1
weekly_dates = [current_week + timedelta(weeks=i) for i in range(number_of_weeks)]

demand_records = []
demand_number = 1

for _, project in projects_df.iterrows():

    project_start = date.fromisoformat(project["start_date"])
    project_end = date.fromisoformat(project["end_date"])

    # Select roles from the project's department
    department_roles = roles_df[
        roles_df["department"] == project["department"]
    ]

    if department_roles.empty:
        department_roles = roles_df

    selected_roles = department_roles.sample(
        n=min(random.randint(1, 3), len(department_roles)),
        random_state=SEED + demand_number
    )

    for _, role in selected_roles.iterrows():

        applicable_categories = categories_for_department(
            role["department"], skills_df["skill_category"].drop_duplicates().tolist()
        )
        applicable_skills = skills_df[
            skills_df["skill_category"].isin(applicable_categories)
        ]
        if applicable_skills.empty:
            applicable_skills = skills_df
        skill = applicable_skills.sample(
            n=1, random_state=SEED + demand_number
        ).iloc[0]

        # Proposed demand has lower approval probability
        if project["approval_probability"] < 0.80:
            demand_type = "proposed"
        else:
            demand_type = "committed"

        for week_start in weekly_dates:

            week_end = week_start + timedelta(days=6)

            # Include only weeks overlapping the project
            if week_end < project_start or week_start > project_end:
                continue

            if week_start in (current_week, last_week):
                active_start = max(week_start, HORIZON_START, project_start)
                active_end = min(week_end, HORIZON_END, project_end)
                if active_end < active_start:
                    continue
                active_day_fraction = (active_end - active_start).days / 7 + 1 / 7
            else:
                active_day_fraction = 1

            required_employees = random.randint(1, 8)

            hours_per_employee = random.choice([20, 30, 35, 40])
            required_hours = float(required_employees * hours_per_employee)
            required_hours *= active_day_fraction

            demand_records.append({
                "demand_id": f"DEM-{demand_number:08d}",
                "project_id": project["project_id"],
                "role_id": role["role_id"],
                "skill_id": skill["skill_id"],
                "demand_week": week_start.isoformat(),
                "required_employees": required_employees,
                "required_hours": required_hours,
                "demand_type": demand_type
            })

            demand_number += 1

# Guarantee that every newly added skill has at least one demand record in an
# applicable department, rather than relying on chance sampling for coverage.
legacy_skill_ids_for_demand = set(
    pd.read_csv(BASELINE_RAW_DIR / "skills.csv")["skill_id"].astype(str)
) if os.environ.get("WORKFORCEIQ_BASELINE_DATA_ROOT") else set()
covered_new_skill_ids = {
    record["skill_id"] for record in demand_records
    if record["skill_id"] not in legacy_skill_ids_for_demand
}
for _, skill in skills_df[~skills_df["skill_id"].astype(str).isin(legacy_skill_ids_for_demand)].iterrows():
    if skill["skill_id"] in covered_new_skill_ids:
        continue
    departments = CATEGORY_DEPARTMENTS.get(skill["skill_category"], set())
    eligible_roles = roles_df[roles_df["department"].isin(departments)].sort_values("role_id")
    chosen = None
    for _, role in eligible_roles.iterrows():
        eligible_projects = projects_df[projects_df["department"] == role["department"]]
        for _, project in eligible_projects.sort_values("project_id").iterrows():
            project_start = date.fromisoformat(project["start_date"])
            project_end = date.fromisoformat(project["end_date"])
            active_weeks = []
            for week in weekly_dates:
                active_start = max(week, HORIZON_START, project_start)
                active_end = min(week + timedelta(days=6), HORIZON_END, project_end)
                if active_end >= active_start:
                    active_weeks.append(week)
            if active_weeks:
                chosen = (role, project, active_weeks[0])
                break
        if chosen:
            break
    if chosen is None:
        raise ValueError(f"No in-horizon project and role can demand skill {skill['skill_id']}.")
    role, project, week_start = chosen
    project_start = date.fromisoformat(project["start_date"])
    project_end = date.fromisoformat(project["end_date"])
    active_start = max(week_start, HORIZON_START, project_start)
    active_end = min(week_start + timedelta(days=6), HORIZON_END, project_end)
    active_day_fraction = ((active_end - active_start).days + 1) / 7
    required_employees = 1 + int(skill["skill_id"][-2:]) % 4
    hours_per_employee = [20, 30, 35, 40][int(skill["skill_id"][-1]) % 4]
    required_hours = float(required_employees * hours_per_employee)
    required_hours *= active_day_fraction
    demand_records.append({
        "demand_id": f"DEM-{demand_number:08d}",
        "project_id": project["project_id"],
        "role_id": role["role_id"],
        "skill_id": skill["skill_id"],
        "demand_week": week_start.isoformat(),
        "required_employees": required_employees,
        "required_hours": required_hours,
        "demand_type": "committed" if project["approval_probability"] >= 0.80 else "proposed",
    })
    demand_number += 1

# Preserve legacy skill associations from the approved baseline, then extend
# coverage for the new taxonomy and closing horizon period.
baseline_path = BASELINE_RAW_DIR / "demand_plans.csv"
if os.environ.get("WORKFORCEIQ_BASELINE_DATA_ROOT") and baseline_path.exists():
    baseline = pd.read_csv(baseline_path)
    baseline["required_hours"] = pd.to_numeric(
        baseline["required_hours"], errors="raise"
    ).astype("float64")
    baseline["demand_week"] = pd.to_datetime(baseline["demand_week"]).dt.date
    project_dates = projects_df.set_index("project_id")
    baseline = baseline[baseline["project_id"].isin(project_dates.index)].copy()
    baseline = baseline[baseline["demand_week"].isin(weekly_dates)].copy()
    closing_source_week = last_week - timedelta(days=7)
    closing_rows = baseline[
        pd.to_datetime(baseline["demand_week"]).dt.date == closing_source_week
    ].copy()
    if not closing_rows.empty:
        closing_rows = closing_rows[closing_rows.apply(
            lambda row: date.fromisoformat(project_dates.loc[row["project_id"], "start_date"]) <= HORIZON_END
            and date.fromisoformat(project_dates.loc[row["project_id"], "end_date"]) >= last_week,
            axis=1,
        )].copy()
        closing_rows["demand_week"] = last_week.isoformat()
        closing_rows["demand_id"] = ""
        for row_index, row in closing_rows.iterrows():
            project_start = date.fromisoformat(project_dates.loc[row["project_id"], "start_date"])
            project_end = date.fromisoformat(project_dates.loc[row["project_id"], "end_date"])
            active_start = max(last_week, HORIZON_START, project_start)
            active_end = min(last_week + timedelta(days=6), HORIZON_END, project_end)
            active_days = max(0, (active_end - active_start).days + 1)
            closing_rows.at[row_index, "required_hours"] *= active_days / 7
    baseline["demand_week"] = baseline["demand_week"].astype(str)
    # Scale demand hours for the two partial horizon periods.
    for row_index, row in baseline.iterrows():
        week = pd.to_datetime(row["demand_week"]).date()
        if week not in (current_week, last_week):
            continue
        project_start = date.fromisoformat(project_dates.loc[row["project_id"], "start_date"])
        project_end = date.fromisoformat(project_dates.loc[row["project_id"], "end_date"])
        active_start = max(week, HORIZON_START, project_start)
        active_end = min(week + timedelta(days=6), HORIZON_END, project_end)
        active_days = max(0, (active_end - active_start).days + 1)
        baseline.at[row_index, "required_hours"] *= active_days / 7
        if active_days == 0:
            baseline.at[row_index, "required_employees"] = 0
    generated = pd.DataFrame(demand_records)
    generated["required_hours"] = pd.to_numeric(
        generated["required_hours"], errors="raise"
    ).astype("float64")
    legacy_skill_ids = set(pd.read_csv(BASELINE_RAW_DIR / "skills.csv")["skill_id"].astype(str))
    generated = generated[~generated["skill_id"].astype(str).isin(legacy_skill_ids)]
    generated["demand_id"] = ""
    df = pd.concat([baseline, closing_rows, generated], ignore_index=True)
    demand_numbers = df["demand_id"].astype(str).str.extract(r"DEM-(\d+)")[0]
    next_demand_number = int(demand_numbers.dropna().astype(int).max()) + 1 if demand_numbers.notna().any() else 1
    missing_ids = df["demand_id"].isna() | (df["demand_id"].astype(str) == "")
    for row_index in df.index[missing_ids]:
        df.at[row_index, "demand_id"] = f"DEM-{next_demand_number:08d}"
        next_demand_number += 1
    df["demand_week"] = pd.to_datetime(df["demand_week"])
    df = df.sort_values(["demand_week", "project_id", "role_id", "skill_id", "demand_id"])
    df = df.reset_index(drop=True)
    df["demand_week"] = df["demand_week"].dt.strftime("%Y-%m-%d")
else:
    df = pd.DataFrame(demand_records)
    df["required_hours"] = pd.to_numeric(
        df["required_hours"], errors="raise"
    ).astype("float64")

# Save demand records
output_file = RAW_DIR / "demand_plans.csv"
df.to_csv(output_file, index=False)

print("Workforce demand generated successfully!")
print("Total demand records:", len(df))
print("Unique projects:", df["project_id"].nunique())

print("\nDemand type distribution:")
print(df["demand_type"].value_counts())

print("\nTotal required employees:", df["required_employees"].sum())
print("Total required hours:", df["required_hours"].sum())

print("\nFirst five demand records:")
print(df.head())
