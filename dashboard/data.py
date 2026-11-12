from pathlib import Path

import pandas as pd
import streamlit as st
from generator.config import data_root as configured_data_root

BASE_DIR = Path(__file__).resolve().parent.parent


def get_data_root() -> Path:
    """Resolve the shared workforce data root, preserving the project default."""
    return configured_data_root(BASE_DIR)


def _csv_path(filename: str, root: Path) -> Path:
    if filename.startswith("../"):
        return root / "raw" / filename[3:]
    return root / "processed" / filename


@st.cache_data(ttl=300, show_spinner=False)
def _load_csv(filename: str, root_path: str) -> pd.DataFrame:
    """Load modest analytic datasets with a short refresh interval."""
    path = _csv_path(filename, Path(root_path))
    if not path.is_file():
        return pd.DataFrame()
    try:
        if filename == "capacity_analysis.csv":
            # Capacity is large; these are the fields used by the UI and simulator views.
            return pd.read_csv(path, usecols=lambda col: col in {
                "availability_id", "employee_id", "availability_date", "available_hours",
                "employee_name", "employment_type", "role_id", "allocated_hours",
                "utilization_percentage", "remaining_hours", "utilization_status",
            })
        return pd.read_csv(path)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def load_csv(filename: str) -> pd.DataFrame:
    return _load_csv(filename, str(get_data_root()))


@st.cache_data(ttl=300, show_spinner=False)
def _read_head(filename: str, rows: int, root_path: str) -> pd.DataFrame:
    path = _csv_path(filename, Path(root_path))
    if not path.is_file():
        return pd.DataFrame()
    try:
        return pd.read_csv(path, nrows=rows)
    except (OSError, ValueError, pd.errors.ParserError):
        return pd.DataFrame()


def read_head(filename: str, rows: int = 1000) -> pd.DataFrame:
    return _read_head(filename, rows, str(get_data_root()))


@st.cache_data(ttl=300, show_spinner=False)
def _get_csv_rows(filename: str, root_path: str) -> int:
    path = _csv_path(filename, Path(root_path))
    if not path.is_file():
        return 0
    try:
        with path.open("rb") as stream:
            return max(sum(1 for _ in stream) - 1, 0)
    except OSError:
        return 0


def get_csv_rows(filename: str) -> int:
    return _get_csv_rows(filename, str(get_data_root()))


def get_options(filename: str, column: str) -> list[str]:
    frame = load_csv(filename)
    if frame.empty or column not in frame:
        return []
    return sorted(frame[column].dropna().astype(str).unique().tolist())


@st.cache_data(ttl=300, show_spinner=False)
def _get_employee_count(root_path: str) -> int:
    path = Path(root_path) / "raw" / "employees.csv"
    if not path.is_file():
        return 0
    try:
        frame = pd.read_csv(path, usecols=["status"])
        return int((frame.status.astype(str).str.casefold() == "active").sum())
    except (OSError, ValueError, pd.errors.ParserError):
        return 0


def get_employee_count() -> int:
    return _get_employee_count(str(get_data_root()))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_shortage_tool(skill: str, week: str | None, root_path: str):
    from services.tools import analyze_skill_shortage
    return analyze_skill_shortage(skill, week)


def shortage_tool(skill: str, week: str | None):
    return _cached_shortage_tool(skill, week, str(get_data_root()))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_talent_tool(
    skill: str, date: str | None, proficiency: int, limit: int, root_path: str
):
    from services.tools import find_internal_talent
    return find_internal_talent(skill, date, proficiency, limit)


def talent_tool(skill: str, date: str | None, proficiency: int, limit: int):
    return _cached_talent_tool(skill, date, proficiency, limit, str(get_data_root()))


@st.cache_data(ttl=300, show_spinner=False)
def _cached_strategy_tool(skill_id: str, week: str, root_path: str):
    from services.tools import compare_workforce_strategies
    return compare_workforce_strategies(skill_id, week)


def strategy_tool(skill_id: str, week: str):
    return _cached_strategy_tool(skill_id, week, str(get_data_root()))
