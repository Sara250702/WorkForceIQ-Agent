"""Shared deterministic generation and data-root configuration."""

from datetime import date
import os
from pathlib import Path


SEED = 20261022
REFERENCE_DATE = date(2026, 11, 11)
HORIZON_START = REFERENCE_DATE
HORIZON_END = date(2027, 11, 10)


def data_root(base_dir: Path) -> Path:
    """Return the selected data root, preserving the historic default."""
    selected = os.environ.get("WORKFORCEIQ_DATA_ROOT")
    if selected:
        return Path(selected).resolve()
    return (base_dir / "data").resolve()


def baseline_data_root(base_dir: Path) -> Path:
    """Return an explicitly selected baseline data root, if provided."""
    selected = os.environ.get("WORKFORCEIQ_BASELINE_DATA_ROOT")
    if not selected:
        return data_root(base_dir)
    return Path(selected).resolve()

