
import pandas as pd
from pathlib import Path
from generator.config import data_root as configured_data_root


BASE_DIR = Path(__file__).resolve().parent.parent


def get_data_root():
    """Resolve the same configured data root used by the dashboard and engines."""
    return configured_data_root(BASE_DIR)


def analyze_skill_shortage(skill_name=None, demand_week=None, limit=5):

    """
    Analyze workforce shortages for a particular skill.

    Args:
        skill_name: Name of the skill to analyze.
        demand_week: Optional demand week (YYYY-MM-DD).

    Returns:
        Structured shortage analysis.
    """

    file_path = (
        get_data_root() / "processed" / "workforce_recommendations.csv"
    )

    if not file_path.exists():
        raise FileNotFoundError(
            "Workforce recommendations dataset not found."
        )

    # Load workforce recommendations; a zero-byte export is an empty dataset.
    try:
        data = pd.read_csv(file_path)
    except pd.errors.EmptyDataError:
        return {
            "status": "not_found",
            "message": "No workforce shortage records are available.",
            "total_skills": 0,
            "skills": [],
        }

    if data.empty:
        return {
            "status": "not_found",
            "message": "No workforce shortage records are available.",
            "total_skills": 0,
            "skills": [],
        }

    # Organization-wide mode ranks all skills by cumulative unmet demand.
    if skill_name is None or not str(skill_name).strip():
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            return {"status": "error", "message": "limit must be a positive integer."}
        required = {"skill_name", "skill_id", "demand_week", "remaining_gap"}
        missing_columns = sorted(required.difference(data.columns))
        if missing_columns:
            return {
                "status": "error",
                "message": "Workforce shortage data is missing required fields.",
                "missing_fields": missing_columns,
            }

        matching_data = data.copy()
        if demand_week is not None:
            matching_data = matching_data[
                matching_data["demand_week"].astype(str) == str(demand_week)
            ]
        matching_data["skill_name"] = matching_data["skill_name"].fillna("").astype(str).str.strip()
        matching_data["skill_id"] = matching_data["skill_id"].fillna("").astype(str).str.strip()
        matching_data["_remaining_gap"] = pd.to_numeric(
            matching_data["remaining_gap"], errors="coerce"
        )
        valid = matching_data[
            matching_data["skill_name"].ne("")
            & matching_data["skill_id"].ne("")
            & matching_data["_remaining_gap"].notna()
            & matching_data["demand_week"].notna()
        ].copy()
        if valid.empty:
            return {
                "status": "not_found",
                "message": "No valid workforce shortage records are available for the selected reporting period.",
                "total_skills": 0,
                "skills": [],
            }

        period_start = valid["demand_week"].astype(str).min()
        period_end = valid["demand_week"].astype(str).max()
        grouped = valid.groupby(["skill_id", "skill_name"], as_index=False).agg(
            cumulative_remaining_gap=("_remaining_gap", "sum"),
            weeks_included=("demand_week", "nunique"),
        )
        grouped["cumulative_remaining_gap"] = grouped["cumulative_remaining_gap"].round(2)
        grouped = grouped.sort_values(
            ["cumulative_remaining_gap", "skill_name", "skill_id"],
            ascending=[False, True, True],
            kind="stable",
        )

        ranked = []
        for row in grouped.head(limit).itertuples(index=False):
            weekly = valid[
                (valid["skill_id"] == row.skill_id)
                & (valid["skill_name"] == row.skill_name)
            ][["demand_week", "_remaining_gap"]].copy()
            weekly = weekly.groupby("demand_week", as_index=False)["_remaining_gap"].sum()
            weekly = weekly.sort_values(
                ["_remaining_gap", "demand_week"], ascending=[False, True], kind="stable"
            ).head(5)
            ranked.append({
                "skill_id": str(row.skill_id),
                "skill_name": str(row.skill_name),
                "cumulative_remaining_gap_hours": float(row.cumulative_remaining_gap),
                "weeks_included": int(row.weeks_included),
                "weekly_details": [
                    {"demand_week": str(week), "remaining_gap_hours": round(float(hours), 2)}
                    for week, hours in weekly[["demand_week", "_remaining_gap"]].itertuples(index=False, name=None)
                ],
            })
        return {
            "status": "success",
            "analysis_scope": "organization_wide",
            "ranking_method": "sum of weekly remaining_gap hours",
            "reporting_period": {
                "start_week": period_start,
                "end_week": period_end,
                "weeks_included": int(valid["demand_week"].nunique()),
            },
            "total_skills": int(len(grouped)),
            "returned_skills": len(ranked),
            "skills": ranked,
        }

    # Preserve the original single-skill behavior.
    matching_data = data[
        data["skill_name"].astype(str).str.strip().str.casefold()
        == str(skill_name).strip().casefold()
    ].copy()

    # Filter by demand week if provided
    if demand_week is not None:

        matching_data = matching_data[
            matching_data["demand_week"].astype(str)
            == demand_week
        ]

    if matching_data.empty:

        return {
            "status": "not_found",
            "message": (
                f"No workforce shortage records found "
                f"for skill: {skill_name}"
            )
        }

    # Sort results chronologically
    matching_data = matching_data.sort_values(
        "demand_week"
    )

    records = []

    for _, row in matching_data.iterrows():

        records.append({
            "demand_week": str(row["demand_week"]),
            "skill_name": str(row["skill_name"]),
            "skill_id": str(row["skill_id"]),
            "gap_hours": round(float(row["gap_hours"]), 2),
            "internal_employees": int(
                row["internal_employees"]
            ),
            "internal_available_hours": round(
                float(row["internal_available_hours"]), 2
            ),
            "remaining_gap": round(
                float(row["remaining_gap"]), 2
            ),
            "potential_trainees": int(
                row["potential_trainees"]
            ),
            "recommendation": str(row["recommendation"])
        })

    return {
        "status": "success",
        "skill_name": skill_name,
        "total_periods": len(records),
        "records": records
    }



def find_internal_talent(
    skill_name,
    availability_date=None,
    min_proficiency=3,
    limit=20
):

    """
    Find qualified internal employees for a particular skill.
    """

    file_path = get_data_root() / "processed" / "talent_discovery.csv"
    skill_master_path = get_data_root() / "raw" / "skills.csv"

    if not file_path.exists():
        raise FileNotFoundError(
            "Talent discovery dataset not found."
        )

    if skill_master_path.exists():
        skill_master = pd.read_csv(skill_master_path, usecols=["skill_id", "skill_name"])
        exact_matches = skill_master[
            skill_master["skill_name"].astype(str).str.strip().str.casefold()
            == str(skill_name).strip().casefold()
        ]
        if exact_matches.empty:
            return {"status": "unknown_skills", "unknown_skills": [str(skill_name)], "employees": []}
        if exact_matches["skill_id"].nunique() > 1:
            return {"status": "ambiguous_skills", "ambiguous_skills": [str(skill_name)], "employees": []}

    data = pd.read_csv(file_path)

    # Match the requested skill
    matching_data = data[
        data["skill_name"].astype(str).str.strip().str.casefold()
        == skill_name.strip().casefold()
    ].copy()

    # Filter qualified and current employees
    matching_data = matching_data[
        (matching_data["is_qualified"] == True)
        & (matching_data["skill_status"] == "Current")
        & (matching_data["proficiency_level"] >= min_proficiency)
        & (matching_data["skill_available_hours"] > 0)
    ]

    # Filter by availability week
    if availability_date is not None:

        matching_data = matching_data[
            matching_data["availability_date"].astype(str)
            == availability_date
        ]

    if matching_data.empty:

        return {
            "status": "not_found",
            "message": (
                f"No qualified internal talent found for {skill_name}."
            )
        }

    # Keep the best weekly record for each employee
    matching_data = matching_data.sort_values(
        by=["proficiency_level", "skill_available_hours"],
        ascending=False
    )

    matching_data = matching_data.drop_duplicates(
        subset="employee_id"
    )

    total_employees = len(matching_data)

    # Apply result limit
    matching_data = matching_data.head(limit)

    employees = []

    for _, row in matching_data.iterrows():

        employees.append({
            "employee_id": str(row["employee_id"]),
            "employee_name": str(row["employee_name"]),
            "role_id": str(row["role_id"]),
            "employment_type": str(row["employment_type"]),
            "skill_name": str(row["skill_name"]),
            "proficiency_level": int(row["proficiency_level"]),
            "availability_date": str(row["availability_date"]),
            "available_hours": round(
                float(row["available_hours"]), 2
            ),
            "estimated_skill_hours": round(
                float(row["skill_available_hours"]), 2
            )
        })
        if "allocated_hours" in row.index and pd.notna(row["allocated_hours"]):
            employees[-1]["allocated_hours"] = round(float(row["allocated_hours"]), 2)
        if "remaining_hours" in row.index and pd.notna(row["remaining_hours"]):
            employees[-1]["remaining_hours"] = round(float(row["remaining_hours"]), 2)

    return {
        "status": "success",
        "skill_name": skill_name,
        "availability_date": availability_date,
        "total_qualified_employees": total_employees,
        "returned_employees": len(employees),
        "employees": employees
    }


def find_employees_by_skills(
    skill_names=None,
    match_mode="all",
    minimum_skill_count=None,
    limit=50,
    exclude_skill_names=None,
    proficiency_operator=None,
    proficiency_value=None,
    proficiency_min=None,
    proficiency_max=None,
    sort_by="employee_id",
    sort_order="asc",
    availability_date=None,
    minimum_skill_available_hours=None,
    minimum_remaining_hours=None,
    count_only=False,
):
    """Query all active employees' current, qualified skill records.

    Named skills use ALL semantics by default. With no skill names and no
    minimum count, the query defaults to employees with at least two distinct
    current, qualified skills. Any result limit is applied only after the full
    employee set has been grouped and matched.
    """
    root = get_data_root()
    employees = pd.read_csv(
        root / "raw" / "employees.csv",
        usecols=["employee_id", "employee_name", "role_id", "employment_type", "status"],
        dtype={"employee_id": str},
    )
    if count_only:
        active_count = int(
            (employees["status"].fillna("").astype(str).str.casefold() == "active").sum()
        )
        return {
            "status": "success",
            "query_type": "employee_count",
            "total_employee_count": active_count,
            "employees": [],
        }

    skills = pd.read_csv(root / "raw" / "skills.csv", usecols=["skill_id", "skill_name"])
    intelligence = pd.read_csv(
        root / "processed" / "skill_intelligence.csv",
        usecols=[
            "employee_id", "skill_id", "proficiency_level", "skill_status", "is_qualified"
        ],
        dtype={"employee_id": str, "skill_id": str},
    )

    def normalize_names(values, field_name):
        if isinstance(values, str):
            values = [values]
        if values is not None and not isinstance(values, (list, tuple)):
            return None, f"{field_name} must be a list of skill names."
        normalized = []
        for value in values or []:
            if not isinstance(value, str) or not value.strip():
                return None, f"Each {field_name} entry must be non-empty text."
            if value.strip().casefold() not in {name.casefold() for name in normalized}:
                normalized.append(value.strip())
        return normalized, None

    requested_names, error = normalize_names(skill_names, "skill_names")
    if error:
        return {"status": "error", "message": error}
    excluded_names, error = normalize_names(exclude_skill_names, "exclude_skill_names")
    if error:
        return {"status": "error", "message": error}

    mode = str(match_mode or "all").strip().casefold()
    if mode not in {"all", "any"}:
        return {"status": "error", "message": "match_mode must be 'all' or 'any'."}

    if minimum_skill_count is None and not requested_names:
        minimum_skill_count = 2
    if minimum_skill_count is not None and (
        isinstance(minimum_skill_count, bool)
        or not isinstance(minimum_skill_count, int)
        or minimum_skill_count < 1
    ):
        return {"status": "error", "message": "minimum_skill_count must be a positive integer."}
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {"status": "error", "message": "limit must be a positive integer."}

    sort_by = str(sort_by or "employee_id").casefold()
    sort_order = str(sort_order or "asc").casefold()
    if sort_by not in {"employee_id", "proficiency"} or sort_order not in {"asc", "desc"}:
        return {"status": "error", "message": "sort_by must be employee_id or proficiency and sort_order must be asc or desc."}

    # Convert filter requests into an explicit comparison without guessing aliases.
    if proficiency_operator is None:
        if proficiency_value is not None:
            proficiency_operator = "gte"
        elif proficiency_min is not None and proficiency_max is not None:
            proficiency_operator = "range"
        elif proficiency_min is not None:
            proficiency_operator, proficiency_value = "gte", proficiency_min
        elif proficiency_max is not None:
            proficiency_operator, proficiency_value = "lte", proficiency_max
    if proficiency_operator is not None:
        proficiency_operator = str(proficiency_operator).casefold()
        if proficiency_operator not in {"gt", "gte", "lt", "lte", "range"}:
            return {"status": "error", "message": "Unsupported proficiency comparison."}
        if proficiency_operator == "range":
            if proficiency_min is None or proficiency_max is None or proficiency_min > proficiency_max or proficiency_value is not None:
                return {"status": "error", "message": "A proficiency range requires valid proficiency_min and proficiency_max values."}
        elif proficiency_value is None or proficiency_min is not None or proficiency_max is not None:
            return {"status": "error", "message": "A proficiency comparison requires proficiency_value only."}
    elif proficiency_min is not None or proficiency_max is not None or proficiency_value is not None:
        return {"status": "error", "message": "Invalid proficiency filter."}

    for field_name, value in (
        ("minimum_skill_available_hours", minimum_skill_available_hours),
        ("minimum_remaining_hours", minimum_remaining_hours),
    ):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0):
            return {"status": "error", "message": f"{field_name} must be a non-negative number."}
    if (minimum_skill_available_hours is not None or minimum_remaining_hours is not None) and not availability_date:
        return {
            "status": "date_required",
            "message": "Weekly capacity filters require an availability_date in YYYY-MM-DD format.",
        }

    skills = skills.copy()
    skills["skill_id"] = skills["skill_id"].astype(str).str.strip()
    skills["skill_name"] = skills["skill_name"].fillna("").astype(str).str.strip()
    skills["_normalized_name"] = skills["skill_name"].str.casefold()
    name_to_ids = skills.groupby("_normalized_name")["skill_id"].apply(list).to_dict()
    canonical_by_id = dict(zip(skills["skill_id"], skills["skill_name"]))
    def resolve_names(names):
        resolved = []
        unknown = []
        ambiguous = []
        for name in names:
            matches = name_to_ids.get(name.casefold(), [])
            if not matches:
                unknown.append(name)
            elif len(matches) > 1:
                ambiguous.append(name)
            else:
                resolved.append(matches[0])
        return resolved, unknown, ambiguous

    resolved_ids, unknown_skills, ambiguous_skills = resolve_names(requested_names)
    excluded_ids, unknown_exclusions, ambiguous_exclusions = resolve_names(excluded_names)
    if unknown_exclusions:
        return {"status": "unknown_skills", "unknown_skills": unknown_exclusions,
                "total_matches": 0, "returned_employees": 0, "employees": []}
    if ambiguous_exclusions:
        return {"status": "ambiguous_skills", "ambiguous_skills": ambiguous_exclusions,
                "total_matches": 0, "returned_employees": 0, "employees": []}
    if unknown_skills:
        return {
            "status": "unknown_skills",
            "message": "Some requested skills are not in the workforce skill master.",
            "unknown_skills": unknown_skills,
            "total_matches": 0,
            "returned_employees": 0,
            "employees": [],
        }
    if ambiguous_skills:
        return {
            "status": "ambiguous_skills",
            "message": "Some skill names match multiple workforce skill IDs.",
            "ambiguous_skills": ambiguous_skills,
            "total_matches": 0,
            "returned_employees": 0,
            "employees": [],
        }

    active = employees[
        employees["status"].fillna("").astype(str).str.strip().str.casefold() == "active"
    ].copy()
    active["employee_id"] = active["employee_id"].fillna("").astype(str).str.strip()
    active = active[active["employee_id"] != ""]
    intelligence["employee_id"] = intelligence["employee_id"].fillna("").astype(str).str.strip()
    intelligence["skill_id"] = intelligence["skill_id"].fillna("").astype(str).str.strip()
    intelligence["skill_status"] = intelligence["skill_status"].fillna("").astype(str).str.strip()
    intelligence["is_qualified"] = (
        intelligence["is_qualified"].astype(str).str.strip().str.casefold()
        .isin({"true", "1", "yes"})
    )
    intelligence["proficiency_level"] = pd.to_numeric(
        intelligence["proficiency_level"], errors="coerce"
    )
    current_qualified = intelligence[
        intelligence["employee_id"].isin(active["employee_id"])
        & intelligence["skill_id"].isin(canonical_by_id)
        & intelligence["skill_status"].str.casefold().eq("current")
        & intelligence["is_qualified"]
    ].copy()
    current_qualified["skill_name"] = current_qualified["skill_id"].map(canonical_by_id)
    current_qualified = current_qualified.sort_values(
        ["proficiency_level", "skill_id"], ascending=[False, True]
    ).drop_duplicates(["employee_id", "skill_id"], keep="first")

    # Exclusions apply to an employee if they hold any excluded current,
    # qualified skill, regardless of the requested proficiency threshold.
    excluded_employees = set(current_qualified.loc[
        current_qualified["skill_id"].isin(excluded_ids), "employee_id"
    ])
    candidate_skills = current_qualified[
        ~current_qualified["employee_id"].isin(excluded_employees)
        & ~current_qualified["skill_id"].isin(excluded_ids)
    ].copy()
    if proficiency_operator:
        levels = candidate_skills["proficiency_level"]
        if proficiency_operator == "gt":
            mask = levels > proficiency_value
        elif proficiency_operator == "gte":
            mask = levels >= proficiency_value
        elif proficiency_operator == "lt":
            mask = levels < proficiency_value
        elif proficiency_operator == "lte":
            mask = levels <= proficiency_value
        else:
            mask = levels.between(proficiency_min, proficiency_max, inclusive="both")
        candidate_skills = candidate_skills[mask].copy()

    availability_by_key = {}
    capacity_by_employee = {}
    if availability_date:
        talent_path = root / "processed" / "talent_discovery.csv"
        if not talent_path.exists():
            return {"status": "error", "message": "Weekly talent availability data is unavailable."}
        talent = pd.read_csv(talent_path, usecols=[
            "employee_id", "skill_id", "availability_date", "available_hours",
            "allocated_hours", "remaining_hours", "skill_available_hours",
        ], dtype={"employee_id": str, "skill_id": str})
        talent["employee_id"] = talent["employee_id"].fillna("").astype(str).str.strip()
        talent["skill_id"] = talent["skill_id"].fillna("").astype(str).str.strip()
        talent["availability_date"] = talent["availability_date"].astype(str)
        talent = talent[talent["availability_date"] == str(availability_date)].copy()
        for row in talent.drop_duplicates(["employee_id", "skill_id"]).itertuples(index=False):
            values = {
                "available_hours": pd.to_numeric(row.available_hours, errors="coerce"),
                "allocated_hours": pd.to_numeric(row.allocated_hours, errors="coerce"),
                "remaining_hours": pd.to_numeric(row.remaining_hours, errors="coerce"),
                "skill_available_hours": pd.to_numeric(row.skill_available_hours, errors="coerce"),
            }
            availability_by_key[(row.employee_id, row.skill_id)] = values
            capacity_by_employee.setdefault(row.employee_id, values)

    employee_info = active.set_index("employee_id").to_dict("index")
    matches = []
    for employee_id, group in candidate_skills.groupby("employee_id", sort=True):
        skill_ids = set(group["skill_id"])
        if resolved_ids:
            requested_set = set(resolved_ids)
            matches_named = (
                requested_set.issubset(skill_ids)
                if mode == "all"
                else bool(requested_set.intersection(skill_ids))
            )
            if not matches_named:
                continue
        if minimum_skill_count is not None and len(skill_ids) < minimum_skill_count:
            continue

        shown = group[group["skill_id"].isin(resolved_ids)] if resolved_ids else group
        if mode == "any" and resolved_ids:
            shown = group[group["skill_id"].isin(resolved_ids)]
        if availability_date:
            available_ids = {
                skill_id for skill_id in shown["skill_id"]
                if (employee_id, skill_id) in availability_by_key
                and (availability_by_key[(employee_id, skill_id)].get("skill_available_hours") or 0) > 0
                and (minimum_skill_available_hours is None
                     or (availability_by_key[(employee_id, skill_id)].get("skill_available_hours") or 0) >= minimum_skill_available_hours)
            }
            if resolved_ids and mode == "all" and not set(resolved_ids).issubset(available_ids):
                continue
            if resolved_ids and mode == "any" and not set(resolved_ids).intersection(available_ids):
                continue
            if not resolved_ids:
                shown = shown[shown["skill_id"].isin(available_ids)]
                if minimum_skill_count is not None and shown["skill_id"].nunique() < minimum_skill_count:
                    continue
            capacity = capacity_by_employee.get(employee_id, {})
            if minimum_remaining_hours is not None and (capacity.get("remaining_hours") is None or capacity.get("remaining_hours") < minimum_remaining_hours):
                continue
        info = employee_info[employee_id]
        proficiency_average = float(shown["proficiency_level"].mean()) if not shown.empty else 0.0
        matches.append({
            "employee_id": str(employee_id),
            "employee_name": str(info.get("employee_name") or ""),
            "role_id": str(info.get("role_id") or ""),
            "employment_type": str(info.get("employment_type") or ""),
            "skill_count": int(len(skill_ids)),
            "sort_proficiency_average": round(proficiency_average, 2),
            "availability_date": str(availability_date) if availability_date else None,
            "weekly_capacity": {
                key: (None if pd.isna(value) else round(float(value), 2))
                for key, value in capacity_by_employee.get(employee_id, {}).items()
                if key != "skill_available_hours"
            } if availability_date else None,
            "skills": [
                {
                    "skill_id": str(row.skill_id),
                    "skill_name": str(row.skill_name),
                    "proficiency_level": int(row.proficiency_level),
                    "skill_status": "Current",
                    "is_qualified": True,
                    **({"skill_available_hours": round(float(availability_by_key[(employee_id, str(row.skill_id))]["skill_available_hours"]), 2)}
                       if (employee_id, str(row.skill_id)) in availability_by_key else {}),
                }
                for row in shown.sort_values("skill_name").itertuples(index=False)
            ],
        })

    matches.sort(
        key=(lambda item: (item["sort_proficiency_average"], item["employee_id"])),
        reverse=sort_order == "desc" if sort_by == "proficiency" else False,
    )
    if sort_by == "employee_id":
        matches.sort(key=lambda item: item["employee_id"], reverse=sort_order == "desc")
    total_matches = len(matches)
    if not matches:
        return {
            "status": "not_found",
            "message": "No active employees match the requested current, qualified skill criteria.",
            "requested_skills": [canonical_by_id[skill_id] for skill_id in resolved_ids],
            "match_mode": mode,
            "minimum_skill_count": minimum_skill_count,
            "total_matches": 0,
            "returned_employees": 0,
            "employees": [],
        }

    matches = matches[:limit]
    return {
        "status": "success",
        "requested_skills": [canonical_by_id[skill_id] for skill_id in resolved_ids],
        "match_mode": mode,
        "minimum_skill_count": minimum_skill_count,
        "excluded_skills": excluded_names,
        "proficiency_operator": proficiency_operator,
        "proficiency_value": proficiency_value,
        "proficiency_min": proficiency_min,
        "proficiency_max": proficiency_max,
        "sort_by": sort_by,
        "sort_order": sort_order,
        "availability_date": availability_date,
        "total_matches": total_matches,
        "returned_employees": len(matches),
        "truncated": total_matches > len(matches),
        "employees": matches,
    }

def analyze_demand_forecast(skill_name=None, demand_week=None, limit=10):
    """Read forecasted demand from generated CSVs without running generators."""
    root = get_data_root()
    path = root / "processed" / "demand_forecast.csv"
    skills_path = root / "raw" / "skills.csv"
    if not path.exists() or not skills_path.exists():
        return {"status": "error", "message": "Demand forecast data is unavailable."}
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {"status": "error", "message": "limit must be a positive integer."}
    data = pd.read_csv(path)
    skills = pd.read_csv(skills_path, usecols=["skill_id", "skill_name"])
    if data.empty:
        return {"status": "not_found", "message": "No demand forecast records are available.", "skills": []}
    if not {"demand_week", "skill_id", "committed_hours", "proposed_hours", "expected_hours"}.issubset(data.columns):
        return {"status": "error", "message": "Demand forecast data is missing required fields."}

    if skill_name and str(skill_name).strip():
        matched = skills[skills.skill_name.astype(str).str.strip().str.casefold() == str(skill_name).strip().casefold()]
        if matched.empty:
            return {"status": "unknown_skills", "unknown_skills": [str(skill_name)], "skills": []}
        if matched.skill_id.nunique() != 1:
            return {"status": "ambiguous_skills", "ambiguous_skills": [str(skill_name)], "skills": []}
        data = data[data.skill_id.astype(str) == str(matched.iloc[0].skill_id)]
    if demand_week is not None:
        data = data[data.demand_week.astype(str) == str(demand_week)]
    if data.empty:
        return {"status": "not_found", "message": "No demand forecast records match the selected filters.", "skills": []}

    names = dict(zip(skills.skill_id.astype(str), skills.skill_name.astype(str)))
    data = data.copy()
    data["skill_id"] = data.skill_id.astype(str)
    data["skill_name"] = data.skill_id.map(names)
    for field in ("committed_hours", "proposed_hours", "expected_hours"):
        data[field] = pd.to_numeric(data[field], errors="coerce").fillna(0)
    grouped = data.groupby(["skill_id", "skill_name", "demand_week"], as_index=False).agg(
        committed_hours=("committed_hours", "sum"),
        proposed_hours=("proposed_hours", "sum"),
        expected_hours=("expected_hours", "sum"),
    )
    summary = grouped.groupby(["skill_id", "skill_name"], as_index=False).agg(
        committed_hours=("committed_hours", "sum"),
        proposed_hours=("proposed_hours", "sum"),
        expected_hours=("expected_hours", "sum"),
        weeks_included=("demand_week", "nunique"),
    ).sort_values(["expected_hours", "skill_name"], ascending=[False, True], kind="stable")
    output = []
    for row in summary.head(limit).itertuples(index=False):
        weekly = grouped[grouped.skill_id == row.skill_id].sort_values(
            ["expected_hours", "demand_week"], ascending=[False, True], kind="stable"
        ).head(5)
        output.append({
            "skill_id": str(row.skill_id), "skill_name": str(row.skill_name),
            "committed_hours": round(float(row.committed_hours), 2),
            "proposed_hours": round(float(row.proposed_hours), 2),
            "expected_hours": round(float(row.expected_hours), 2),
            "weeks_included": int(row.weeks_included),
            "weekly_details": [
                {"demand_week": str(item.demand_week),
                 "committed_hours": round(float(item.committed_hours), 2),
                 "proposed_hours": round(float(item.proposed_hours), 2),
                 "expected_hours": round(float(item.expected_hours), 2)}
                for item in weekly.itertuples(index=False)
            ],
        })
    dates = grouped.demand_week.astype(str)
    return {
        "status": "success", "analysis_scope": "skill_forecast",
        "reporting_period": {"start_week": dates.min(), "end_week": dates.max(),
                             "weeks_included": int(grouped.demand_week.nunique())},
        "total_skills": int(len(summary)), "returned_skills": len(output), "skills": output,
    }


def analyze_workforce_capacity(skill_names=None, demand_week=None, limit=10):
    """Read weekly capacity and skill-gap outputs; performs no allocations."""
    root = get_data_root()
    capacity_path = root / "processed" / "capacity_analysis.csv"
    gap_path = root / "processed" / "skill_gap_analysis.csv"
    skills_path = root / "raw" / "skills.csv"
    if not all(path.exists() for path in (capacity_path, gap_path, skills_path)):
        return {"status": "error", "message": "Capacity analysis data is unavailable."}
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {"status": "error", "message": "limit must be a positive integer."}
    capacity = pd.read_csv(capacity_path)
    gaps = pd.read_csv(gap_path)
    skills = pd.read_csv(skills_path, usecols=["skill_id", "skill_name"])
    if not {"availability_date", "available_hours", "allocated_hours", "remaining_hours"}.issubset(capacity.columns):
        return {"status": "error", "message": "Capacity data is missing required fields."}
    if not {"demand_week", "skill_id", "required_hours", "available_hours", "gap_hours", "gap_status"}.issubset(gaps.columns):
        return {"status": "error", "message": "Skill-gap data is missing required fields."}
    if demand_week is not None:
        capacity = capacity[capacity.availability_date.astype(str) == str(demand_week)]
        gaps = gaps[gaps.demand_week.astype(str) == str(demand_week)]
    if isinstance(skill_names, str):
        skill_names = [skill_names]
    if skill_names is not None and not isinstance(skill_names, (list, tuple)):
        return {"status": "error", "message": "skill_names must be a list of exact skill names."}
    requested = []
    for name in skill_names or []:
        matched = skills[skills.skill_name.astype(str).str.strip().str.casefold() == str(name).strip().casefold()]
        if matched.empty:
            return {"status": "unknown_skills", "unknown_skills": [str(name)], "skill_gaps": []}
        if matched.skill_id.nunique() != 1:
            return {"status": "ambiguous_skills", "ambiguous_skills": [str(name)], "skill_gaps": []}
        requested.append(str(matched.iloc[0].skill_id))
    if requested:
        gaps = gaps[gaps.skill_id.astype(str).isin(requested)]

    capacity["availability_date"] = capacity.availability_date.astype(str)
    weekly_capacity = capacity.groupby("availability_date", as_index=False).agg(
        available_hours=("available_hours", "sum"),
        allocated_hours=("allocated_hours", "sum"),
        remaining_hours=("remaining_hours", "sum"),
    ).sort_values("availability_date")
    names = dict(zip(skills.skill_id.astype(str), skills.skill_name.astype(str)))
    gaps = gaps.copy()
    gaps["skill_id"] = gaps.skill_id.astype(str)
    gaps["skill_name"] = gaps.skill_id.map(names)
    gap_records = []
    for row in gaps.sort_values(["gap_hours", "demand_week"], ascending=[False, True]).head(limit).itertuples(index=False):
        gap_records.append({
            "demand_week": str(row.demand_week), "skill_id": str(row.skill_id),
            "skill_name": str(row.skill_name), "required_hours": round(float(row.required_hours), 2),
            "skill_available_hours": round(float(row.available_hours), 2),
            "gap_hours": round(float(row.gap_hours), 2), "gap_status": str(row.gap_status),
            "qualified_employees": int(getattr(row, "qualified_employees", 0)),
        })
    dates = weekly_capacity.availability_date if not weekly_capacity.empty else pd.Series(dtype=str)
    return {
        "status": "success" if not weekly_capacity.empty or not gaps.empty else "not_found",
        "reporting_period": {"start_week": dates.min() if not dates.empty else None,
                             "end_week": dates.max() if not dates.empty else None,
                             "weeks_included": int(dates.nunique()) if not dates.empty else 0},
        "weekly_capacity": [
            {"availability_date": str(row.availability_date),
             "available_hours": round(float(row.available_hours), 2),
             "allocated_hours": round(float(row.allocated_hours), 2),
             "remaining_hours": round(float(row.remaining_hours), 2)}
            for row in weekly_capacity.tail(limit).itertuples(index=False)
        ],
        "skill_gaps": gap_records,
        "total_skill_gap_records": int(len(gaps)),
    }


def summarize_skill_intelligence(skill_names=None, limit=10):
    """Summarize active employees' current, qualified skill intelligence."""
    root = get_data_root()
    required_paths = [root / "raw" / filename for filename in ("employees.csv", "skills.csv")]
    intelligence_path = root / "processed" / "skill_intelligence.csv"
    if not all(path.exists() for path in required_paths) or not intelligence_path.exists():
        return {"status": "error", "message": "Skill intelligence data is unavailable."}
    employees = pd.read_csv(required_paths[0], usecols=["employee_id", "status"], dtype={"employee_id": str})
    skills = pd.read_csv(required_paths[1], usecols=["skill_id", "skill_name"], dtype={"skill_id": str})
    intelligence = pd.read_csv(intelligence_path, usecols=["employee_id", "skill_id", "proficiency_level", "skill_status", "is_qualified"], dtype={"employee_id": str, "skill_id": str})
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return {"status": "error", "message": "limit must be a positive integer."}
    if isinstance(skill_names, str):
        skill_names = [skill_names]
    if skill_names is not None and not isinstance(skill_names, (list, tuple)):
        return {"status": "error", "message": "skill_names must be a list of exact skill names."}
    requested_ids = []
    for name in skill_names or []:
        matched = skills[skills.skill_name.astype(str).str.strip().str.casefold() == str(name).strip().casefold()]
        if matched.empty:
            return {"status": "unknown_skills", "unknown_skills": [str(name)], "skills": []}
        if matched.skill_id.nunique() != 1:
            return {"status": "ambiguous_skills", "ambiguous_skills": [str(name)], "skills": []}
        requested_ids.append(str(matched.iloc[0].skill_id))
    active_ids = set(employees.loc[employees.status.astype(str).str.strip().str.casefold() == "active", "employee_id"].astype(str))
    intelligence["employee_id"] = intelligence.employee_id.fillna("").astype(str)
    intelligence["skill_id"] = intelligence.skill_id.fillna("").astype(str)
    intelligence["is_qualified"] = intelligence.is_qualified.astype(str).str.casefold().isin({"true", "1", "yes"})
    intelligence["proficiency_level"] = pd.to_numeric(intelligence.proficiency_level, errors="coerce")
    qualified = intelligence[
        intelligence.employee_id.isin(active_ids)
        & intelligence.skill_status.astype(str).str.casefold().eq("current")
        & intelligence.is_qualified
    ].dropna(subset=["proficiency_level"]).sort_values(
        "proficiency_level", ascending=False
    ).drop_duplicates(["employee_id", "skill_id"])
    if requested_ids:
        qualified = qualified[qualified.skill_id.isin(requested_ids)]
        skills = skills[skills.skill_id.isin(requested_ids)]
    grouped = qualified.groupby("skill_id").agg(
        qualified_employee_count=("employee_id", "nunique"),
        proficiency_distribution=("proficiency_level", lambda series: {
            str(int(level)): int(count)
            for level, count in series.value_counts().sort_index().items()
        }),
    ).reset_index()
    output = skills.merge(grouped, on="skill_id", how="left").fillna({"qualified_employee_count": 0})
    output["qualified_employee_count"] = output.qualified_employee_count.astype(int)
    output = output.sort_values(["qualified_employee_count", "skill_name"], ascending=[True, True]).head(limit)
    return {
        "status": "success", "ranking": "fewest qualified active employees first",
        "total_skills": int(len(skills)), "returned_skills": len(output),
        "skills": [
            {"skill_id": str(row.skill_id), "skill_name": str(row.skill_name),
             "qualified_employee_count": int(row.qualified_employee_count),
             "proficiency_distribution": row.proficiency_distribution if isinstance(row.proficiency_distribution, dict) else {}}
            for row in output.itertuples(index=False)
        ],
    }


def compare_workforce_strategies(skill_id, demand_week):
    """
    Compare workforce strategies for a specific skill and demand week.
    """

    from engine.what_if_simulator import load_data, compare_scenarios

    data = load_data()
    recommendations = data["recommendations"]
    matching_recommendation = recommendations[
        recommendations["demand_week"].astype(str).eq(str(demand_week))
        & recommendations["skill_id"].astype(str).eq(str(skill_id))
    ]
    if matching_recommendation.empty:
        return {
            "status": "not_found",
            "message": (
                "No workforce recommendation exists for the requested "
                "skill and demand week."
            ),
        }

    results = compare_scenarios(
        data,
        demand_week,
        skill_id
    )

    if results is None or results.empty:
        return {
            "status": "not_found",
            "message": "No scenario results found for the requested skill and week."
        }

    scenarios = []

    for _, row in results.iterrows():
        scenarios.append({
            "strategy": str(row["strategy"]),
            "hours_resolved": round(float(row["hours_resolved"]), 2),
            "remaining_gap": round(float(row["remaining_gap"]), 2),
            "estimated_cost": round(float(row["estimated_cost"]), 2)
        })

    return {
        "status": "success",
        "skill_id": skill_id,
        "demand_week": demand_week,
        "scenarios": scenarios
    }
