"""Local talent matching for Project Intelligence.

Everything here runs locally with Pandas. No employee record is sent to Groq,
no workforce dataset is modified, and no allocation is created.

Use :func:`load_matching_data` to inspect the input frames and
:func:`match_project_requirements` to run a match. Requirements must already
follow the schema validated by
``features.project_intelligence.requirement_extractor``.
"""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from features.project_intelligence.requirement_extractor import (
    validate_requirements,
)

MAX_CANDIDATES_PER_TIER = 10

NO_QUALIFIED_MESSAGE = (
    "No suitable internal employee with this skill is currently available."
)

RECOMMENDATION_FILLED = "Filled"
RECOMMENDATION_PARTIAL = "Partial staffing gap"
RECOMMENDATION_VERIFY = "Qualification match — availability requires verification"
RECOMMENDATION_TRAINING = "Training required — not a qualification guarantee"
RECOMMENDATION_EXTERNAL = "External hiring required"
RECOMMENDATION_UNRESOLVED = (
    "Skill not in workforce taxonomy — internal supply not assessed"
)
RECOMMENDATION_NO_MATCH = "No internal match"

_ACTIVE_STATUS = "active"
_CURRENT_STATUS = "current"

_REQUIRED_FILES: dict[str, tuple[str, tuple[str, ...]]] = {
    "employees": (
        "raw/employees.csv",
        ("employee_id", "employee_name", "role_id", "employment_type", "status"),
    ),
    "skills": ("raw/skills.csv", ("skill_id", "skill_name", "skill_category")),
    "skill_intelligence": (
        "processed/skill_intelligence.csv",
        (
            "employee_id",
            "skill_id",
            "proficiency_level",
            "last_verified_date",
            "days_since_verified",
            "skill_status",
            "is_qualified",
            "skill_name",
            "skill_category",
        ),
    ),
    "capacity": (
        "processed/capacity_analysis.csv",
        ("employee_id", "availability_date", "remaining_hours"),
    ),
}

_OPTIONAL_FILES: dict[str, tuple[str, tuple[str, ...]]] = {
    "training": (
        "raw/training.csv",
        ("employee_id", "skill_id", "training_status"),
    ),
    "roles": ("raw/roles.csv", ("role_id", "role_name")),
}


class MatchingDataError(RuntimeError):
    """Raised when the workforce inputs cannot be read safely."""


def resolve_data_root(root: Path | str | None = None) -> Path:
    """Resolve the active data root dynamically, never hardcoding a folder."""
    if root is not None:
        return Path(root).resolve()

    from dashboard.data import get_data_root

    return Path(get_data_root()).resolve()


def _read_required(path: Path, columns: tuple[str, ...], label: str) -> pd.DataFrame:
    if not path.is_file():
        raise MatchingDataError(
            f"Required dataset '{label}' is missing from the active data root."
        )
    try:
        frame = pd.read_csv(path, usecols=list(columns))
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError) as exc:
        raise MatchingDataError(
            f"Required dataset '{label}' could not be read. It may be malformed "
            "or missing expected columns."
        ) from exc

    missing = [column for column in columns if column not in frame.columns]
    if missing:
        raise MatchingDataError(
            f"Required dataset '{label}' is missing columns: {', '.join(missing)}."
        )
    if frame.empty:
        raise MatchingDataError(f"Required dataset '{label}' is empty.")
    return frame


def _read_optional(
    path: Path, columns: tuple[str, ...], label: str, warnings: list[str]
) -> pd.DataFrame:
    if not path.is_file():
        warnings.append(f"Optional dataset '{label}' is missing; related details are limited.")
        return pd.DataFrame(columns=list(columns))
    try:
        frame = pd.read_csv(path, usecols=list(columns))
    except (OSError, ValueError, pd.errors.ParserError, pd.errors.EmptyDataError):
        warnings.append(f"Optional dataset '{label}' could not be read; related details are limited.")
        return pd.DataFrame(columns=list(columns))

    missing = [column for column in columns if column not in frame.columns]
    if missing:
        warnings.append(
            f"Optional dataset '{label}' is missing columns "
            f"({', '.join(missing)}); related details are limited."
        )
        return pd.DataFrame(columns=list(columns))
    return frame


def _coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series.fillna(False)
    normalized = series.astype(str).str.strip().str.casefold()
    return normalized.isin({"true", "1", "yes", "y", "t"})


def _normalize_skill_name(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _prepare_frames(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    prepared: dict[str, pd.DataFrame] = {}

    employees = frames["employees"].copy()
    employees["employee_id"] = employees["employee_id"].astype(str).str.strip()
    employees["employee_name"] = employees["employee_name"].fillna("").astype(str)
    employees["role_id"] = employees["role_id"].fillna("").astype(str)
    employees["employment_type"] = employees["employment_type"].fillna("").astype(str)
    employees["status"] = employees["status"].fillna("").astype(str).str.strip().str.casefold()
    employees = employees.drop_duplicates(subset=["employee_id"], keep="first")
    prepared["employees"] = employees

    skills = frames["skills"].copy()
    skills["skill_id"] = skills["skill_id"].astype(str).str.strip()
    skills["skill_name"] = skills["skill_name"].fillna("").astype(str).str.strip()
    skills["skill_category"] = skills["skill_category"].fillna("").astype(str).str.strip()
    skills = skills[skills["skill_name"] != ""].drop_duplicates(subset=["skill_id"])
    prepared["skills"] = skills

    intelligence = frames["skill_intelligence"].copy()
    intelligence["employee_id"] = intelligence["employee_id"].astype(str).str.strip()
    intelligence["skill_id"] = intelligence["skill_id"].astype(str).str.strip()
    intelligence["skill_name"] = intelligence["skill_name"].fillna("").astype(str)
    intelligence["skill_category"] = intelligence["skill_category"].fillna("").astype(str)
    intelligence["proficiency_level"] = pd.to_numeric(
        intelligence["proficiency_level"], errors="coerce"
    )
    intelligence["days_since_verified"] = pd.to_numeric(
        intelligence["days_since_verified"], errors="coerce"
    )
    intelligence["skill_status"] = (
        intelligence["skill_status"].fillna("").astype(str).str.strip()
    )
    intelligence["is_qualified"] = _coerce_bool(intelligence["is_qualified"])
    if intelligence["proficiency_level"].isna().all():
        raise MatchingDataError(
            "Required dataset 'processed/skill_intelligence.csv' has no usable "
            "proficiency values."
        )
    intelligence = intelligence.dropna(subset=["proficiency_level"])
    intelligence["proficiency_level"] = intelligence["proficiency_level"].astype(int)
    prepared["skill_intelligence"] = intelligence

    capacity = frames["capacity"].copy()
    capacity["employee_id"] = capacity["employee_id"].astype(str).str.strip()
    capacity["availability_date"] = pd.to_datetime(
        capacity["availability_date"], errors="coerce"
    )
    capacity["remaining_hours"] = pd.to_numeric(
        capacity["remaining_hours"], errors="coerce"
    )
    capacity = capacity.dropna(subset=["availability_date"])
    if capacity["remaining_hours"].isna().all():
        raise MatchingDataError(
            "Required dataset 'processed/capacity_analysis.csv' has no usable "
            "remaining-hours values."
        )
    if capacity.duplicated(subset=["employee_id", "availability_date"]).any():
        raise MatchingDataError(
            "Required dataset 'processed/capacity_analysis.csv' contains duplicate "
            "employee-week records and cannot be used reliably."
        )
    capacity["week_end"] = capacity["availability_date"] + pd.Timedelta(days=6)
    capacity = capacity.sort_values(["employee_id", "availability_date"])
    prepared["capacity"] = capacity

    training = frames["training"].copy()
    if not training.empty:
        training["employee_id"] = training["employee_id"].astype(str).str.strip()
        training["skill_id"] = training["skill_id"].astype(str).str.strip()
        training["training_status"] = (
            training["training_status"].fillna("").astype(str).str.strip().str.casefold()
        )
    prepared["training"] = training

    roles = frames["roles"].copy()
    if not roles.empty:
        roles["role_id"] = roles["role_id"].astype(str).str.strip()
        roles["role_name"] = roles["role_name"].fillna("").astype(str).str.strip()
    prepared["roles"] = roles

    return prepared


@lru_cache(maxsize=4)
def _cached_bundle(root_path: str) -> tuple[dict[str, pd.DataFrame], tuple[str, ...]]:
    root = Path(root_path)
    warnings: list[str] = []
    raw: dict[str, pd.DataFrame] = {}

    for key, (relative, columns) in _REQUIRED_FILES.items():
        raw[key] = _read_required(root / relative, columns, relative)
    for key, (relative, columns) in _OPTIONAL_FILES.items():
        raw[key] = _read_optional(root / relative, columns, relative, warnings)

    frames = _prepare_frames(raw)
    return frames, tuple(warnings)


def load_matching_data(
    root: Path | str | None = None,
) -> dict[str, pd.DataFrame]:
    """Load and normalize only the datasets needed for matching.

    Input frames are cached by resolved data-root path. Match results are never
    cached. Callers must treat the returned frames as read-only.
    """
    frames, _ = _cached_bundle(str(resolve_data_root(root)))
    return frames


def _training_map(training: pd.DataFrame) -> dict[tuple[str, str], str]:
    statuses: dict[tuple[str, str], set[str]] = {}
    if training.empty:
        return {}
    for row in training.itertuples(index=False):
        key = (str(row.employee_id), str(row.skill_id))
        value = str(row.training_status or "").strip()
        if value:
            statuses.setdefault(key, set()).add(value)
    return {key: ", ".join(sorted(values)) for key, values in statuses.items()}


def _role_map(roles: pd.DataFrame) -> dict[str, str]:
    if roles.empty:
        return {}
    return {
        str(row.role_id): str(row.role_name or "")
        for row in roles.itertuples(index=False)
    }


def _project_weeks(
    capacity: pd.DataFrame, start: pd.Timestamp | None, end: pd.Timestamp | None
) -> list[pd.Timestamp]:
    if start is None or end is None:
        return []
    weeks = pd.DatetimeIndex(capacity["availability_date"].unique()).sort_values()
    week_end = weeks + pd.Timedelta(days=6)
    overlap = (weeks <= end) & (week_end >= start)
    return [pd.Timestamp(week) for week in weeks[overlap]]


def _availability_frame(
    capacity: pd.DataFrame,
    employee_ids: Iterable[str],
    weeks: list[pd.Timestamp],
    required_hours: float | None,
) -> pd.DataFrame:
    """Per-employee weekly verification for the overlapping project weeks."""
    columns = [
        "weeks_with_data",
        "total_remaining",
        "min_remaining",
        "negative_weeks",
        "short_weeks",
    ]
    ids = list(dict.fromkeys(str(employee_id) for employee_id in employee_ids))
    if not ids or not weeks:
        return pd.DataFrame(columns=columns)

    window = capacity[
        capacity["employee_id"].isin(ids)
        & capacity["availability_date"].isin(weeks)
    ].dropna(subset=["remaining_hours"])

    if window.empty:
        return pd.DataFrame(columns=columns)

    grouped = window.groupby("employee_id", sort=False)

    result = pd.DataFrame(
        {
            "weeks_with_data": grouped["availability_date"].nunique(),
            "total_remaining": grouped["remaining_hours"].sum(),
            "min_remaining": grouped["remaining_hours"].min(),
            "negative_weeks": grouped["remaining_hours"].apply(
                lambda values: int((values < 0).sum())
            ),
        }
    )

    if required_hours is None:
        result["short_weeks"] = grouped["remaining_hours"].apply(
            lambda values: int((values <= 0).sum())
        )
    else:
        result["short_weeks"] = grouped["remaining_hours"].apply(
            lambda values: int((values < required_hours).sum())
        )

    return result


def _availability_status(
    weeks_expected: int,
    weeks_with_data: int,
    negative_weeks: int,
    short_weeks: int,
    total_remaining: float,
    has_dates: bool,
) -> tuple[str, str]:
    """Return ``(coverage_status, availability_status)``."""
    if not has_dates:
        return "not_verified", "unknown"
    if weeks_expected <= 0:
        return "not_verified", "unknown"
    if weeks_with_data < weeks_expected:
        return "partially_verified", "unknown"
    if short_weeks == 0 and negative_weeks == 0:
        return "fully_verified", "available"
    if total_remaining > 0:
        return "fully_verified", "limited"
    return "fully_verified", "unavailable"


def _availability_reason(
    coverage: str,
    status: str,
    weeks_expected: int,
    weeks_with_data: int,
    short_weeks: int,
    negative_weeks: int,
    required_hours: float | None,
) -> str:
    if coverage == "not_verified":
        return (
            "Project dates are missing or outside the availability horizon, so "
            "availability cannot be fully verified."
        )
    if coverage == "partially_verified":
        return (
            f"Availability is only partially verified ({weeks_with_data} of "
            f"{weeks_expected} project weeks have capacity records)."
        )
    if negative_weeks > 0:
        return (
            f"{negative_weeks} of {weeks_expected} project weeks have negative "
            "remaining hours."
        )
    if short_weeks > 0:
        if required_hours is None:
            return (
                f"{short_weeks} of {weeks_expected} project weeks have zero or "
                "negative remaining hours."
            )
        return (
            f"{short_weeks} of {weeks_expected} project weeks have less than the "
            f"required {required_hours:g} remaining hours."
        )
    if status == "available":
        return "Available for every overlapping project week."
    return "Availability does not meet the project requirement."


def _candidate(
    row: Any,
    *,
    employee_lookup: dict[str, dict[str, str]],
    roles: dict[str, str],
    training: dict[tuple[str, str], str],
    relation: str,
    coverage: str,
    availability: str,
    weeks_expected: int,
    weeks_with_data: int,
    short_weeks: int,
    negative_weeks: int,
    min_remaining: float | None,
    total_remaining: float,
    required_hours: float | None,
    reason: str | None = None,
    counts_toward_headcount: bool = False,
    selected_for_position: bool = False,
) -> dict[str, Any]:
    employee = employee_lookup.get(str(row.employee_id), {})
    employee_name = str(employee.get("employee_name", ""))
    role_id = str(employee.get("role_id", ""))
    employment_type = str(employee.get("employment_type", ""))
    employee_status = str(employee.get("status", ""))

    skill_id = str(row.skill_id)
    availability_reason = _availability_reason(
        coverage,
        availability,
        weeks_expected,
        weeks_with_data,
        short_weeks,
        negative_weeks,
        required_hours,
    )

    last_verified = getattr(row, "last_verified_date", None)
    last_verified_date = (
        "" if last_verified is None or pd.isna(last_verified) else str(last_verified)
    )
    days_since = getattr(row, "days_since_verified", None)

    return {
        "employee_id": str(row.employee_id),
        "employee_name": employee_name,
        "employee_status": employee_status,
        "role_id": role_id,
        "role_name": roles.get(role_id, ""),
        "employment_type": employment_type,
        "skill_id": skill_id,
        "skill_name": str(getattr(row, "skill_name", "")),
        "skill_category": str(getattr(row, "skill_category", "")),
        "proficiency_level": int(getattr(row, "proficiency_level", 0)),
        "skill_status": str(getattr(row, "skill_status", "")),
        "last_verified_date": last_verified_date,
        "days_since_verified": (
            None if days_since is None or pd.isna(days_since) else int(days_since)
        ),
        "relation": relation,
        "training_status": training.get((str(row.employee_id), skill_id)),
        "coverage_status": coverage,
        "availability_status": availability,
        "weeks_expected": weeks_expected,
        "weeks_with_data": weeks_with_data,
        "weeks_below_required": short_weeks,
        "negative_weeks": negative_weeks,
        "min_remaining_hours": (
            None if min_remaining is None or pd.isna(min_remaining) else float(min_remaining)
        ),
        "net_available_hours": float(total_remaining) if total_remaining is not None else 0.0,
        "counts_toward_headcount": bool(counts_toward_headcount),
        "selected_for_position": bool(selected_for_position),
        "reason": reason or availability_reason,
        "availability_reason": availability_reason,
    }


def _empty_skill_result(
    requirement: dict[str, Any], *, resolution: str
) -> dict[str, Any]:
    needed = int(requirement.get("employees_needed") or 0)
    return {
        "skill_name": str(requirement.get("skill_name") or ""),
        "resolved_skill_id": None,
        "skill_category": None,
        "resolution": resolution,
        "min_proficiency_level": int(requirement.get("min_proficiency_level") or 0),
        "employees_needed": needed,
        "required_weekly_hours_per_position": requirement.get(
            "required_weekly_hours_per_position"
        ),
        "matched_count": 0,
        "remaining_gap": needed,
        "recommended_employee_ids": [],
        "qualified_candidates": [],
        "qualified_candidates_total": 0,
        "capacity_conflict_total": 0,
        "same_skill_conflict_total": 0,
        "training_candidates": [],
        "training_candidates_total": 0,
        "related_skill_candidates": [],
        "related_skill_candidates_total": 0,
        "stale_candidates": [],
        "stale_candidates_total": 0,
        "excluded_candidates": [],
        "excluded_candidates_total": 0,
        "exclusion_summary": {},
        "availability": {"weeks_expected": 0, "fully_verified": False},
        "recommendation": RECOMMENDATION_UNRESOLVED,
        "recommendation_reason": (
            f"'{requirement.get('skill_name')}' is not an exact match in the "
            "workforce skill taxonomy. Internal supply cannot be assessed for "
            "this requirement until the manager resolves the skill."
        ),
        "external_hiring_recommended": needed > 0,
        "warnings": ["Skill is unresolved in the workforce taxonomy."],
    }


def _resolve_skill(
    name: str, skills: pd.DataFrame
) -> tuple[dict[str, Any] | None, str | None]:
    """Return ``(skill_row, warning)`` using exact normalized matching only."""
    normalized = _normalize_skill_name(name)
    if not normalized:
        return None, "Skill name is empty."

    by_name = skills[skills["skill_name"].map(_normalize_skill_name) == normalized]
    if len(by_name) == 1:
        return by_name.iloc[0].to_dict(), None
    if len(by_name) > 1:
        return None, (
            f"Skill name '{name}' matches multiple taxonomy skills and must be "
            "resolved by the manager."
        )

    by_id = skills[skills["skill_id"].str.casefold() == normalized]
    if len(by_id) == 1:
        return by_id.iloc[0].to_dict(), None

    return None, f"Skill '{name}' is not present in the workforce taxonomy."


def _sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            -(item["min_remaining_hours"] if item["min_remaining_hours"] is not None else -1e9),
            -item["proficiency_level"],
            item["employee_id"],
        ),
    )


def _tier(candidates: list[dict[str, Any]], limit: int) -> tuple[list[dict[str, Any]], int]:
    return candidates[:limit], len(candidates)


def _match_resolved_skill(
    requirement: dict[str, Any],
    skill_row: dict[str, Any],
    *,
    frames: dict[str, pd.DataFrame],
    weeks: list[pd.Timestamp],
    project_dates_present: bool,
    required_skill_ids: set[str],
    allocation_ledger: dict[str, dict[pd.Timestamp, float]],
    unknown_hours_employees: set[str],
    selected_skill_employees: dict[str, set[str]],
    limit: int,
) -> dict[str, Any]:
    employees = frames["employees"]
    intelligence = frames["skill_intelligence"]
    capacity = frames["capacity"]
    training = _training_map(frames["training"])
    roles = _role_map(frames["roles"])
    employee_lookup: dict[str, dict[str, str]] = employees.set_index("employee_id")[
        ["employee_name", "role_id", "employment_type", "status"]
    ].to_dict("index")

    skill_id = str(skill_row["skill_id"])
    skill_name = str(skill_row["skill_name"])
    skill_category = str(skill_row["skill_category"])
    required_level = int(requirement.get("min_proficiency_level") or 0)
    needed = int(requirement.get("employees_needed") or 0)
    required_hours_raw = requirement.get("required_weekly_hours_per_position")
    required_hours = (
        float(required_hours_raw) if required_hours_raw is not None else None
    )

    employee_status = employees.set_index("employee_id")["status"]
    exact = intelligence[intelligence["skill_id"] == skill_id].copy()
    exact["employee_status"] = (
        exact["employee_id"].map(employee_status).fillna("").astype(str)
    )

    active_exact = exact[exact["employee_status"] == _ACTIVE_STATUS].copy()
    inactive_exact = exact[exact["employee_status"] != _ACTIVE_STATUS].copy()

    is_current = active_exact["skill_status"].str.casefold() == _CURRENT_STATUS
    is_qualified_row = active_exact["is_qualified"].astype(bool)
    # The approved qualification rule requires current skills at level 3 or above,
    # in addition to the project's own minimum proficiency.
    qualification_level = max(required_level, 3)
    meets_proficiency = active_exact["proficiency_level"] >= qualification_level

    qualified_rows = active_exact[
        is_current & is_qualified_row & meets_proficiency
    ].sort_values(
        ["proficiency_level", "employee_id"], ascending=[False, True]
    ).drop_duplicates(subset=["employee_id"], keep="first")

    qualified_ids = qualified_rows["employee_id"].tolist()
    availability = _availability_frame(capacity, qualified_ids, weeks, required_hours)
    weeks_expected = len(weeks)
    capacity_window = capacity[
        capacity["employee_id"].isin(qualified_ids)
        & capacity["availability_date"].isin(weeks)
    ].dropna(subset=["remaining_hours"])
    weekly_capacity = {
        str(employee_id): {
            pd.Timestamp(row.availability_date): float(row.remaining_hours)
            for row in group.itertuples(index=False)
        }
        for employee_id, group in capacity_window.groupby("employee_id", sort=False)
    }

    qualified_candidates: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    exclusion_summary: dict[str, int] = {}

    def add_exclusion(candidate: dict[str, Any], reason: str) -> None:
        candidate = dict(candidate)
        candidate["reason"] = reason
        excluded.append(candidate)
        key = _exclusion_key(reason)
        exclusion_summary[key] = exclusion_summary.get(key, 0) + 1

    for row in qualified_rows.itertuples(index=False):
        employee_id = str(row.employee_id)
        if employee_id in availability.index:
            record = availability.loc[employee_id]
            weeks_with_data = int(record["weeks_with_data"])
            total_remaining = float(record["total_remaining"])
            min_remaining = float(record["min_remaining"])
            negative_weeks = int(record["negative_weeks"])
            short_weeks = int(record["short_weeks"])
        else:
            weeks_with_data = 0
            total_remaining = 0.0
            min_remaining = None
            negative_weeks = 0
            short_weeks = 0

        coverage, status = _availability_status(
            weeks_expected,
            weeks_with_data,
            negative_weeks,
            short_weeks,
            total_remaining,
            project_dates_present,
        )

        candidate = _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="exact",
            coverage=coverage,
            availability=status,
            weeks_expected=weeks_expected,
            weeks_with_data=weeks_with_data,
            short_weeks=short_weeks,
            negative_weeks=negative_weeks,
            min_remaining=min_remaining,
            total_remaining=total_remaining,
            required_hours=required_hours,
            counts_toward_headcount=(
                coverage == "fully_verified" and status == "available"
            ),
        )
        qualified_candidates.append(candidate)

        if not candidate["counts_toward_headcount"] and candidate["availability_status"] != "available":
            add_exclusion(candidate, candidate["availability_reason"])

    # Process candidates in order while enforcing the run-wide weekly capacity ledger.
    qualified_candidates = _sort_candidates(qualified_candidates)
    selected_here = 0
    capacity_conflict_total = 0
    same_skill_conflict_total = 0
    recommended_ids: list[str] = []
    selected_for_skill = selected_skill_employees.setdefault(skill_id, set())
    for candidate in qualified_candidates:
        if not candidate["counts_toward_headcount"]:
            continue
        employee_id = candidate["employee_id"]
        if employee_id in selected_for_skill:
            same_skill_conflict_total += 1
            add_exclusion(candidate, "Already counted for another position of the same skill.")
            continue
        if selected_here >= needed:
            continue

        conflict_reason: str | None = None
        if required_hours is None:
            if employee_id in allocation_ledger or employee_id in unknown_hours_employees:
                conflict_reason = (
                    "Weekly hours are unspecified, so combined capacity across "
                    "multiple skill requirements cannot be verified."
                )
        elif employee_id in unknown_hours_employees:
            conflict_reason = (
                "A prior skill assignment has unspecified weekly hours, so "
                "combined capacity cannot be verified."
            )
        else:
            employee_capacity = weekly_capacity.get(employee_id, {})
            assigned_hours = allocation_ledger.get(employee_id, {})
            short_weeks = [
                week
                for week in weeks
                if week not in employee_capacity
                or employee_capacity[week] - assigned_hours.get(week, 0.0)
                < required_hours - 1e-9
            ]
            if short_weeks:
                conflict_reason = (
                    "Combined weekly demand exceeds remaining capacity in "
                    f"{len(short_weeks)} of {weeks_expected} overlapping "
                    "project weeks."
                )
        if conflict_reason:
            capacity_conflict_total += 1
            add_exclusion(candidate, conflict_reason)
            continue

        selected_for_skill.add(employee_id)
        candidate["selected_for_position"] = True
        candidate["allocated_weekly_hours"] = required_hours
        recommended_ids.append(candidate["employee_id"])
        selected_here += 1
        if required_hours is None:
            unknown_hours_employees.add(employee_id)
        else:
            ledger = allocation_ledger.setdefault(employee_id, {})
            for week in weeks:
                ledger[week] = ledger.get(week, 0.0) + required_hours

    matched_count = selected_here
    remaining_gap = max(0, needed - matched_count)

    # Training candidates: exact skill, current, below the qualification bar.
    training_rows = active_exact[
        is_current & ~is_qualified_row & (active_exact["proficiency_level"] < 3)
    ].copy()
    training_rows = training_rows.sort_values(
        ["proficiency_level", "employee_id"], ascending=[False, True]
    ).drop_duplicates(subset=["employee_id"], keep="first")
    training_candidates = [
        _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="training",
            coverage="not_verified",
            availability="unknown",
            weeks_expected=weeks_expected,
            weeks_with_data=0,
            short_weeks=0,
            negative_weeks=0,
            min_remaining=None,
            total_remaining=0.0,
            required_hours=required_hours,
            reason=(
                f"Current proficiency {int(row.proficiency_level)} is below the "
                "qualified level; training is advisory only."
            ),
        )
        for row in training_rows.itertuples(index=False)
    ]

    # Stale and expired exact-skill records are advisory only.
    stale_rows = active_exact[
        active_exact["skill_status"].str.casefold() != _CURRENT_STATUS
    ].sort_values(
        ["days_since_verified", "employee_id"], ascending=[False, True]
    ).drop_duplicates(subset=["employee_id"], keep="first")
    stale_candidates = [
        _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="stale",
            coverage="not_verified",
            availability="unknown",
            weeks_expected=weeks_expected,
            weeks_with_data=0,
            short_weeks=0,
            negative_weeks=0,
            min_remaining=None,
            total_remaining=0.0,
            required_hours=required_hours,
            reason=(
                f"Skill status is '{row.skill_status}'; re-verification or "
                "training may be required and this record is not a qualified match."
            ),
        )
        for row in stale_rows.itertuples(index=False)
    ]

    # Related skills in the same category are potential training candidates.
    exact_employee_ids = set(exact["employee_id"])
    related_skill_ids = frames["skills"].loc[
        (frames["skills"]["skill_category"] == skill_category)
        & (frames["skills"]["skill_id"] != skill_id),
        "skill_id",
    ]
    related = intelligence[
        intelligence["skill_id"].isin(related_skill_ids)
        & ~intelligence["skill_id"].isin(required_skill_ids)
        & (intelligence["is_qualified"].astype(bool))
        & (intelligence["skill_status"].str.casefold() == _CURRENT_STATUS)
        & (~intelligence["employee_id"].isin(exact_employee_ids))
    ].copy()
    if not related.empty:
        related["employee_status"] = (
            related["employee_id"].map(employee_status).fillna("").astype(str)
        )
        related = related[related["employee_status"] == _ACTIVE_STATUS]
    related = related.sort_values(
        ["proficiency_level", "employee_id"], ascending=[False, True]
    ).drop_duplicates(subset=["employee_id"], keep="first")
    related_candidates = [
        _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="related",
            coverage="not_verified",
            availability="unknown",
            weeks_expected=weeks_expected,
            weeks_with_data=0,
            short_weeks=0,
            negative_weeks=0,
            min_remaining=None,
            total_remaining=0.0,
            required_hours=required_hours,
            reason=(
                f"Related skill '{row.skill_name}' in category '{skill_category}' "
                "is advisory only and is not a qualified match."
            ),
        )
        for row in related.itertuples(index=False)
    ]

    # Inactive employees are excluded from every tier but reported.
    for row in inactive_exact.itertuples(index=False):
        candidate = _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="exact",
            coverage="not_verified",
            availability="unknown",
            weeks_expected=weeks_expected,
            weeks_with_data=0,
            short_weeks=0,
            negative_weeks=0,
            min_remaining=None,
            total_remaining=0.0,
            required_hours=required_hours,
        )
        add_exclusion(
            candidate,
            f"Employee status is '{row.employee_status}'; only active employees "
            "are matched.",
        )

    # Active current employees below the required proficiency but at level 3+.
    under_level = active_exact[
        is_current & is_qualified_row & ~meets_proficiency
    ].drop_duplicates(subset=["employee_id"], keep="first")
    for row in under_level.itertuples(index=False):
        candidate = _candidate(
            row,
            employee_lookup=employee_lookup,
            roles=roles,
            training=training,
            relation="exact",
            coverage="not_verified",
            availability="unknown",
            weeks_expected=weeks_expected,
            weeks_with_data=0,
            short_weeks=0,
            negative_weeks=0,
            min_remaining=None,
            total_remaining=0.0,
            required_hours=required_hours,
        )
        add_exclusion(
            candidate,
            f"Proficiency {int(row.proficiency_level)} is below the required "
            f"level {required_level}.",
        )

    qualified_capped, qualified_total = _tier(qualified_candidates, limit)
    training_capped, training_total = _tier(training_candidates, limit)
    related_capped, related_total = _tier(related_candidates, limit)
    stale_capped, stale_total = _tier(stale_candidates, limit)
    excluded_capped, excluded_total = _tier(excluded, limit)

    recommendation, reason = _recommendation(
        needed=needed,
        matched=matched_count,
        qualified_total=qualified_total,
        capacity_conflict_total=capacity_conflict_total,
        same_skill_conflict_total=same_skill_conflict_total,
        training_total=training_total,
        stale_total=stale_total,
    )

    warnings: list[str] = []
    if weeks_expected == 0:
        warnings.append(
            "The project period does not overlap the availability data horizon; "
            "no employee can be counted as filled."
        )

    return {
        "skill_name": skill_name,
        "resolved_skill_id": skill_id,
        "skill_category": skill_category,
        "resolution": "exact",
        "min_proficiency_level": required_level,
        "employees_needed": needed,
        "required_weekly_hours_per_position": required_hours,
        "matched_count": matched_count,
        "remaining_gap": remaining_gap,
        "recommended_employee_ids": recommended_ids,
        "qualified_candidates": qualified_capped,
        "qualified_candidates_total": qualified_total,
        "capacity_conflict_total": capacity_conflict_total,
        "same_skill_conflict_total": same_skill_conflict_total,
        "training_candidates": training_capped,
        "training_candidates_total": training_total,
        "related_skill_candidates": related_capped,
        "related_skill_candidates_total": related_total,
        "stale_candidates": stale_capped,
        "stale_candidates_total": stale_total,
        "excluded_candidates": excluded_capped,
        "excluded_candidates_total": excluded_total,
        "exclusion_summary": exclusion_summary,
        "availability": {
            "weeks_expected": weeks_expected,
            "fully_verified": weeks_expected > 0,
        },
        "recommendation": recommendation,
        "recommendation_reason": reason,
        "external_hiring_recommended": remaining_gap > 0,
        "warnings": warnings,
    }


def _exclusion_key(reason: str) -> str:
    lowered = reason.casefold()
    if lowered.startswith("employee status"):
        return "inactive_employee"
    if "combined capacity cannot be verified" in lowered or "weekly hours are unspecified" in lowered:
        return "capacity_conflict"
    if "combined weekly demand exceeds remaining capacity" in lowered:
        return "capacity_conflict"
    if "another position of the same skill" in lowered:
        return "same_skill_duplicate"
    if "partially verified" in lowered:
        return "availability_partial"
    if "outside the availability horizon" in lowered or "dates are missing" in lowered:
        return "availability_unverified"
    if "negative remaining hours" in lowered:
        return "negative_capacity"
    if "zero or negative" in lowered or "less than the required" in lowered:
        return "insufficient_capacity"
    if lowered.startswith("proficiency"):
        return "below_required_proficiency"
    return "other"


def _recommendation(
    *,
    needed: int,
    matched: int,
    qualified_total: int,
    capacity_conflict_total: int,
    same_skill_conflict_total: int,
    training_total: int,
    stale_total: int,
) -> tuple[str, str]:
    filled_text = f"{matched} of {needed} position(s) filled."
    if matched > 0 and matched >= needed:
        return (
            RECOMMENDATION_FILLED,
            f"{filled_text} All requested positions have a fully available, "
            "qualified employee.",
        )
    if matched > 0:
        if same_skill_conflict_total > 0:
            return (
                RECOMMENDATION_PARTIAL,
                f"{filled_text} An employee is counted only once for this skill; "
                "the remaining positions require additional distinct candidates.",
            )
        if capacity_conflict_total > 0:
            return (
                RECOMMENDATION_PARTIAL,
                f"{filled_text} The remaining positions exceed verified weekly "
                "capacity when combined with other skill assignments.",
            )
        return (
            RECOMMENDATION_PARTIAL,
            f"{filled_text} The remaining {needed - matched} position(s) require "
            "verification, training or external hiring.",
        )
    if same_skill_conflict_total > 0:
        return (
            RECOMMENDATION_PARTIAL,
            f"{filled_text} Qualified employees were already counted for another "
            "position of this same skill; additional distinct candidates are needed.",
        )
    if capacity_conflict_total > 0:
        return (
            RECOMMENDATION_PARTIAL,
            f"{filled_text} Qualified employees were not counted because combined "
            "weekly demand exceeds or cannot be verified against remaining capacity.",
        )
    if qualified_total > 0:
        return (
            RECOMMENDATION_VERIFY,
            "Qualified employees exist for this skill, but none has fully verified "
            "availability for every project week. " + NO_QUALIFIED_MESSAGE,
        )
    if training_total > 0:
        return (
            RECOMMENDATION_TRAINING,
            NO_QUALIFIED_MESSAGE
            + " Training candidates are advisory only; training does not guarantee "
            "qualification.",
        )
    if stale_total > 0:
        return (
            RECOMMENDATION_NO_MATCH,
            NO_QUALIFIED_MESSAGE
            + " Only stale or expired skill records were found; they do not count "
            "as qualified.",
        )
    return (
        RECOMMENDATION_EXTERNAL,
        NO_QUALIFIED_MESSAGE + " External hiring is required for the remaining gap.",
    )


def match_project_requirements(
    requirements: dict[str, Any],
    *,
    data_root: Path | str | None = None,
    max_candidates: int = MAX_CANDIDATES_PER_TIER,
) -> dict[str, Any]:
    """Match validated project requirements against local workforce records.

    Returns a structured result. When the workforce data cannot be read, the
    result has ``status == "data_error"`` and a clear ``data_error`` message.
    """
    normalized, errors = validate_requirements(requirements)
    if normalized is None:
        return {
            "status": "invalid_requirements",
            "data_error": None,
            "errors": errors,
            "project": {},
            "summary": {},
            "skills": [],
            "warnings": [],
        }

    try:
        frames, load_warnings = _cached_bundle(str(resolve_data_root(data_root)))
    except MatchingDataError as exc:
        return {
            "status": "data_error",
            "data_error": str(exc),
            "errors": [],
            "project": {},
            "summary": {},
            "skills": [],
            "warnings": [],
        }

    frames = dict(frames)
    warnings: list[str] = list(load_warnings) + list(normalized.get("warnings") or [])
    capacity = frames["capacity"]

    start = (
        pd.Timestamp(normalized["project_start_date"])
        if normalized.get("project_start_date")
        else None
    )
    end = (
        pd.Timestamp(normalized["project_end_date"])
        if normalized.get("project_end_date")
        else None
    )
    project_dates_present = start is not None and end is not None

    if not project_dates_present:
        warnings.append(
            "Project dates are missing. Availability cannot be fully verified, "
            "so no employee can be counted as a filled position."
        )

    weeks = _project_weeks(capacity, start, end)
    horizon_start = capacity["availability_date"].min()
    horizon_end = capacity["availability_date"].max()

    allocation_ledger: dict[str, dict[pd.Timestamp, float]] = {}
    unknown_hours_employees: set[str] = set()
    selected_skill_employees: dict[str, set[str]] = {}
    skills_results: list[dict[str, Any]] = []
    unresolved: list[str] = []
    required_skill_ids: set[str] = set()
    for requested in normalized.get("skills_required") or []:
        required, _ = _resolve_skill(
            str(requested.get("skill_name") or ""), frames["skills"]
        )
        if required is not None:
            required_skill_ids.add(str(required["skill_id"]))

    for requirement in normalized.get("skills_required") or []:
        skill_row, resolution_warning = _resolve_skill(
            str(requirement.get("skill_name") or ""), frames["skills"]
        )
        if skill_row is None:
            unresolved.append(str(requirement.get("skill_name") or ""))
            result = _empty_skill_result(requirement, resolution="unresolved")
            if resolution_warning:
                result["warnings"].append(resolution_warning)
                result["recommendation_reason"] = resolution_warning
            skills_results.append(result)
            continue

        skills_results.append(
            _match_resolved_skill(
                requirement,
                skill_row,
                frames=frames,
                weeks=weeks,
                project_dates_present=project_dates_present,
                required_skill_ids=required_skill_ids,
                allocation_ledger=allocation_ledger,
                unknown_hours_employees=unknown_hours_employees,
                selected_skill_employees=selected_skill_employees,
                limit=max(0, int(max_candidates)),
            )
        )

    positions_requested = sum(
        int(result["employees_needed"]) for result in skills_results
    )
    positions_filled = sum(int(result["matched_count"]) for result in skills_results)

    if unresolved:
        warnings.append(
            "Some skills are unresolved and were not matched: "
            + ", ".join(unresolved)
            + "."
        )

    return {
        "status": "ok",
        "data_error": None,
        "errors": [],
        "project": {
            "project_name": normalized.get("project_name"),
            "project_start_date": normalized.get("project_start_date"),
            "project_end_date": normalized.get("project_end_date"),
            "project_duration_weeks": normalized.get("project_duration_weeks"),
            "availability_weeks": len(weeks),
            "data_horizon_start": horizon_start.date().isoformat() if pd.notna(horizon_start) else None,
            "data_horizon_end": horizon_end.date().isoformat() if pd.notna(horizon_end) else None,
        },
        "summary": {
            "skills_requested": len(skills_results),
            "skills_resolved": len(skills_results) - len(unresolved),
            "positions_requested": positions_requested,
            "positions_filled": positions_filled,
            "positions_unfilled": max(0, positions_requested - positions_filled),
            "unresolved_skills": unresolved,
            "qualified_candidate_matches": sum(
                int(result["qualified_candidates_total"]) for result in skills_results
            ),
        },
        "skills": skills_results,
        "warnings": list(dict.fromkeys(warnings)),
    }


def candidate_tier_limit(limit: int | None = None) -> int:
    """Return the effective display cap for a candidate tier."""
    if limit is None:
        return MAX_CANDIDATES_PER_TIER
    return max(0, int(limit))
