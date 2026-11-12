
import pandas as pd

from engine.decision_rules import (
    get_utilization_status,
    get_skill_status,
    choose_recommendation,
    explain_recommendation
)


# 1. UTILIZATION STATUS TESTS

def test_no_availability():
    row = {
        "available_hours": 0,
        "utilization_percentage": 0
    }
    assert get_utilization_status(row) == "No Availability"


def test_overallocated():
    row = {
        "available_hours": 40,
        "utilization_percentage": 120
    }
    assert get_utilization_status(row) == "Overallocated"


def test_high_utilization():
    row = {
        "available_hours": 40,
        "utilization_percentage": 90
    }
    assert get_utilization_status(row) == "High Utilization"


def test_healthy_utilization():
    row = {
        "available_hours": 40,
        "utilization_percentage": 75
    }
    assert get_utilization_status(row) == "Healthy Utilization"


def test_underutilized():
    row = {
        "available_hours": 40,
        "utilization_percentage": 50
    }
    assert get_utilization_status(row) == "Underutilized"


# 2. SKILL STATUS TESTS

def test_expired_skill():
    today = pd.Timestamp("2026-11-11")
    row = {
        "expiry_date": pd.Timestamp("2026-11-10"),
        "days_since_verified": 10
    }
    assert get_skill_status(row, today) == "Expired"


def test_stale_skill():
    today = pd.Timestamp("2026-11-11")
    row = {
        "expiry_date": pd.NaT,
        "days_since_verified": 400
    }
    assert get_skill_status(row, today) == "Stale"


def test_current_skill():
    today = pd.Timestamp("2026-11-11")
    row = {
        "expiry_date": pd.NaT,
        "days_since_verified": 100
    }
    assert get_skill_status(row, today) == "Current"


# 3. RECOMMENDATION TESTS

def test_internal_reallocation_recommendation():
    row = {
        "remaining_gap": 0,
        "potential_trainees": 5
    }
    assert choose_recommendation(row) == "Internal Reallocation"


def test_training_recommendation():
    row = {
        "remaining_gap": 20,
        "potential_trainees": 3
    }
    assert choose_recommendation(row) == "Training"


def test_external_hiring_recommendation():
    row = {
        "remaining_gap": 20,
        "potential_trainees": 0
    }
    assert choose_recommendation(row) == "External Hiring"


# 4. RECOMMENDATION EXPLANATION TESTS

def test_internal_reallocation_explanation():
    row = {"recommendation": "Internal Reallocation"}
    assert "Qualified internal employees" in explain_recommendation(row)


def test_training_explanation():
    row = {"recommendation": "Training"}
    assert "training employees" in explain_recommendation(row)


def test_external_hiring_explanation():
    row = {"recommendation": "External Hiring"}
    assert "External hiring" in explain_recommendation(row)
