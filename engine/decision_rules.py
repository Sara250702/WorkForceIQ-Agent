import pandas as pd
import sys
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
from generator.config import REFERENCE_DATE


def get_utilization_status(row):

    if row["available_hours"] == 0:
        return "No Availability"

    elif row["utilization_percentage"] > 100:
        return "Overallocated"

    elif row["utilization_percentage"] >= 86:
        return "High Utilization"

    elif row["utilization_percentage"] >= 70:
        return "Healthy Utilization"

    else:
        return "Underutilized"


def get_skill_status(row, today=None):

    if today is None:
        if os.environ.get("WORKFORCEIQ_DATA_ROOT"):
            today = pd.Timestamp(REFERENCE_DATE)
        else:
            today = pd.Timestamp.today().normalize()

    if pd.notna(row["expiry_date"]) and row["expiry_date"] < today:
        return "Expired"

    elif row["days_since_verified"] > 365:
        return "Stale"

    else:
        return "Current"


def choose_recommendation(row):

    if row["remaining_gap"] <= 0:
        return "Internal Reallocation"

    elif row["potential_trainees"] > 0:
        return "Training"

    else:
        return "External Hiring"


def explain_recommendation(row):

    if row["recommendation"] == "Internal Reallocation":
        return (
            "Qualified internal employees have enough available "
            "capacity to cover the skill shortage."
        )

    elif row["recommendation"] == "Training":
        return (
            "The remaining skill shortage may be addressed by "
            "training employees who have foundational knowledge."
        )

    else:
        return (
            "Internal capacity and potential training candidates "
            "are insufficient. External hiring may be required."
        )
