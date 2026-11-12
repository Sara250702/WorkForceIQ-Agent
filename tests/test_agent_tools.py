
from pathlib import Path
from copy import deepcopy
from types import SimpleNamespace
import json

import pandas as pd

from services import agent, tools
from services.agent import execute_tool


def _write_query_root(tmp_path, records, *, statuses=None, talent_rows=None):
    root = Path(tmp_path)
    (root / "raw").mkdir(parents=True, exist_ok=True)
    (root / "processed").mkdir(parents=True, exist_ok=True)
    catalog = [
        ("SK-PY", "Python"),
        ("SK-JAVA", "Java"),
        ("SK-ST", "Streamlit"),
        ("SK-FAST", "FastAPI"),
        ("SK-ML", "Machine Learning"),
    ]
    skill_ids = {skill_name: skill_id for skill_id, skill_name in catalog}
    pd.DataFrame(catalog, columns=["skill_id", "skill_name"]).to_csv(
        root / "raw" / "skills.csv", index=False
    )
    employee_ids = sorted({record[0] for record in records})
    statuses = statuses or {}
    employees = [
        {
            "employee_id": employee_id,
            "employee_name": f"Name {employee_id}",
            "role_id": "ROLE-ENG",
            "employment_type": "Full-time",
            "status": statuses.get(employee_id, "active"),
        }
        for employee_id in employee_ids
    ]
    pd.DataFrame(employees).to_csv(root / "raw" / "employees.csv", index=False)
    intelligence = [
        {
            "employee_id": employee_id,
            "skill_id": skill_ids[skill_name],
            "proficiency_level": proficiency,
            "skill_status": skill_status,
            "is_qualified": qualified,
        }
        for employee_id, skill_name, proficiency, skill_status, qualified in records
    ]
    pd.DataFrame(intelligence).to_csv(
        root / "processed" / "skill_intelligence.csv", index=False
    )
    if talent_rows is not None:
        pd.DataFrame(talent_rows).to_csv(
            root / "processed" / "talent_discovery.csv", index=False
        )
    return root


def _row(employee_id, skill, level=4, status="Current", qualified=True):
    return (employee_id, skill, level, status, qualified)


def test_execute_unknown_tool():
    result = execute_tool("unknown_tool", {})

    assert result["status"] == "error"
    assert result["message"] == "Unknown tool: unknown_tool"


def test_execute_tool_with_missing_arguments():
    result = execute_tool("compare_workforce_strategies", {})

    assert result["status"] == "error"
    assert "query failed" in result["message"]


def _write_shortage_records(tmp_path, records):
    root = Path(tmp_path)
    (root / "processed").mkdir(parents=True, exist_ok=True)
    columns = ["skill_id", "skill_name", "demand_week", "remaining_gap"]
    columns.extend(key for record in records for key in record if key not in columns)
    pd.DataFrame(records, columns=columns).to_csv(
        root / "processed" / "workforce_recommendations.csv", index=False
    )
    return root


def test_organization_shortage_aggregates_and_ranks_remaining_gaps(monkeypatch, tmp_path):
    root = _write_shortage_records(tmp_path / "org-shortage", [
        {"skill_id": "SK-A", "skill_name": "Python", "demand_week": "2027-01-04", "remaining_gap": 5},
        {"skill_id": "SK-A", "skill_name": "Python", "demand_week": "2027-01-11", "remaining_gap": 10},
        {"skill_id": "SK-B", "skill_name": "SQL", "demand_week": "2027-01-04", "remaining_gap": 8},
        {"skill_id": "SK-B", "skill_name": "SQL", "demand_week": "2027-01-11", "remaining_gap": 8},
        {"skill_id": "SK-C", "skill_name": "Streamlit", "demand_week": "2027-01-04", "remaining_gap": 12},
    ])
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.analyze_skill_shortage()

    assert result["status"] == "success"
    assert result["analysis_scope"] == "organization_wide"
    assert result["ranking_method"] == "sum of weekly remaining_gap hours"
    assert [item["skill_name"] for item in result["skills"]] == ["SQL", "Python", "Streamlit"]
    assert [item["cumulative_remaining_gap_hours"] for item in result["skills"]] == [16, 15, 12]
    assert result["reporting_period"] == {
        "start_week": "2027-01-04", "end_week": "2027-01-11", "weeks_included": 2
    }
    assert result["skills"][1]["weekly_details"] == [
        {"demand_week": "2027-01-11", "remaining_gap_hours": 10.0},
        {"demand_week": "2027-01-04", "remaining_gap_hours": 5.0},
    ]


def test_organization_shortage_defaults_to_five_and_filters_week(monkeypatch, tmp_path):
    records = [
        {"skill_id": f"SK-{i}", "skill_name": f"Skill {i}",
         "demand_week": "2027-01-04", "remaining_gap": float(i)}
        for i in range(1, 8)
    ]
    records.extend([
        {"skill_id": "SK-1", "skill_name": "Skill 1",
         "demand_week": "2027-01-11", "remaining_gap": 20.0},
    ])
    root = _write_shortage_records(tmp_path / "top-five", records)
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    overall = tools.analyze_skill_shortage()
    selected_week = tools.analyze_skill_shortage(demand_week="2027-01-04")

    assert overall["returned_skills"] == 5
    assert overall["skills"][0]["skill_name"] == "Skill 1"
    assert overall["skills"][0]["cumulative_remaining_gap_hours"] == 21
    assert selected_week["reporting_period"]["weeks_included"] == 1
    assert selected_week["skills"][0]["skill_name"] == "Skill 7"


def test_organization_shortage_handles_empty_and_missing_values(monkeypatch, tmp_path):
    root = _write_shortage_records(tmp_path / "empty-shortage", [])
    monkeypatch.setattr(tools, "get_data_root", lambda: root)
    empty = tools.analyze_skill_shortage()
    assert empty["status"] == "not_found"
    assert empty["skills"] == []

    root = _write_shortage_records(tmp_path / "na-shortage", [
        {"skill_id": "SK-A", "skill_name": "Python", "demand_week": "2027-01-04", "remaining_gap": None},
        {"skill_id": "SK-B", "skill_name": "SQL", "demand_week": "2027-01-04", "remaining_gap": 4},
    ])
    monkeypatch.setattr(tools, "get_data_root", lambda: root)
    result = tools.analyze_skill_shortage()
    assert result["total_skills"] == 1
    assert result["skills"][0]["skill_name"] == "SQL"


def test_single_skill_shortage_behavior_and_optional_week_remain(monkeypatch, tmp_path):
    root = _write_shortage_records(tmp_path / "single-skill", [
        {"skill_id": "SK-PY", "skill_name": "Python", "demand_week": "2027-01-04",
         "remaining_gap": 5, "gap_hours": 8, "internal_employees": 1,
         "internal_available_hours": 3, "potential_trainees": 2,
         "recommendation": "Training"},
        {"skill_id": "SK-PY", "skill_name": "Python", "demand_week": "2027-01-11",
         "remaining_gap": 6, "gap_hours": 10, "internal_employees": 1,
         "internal_available_hours": 4, "potential_trainees": 2,
         "recommendation": "Training"},
    ])
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.analyze_skill_shortage("python", "2027-01-11")

    assert result["status"] == "success"
    assert result["total_periods"] == 1
    assert result["records"][0]["remaining_gap"] == 6
    assert result["records"][0]["demand_week"] == "2027-01-11"


def test_shortage_tool_schema_supports_broad_questions():
    schema = next(tool for tool in agent.WORKFORCE_TOOLS if tool["name"] == "analyze_skill_shortage")
    assert "skill_name" not in schema["parameters"].get("required", [])
    assert "omitted" in schema["description"]
    assert "without skill_name" in agent.AGENT_INSTRUCTIONS
    assert "only when the user explicitly specifies" in schema["description"]
    assert "never infer or insert a week" in agent.AGENT_INSTRUCTIONS


def test_shortage_agent_omits_unrequested_week_and_uses_explicit_week(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "test-model")

    def invoke(user_message, args, function_name="analyze_skill_shortage"):
        call = SimpleNamespace(
            id="shortage-call",
            function=SimpleNamespace(
                name=function_name,
                arguments=json.dumps(args),
            ),
        )
        responses = [
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                tool_calls=[call], content=None,
            ))]),
            SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
                tool_calls=[], content="Shortage results are ready.",
            ))]),
        ]
        calls = []
        def create(**kwargs):
            calls.append(kwargs)
            return responses.pop(0)
        monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ))
        captured = {}
        def dispatch(name, arguments, **__):
            captured["tool_name"] = name
            captured["arguments"] = dict(arguments)
            return {
                "status": "success", "analysis_scope": "organization_wide",
                "total_skills": 0, "returned_skills": 0, "skills": [],
                "reporting_period": {},
            }
        monkeypatch.setattr(agent, "execute_tool", dispatch)
        answer = agent.run_agent(user_message)
        return captured, calls, answer

    broad, broad_calls, _ = invoke(
        "Which skills have the highest workforce shortage?",
        {"skill_name": "Python", "demand_week": "2026-11-13"},
    )
    explicit, _, _ = invoke(
        "Which skills had the highest shortage for reporting week 2026-11-23?",
        {"skill_name": "Python", "demand_week": "2026-11-13"},
    )
    misrouted, _, _ = invoke(
        "Which skills have the highest workforce shortage?",
        {"skill_id": "SKL-000040", "demand_week": "2026-11-13"},
        function_name="compare_workforce_strategies",
    )

    assert broad["tool_name"] == "analyze_skill_shortage"
    assert broad["arguments"] == {}
    assert broad_calls[0]["tool_choice"] == {
        "type": "function", "function": {"name": "analyze_skill_shortage"}
    }
    assert explicit["tool_name"] == "analyze_skill_shortage"
    assert explicit["arguments"] == {"demand_week": "2026-11-23"}
    assert misrouted["tool_name"] == "analyze_skill_shortage"
    assert misrouted["arguments"] == {}


def test_strategy_tool_asks_for_missing_skill_or_week_before_dispatch(monkeypatch):
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    dispatched = []

    def invoke(args):
        call = SimpleNamespace(
            id="strategy-call",
            function=SimpleNamespace(
                name="compare_workforce_strategies",
                arguments=json.dumps(args),
            ),
        )
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[call], content=None,
        ))])
        responses = [response, SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[], content="Here is the strategy comparison.",
        ))])]
        monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: responses.pop(0)))
        ))
        def dispatch(_name, arguments, **__):
            dispatched.append(arguments)
            return {"status": "success", "scenarios": []}
        monkeypatch.setattr(agent, "execute_tool", dispatch)
        return agent.run_agent("Compare workforce strategies for a skill shortage.")

    both_missing = invoke({})
    week_missing = invoke({"skill_id": "SKL-000040"})
    skill_missing = invoke({"demand_week": "2027-05-03"})
    valid = invoke({"skill_id": "SKL-000040", "demand_week": "2027-05-03"})

    assert "skill and demand week" in both_missing
    assert "Which demand week" in week_missing
    assert "Which skill" in skill_missing
    assert len(dispatched) == 1
    assert dispatched[0] == {"skill_id": "SKL-000040", "demand_week": "2027-05-03"}
    assert valid == "Here is the strategy comparison."


def test_full_dataset_two_skill_intersection(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "two-skills",
        [_row("EMP-AB", "Python"), _row("EMP-AB", "Java"), _row("EMP-A", "Python")],
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.find_employees_by_skills(["Python", "Java"])

    assert result["status"] == "success"
    assert result["total_matches"] == 1
    assert result["employees"][0]["employee_id"] == "EMP-AB"
    assert {skill["skill_name"] for skill in result["employees"][0]["skills"]} == {"Python", "Java"}


def test_python_and_machine_learning_search_has_verified_total_and_table(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "python-machine-learning",
        [
            _row("EMP-BOTH", "Python"), _row("EMP-BOTH", "Machine Learning"),
            _row("EMP-PY", "Python"),
        ],
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = execute_tool("find_employees_by_skills", {
        "skill_names": ["Python", "Machine Learning"],
    })
    formatted = agent.format_tool_result("find_employees_by_skills", result)

    assert result["total_matches"] == 1
    assert [row["employee_id"] for row in result["employees"]] == ["EMP-BOTH"]
    assert "1 total matches; 1 displayed" in formatted
    assert "EMP-BOTH" in formatted
    assert "EMP-PY" not in formatted
    assert "| Employee ID | Name | Relevant qualified skills | Weekly capacity |" in formatted


def test_full_dataset_three_skill_intersection(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "three-skills",
        [
            _row("EMP-ALL", "Python"), _row("EMP-ALL", "Streamlit"), _row("EMP-ALL", "FastAPI"),
            _row("EMP-PAIR", "Python"), _row("EMP-PAIR", "Streamlit"),
        ],
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.find_employees_by_skills(["Python", "Streamlit", "FastAPI"])

    assert result["total_matches"] == 1
    assert result["employees"][0]["employee_id"] == "EMP-ALL"


def test_match_beyond_old_single_skill_top_twenty(monkeypatch, tmp_path):
    records = []
    talent_rows = []
    for index in range(21):
        for prefix, skill in (("PY", "Python"), ("JA", "Java")):
            employee_id = f"EMP-{prefix}-{index:02d}"
            records.append(_row(employee_id, skill, level=5))
            talent_rows.append({
                "employee_id": employee_id, "employee_name": employee_id,
                "role_id": "ROLE-ENG", "employment_type": "Full-time",
                "skill_name": skill, "proficiency_level": 5,
                "skill_status": "Current", "is_qualified": True,
                "skill_available_hours": 40, "availability_date": "2027-01-04",
                "available_hours": 40,
            })
    records.extend([_row("EMP-SHARED", "Python", level=3), _row("EMP-SHARED", "Java", level=3)])
    for skill in ("Python", "Java"):
        talent_rows.append({
            "employee_id": "EMP-SHARED", "employee_name": "Shared",
            "role_id": "ROLE-ENG", "employment_type": "Full-time",
            "skill_name": skill, "proficiency_level": 3,
            "skill_status": "Current", "is_qualified": True,
            "skill_available_hours": 1, "availability_date": "2027-01-04",
            "available_hours": 1,
        })
    root = _write_query_root(
        tmp_path / "outside-top-twenty", records, talent_rows=talent_rows
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    old_python = tools.find_internal_talent("Python", limit=20)
    old_java = tools.find_internal_talent("Java", limit=20)
    exact = tools.find_employees_by_skills(["Python", "Java"], limit=1)

    assert "EMP-SHARED" not in {row["employee_id"] for row in old_python["employees"]}
    assert "EMP-SHARED" not in {row["employee_id"] for row in old_java["employees"]}
    assert exact["total_matches"] == 1
    assert exact["employees"][0]["employee_id"] == "EMP-SHARED"


def test_default_multi_skill_count_and_response_limit(monkeypatch, tmp_path):
    records = [_row("EMP-MULTI", "Python"), _row("EMP-MULTI", "Java")]
    records += [_row(f"EMP-SINGLE-{i}", "Python") for i in range(3)]
    root = _write_query_root(tmp_path / "skill-count", records)
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.find_employees_by_skills(limit=1)

    assert result["total_matches"] == 1
    assert result["returned_employees"] == 1
    assert result["truncated"] is False
    assert result["employees"][0]["employee_id"] == "EMP-MULTI"
    assert result["minimum_skill_count"] == 2
    formatted = agent.format_employee_search_result(result)
    assert "1 total matches; 1 displayed" in formatted
    assert "EMP-MULTI" in formatted
    assert "| Employee ID | Name | Relevant qualified skills | Weekly capacity |" in formatted


def test_inactive_stale_and_underqualified_skill_rows_are_excluded(monkeypatch, tmp_path):
    records = [
        _row("EMP-OK", "Python"), _row("EMP-OK", "Java"),
        _row("EMP-INACTIVE", "Python"), _row("EMP-INACTIVE", "Java"),
        _row("EMP-STALE", "Python"), _row("EMP-STALE", "Java", status="Stale", qualified=False),
        _row("EMP-LOW", "Python"), _row("EMP-LOW", "Java", level=2, qualified=False),
    ]
    root = _write_query_root(
        tmp_path / "qualification-filters", records, statuses={"EMP-INACTIVE": "inactive"}
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.find_employees_by_skills(["Python", "Java"])

    assert [employee["employee_id"] for employee in result["employees"]] == ["EMP-OK"]


def test_unknown_skill_and_zero_matches_are_clear(monkeypatch, tmp_path):
    root = _write_query_root(tmp_path / "no-match", [_row("EMP-PY", "Python")])
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    unknown = tools.find_employees_by_skills(["MadeUpSkill"])
    none_found = tools.find_employees_by_skills(["Python", "Java"])

    assert unknown["status"] == "unknown_skills"
    assert unknown["unknown_skills"] == ["MadeUpSkill"]
    assert unknown["total_matches"] == 0
    assert none_found["status"] == "not_found"
    assert none_found["total_matches"] == 0
    assert none_found["employees"] == []


def test_existing_and_new_agent_tools_are_registered_and_dispatched(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "agent-dispatch",
        [_row("EMP-AB", "Python"), _row("EMP-AB", "Java")],
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)
    names = {tool["name"] for tool in agent.WORKFORCE_TOOLS}

    assert names == {
        "analyze_skill_shortage", "find_internal_talent",
        "find_employees_by_skills", "compare_workforce_strategies",
    }
    assert {"analyze_demand_forecast", "analyze_workforce_capacity", "summarize_skill_intelligence"}.isdisjoint(names)
    assert callable(tools.analyze_demand_forecast)
    assert callable(tools.analyze_workforce_capacity)
    assert callable(tools.summarize_skill_intelligence)
    assert "find_employees_by_skills" in agent.TOOL_FUNCTIONS
    result = execute_tool("find_employees_by_skills", {"skill_names": ["Python", "Java"]})
    assert result["status"] == "success"
    assert result["employees"][0]["employee_id"] == "EMP-AB"
    assert "require ALL" in agent.AGENT_INSTRUCTIONS
    assert "analyze_demand_forecast" not in agent.AGENT_INSTRUCTIONS


def test_employee_count_uses_active_workforce_total_without_a_list(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "employee-count",
        [_row("EMP-A", "Python"), _row("EMP-B", "Java"), _row("EMP-C", "Python")],
        statuses={"EMP-C": "inactive"},
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = execute_tool("find_employees_by_skills", {"count_only": True, "limit": 0})

    assert result == {
        "status": "success",
        "query_type": "employee_count",
        "total_employee_count": 2,
        "employees": [],
    }
    assert agent.compact_tool_result("find_employees_by_skills", result)["total_employee_count"] == 2
    assert agent.format_tool_result("find_employees_by_skills", result) == "There are 2 active employees."


def test_employee_tool_payload_is_compact_and_bounded():
    result = {
        "status": "success", "total_matches": 25, "truncated": False,
        "employees": [
            {"employee_id": f"EMP-{i}", "employee_name": f"Person {i}",
             "role_id": "private-role", "employment_type": "Full-time", "skill_count": 2,
             "skills": [{"skill_name": "Python", "proficiency_level": 4,
                         "skill_status": "Current", "is_qualified": True}]}
            for i in range(25)
        ],
    }

    compact = agent.compact_tool_result("find_employees_by_skills", result)

    assert compact["total_matches"] == 25
    assert compact["returned_employees"] == agent.MAX_EMPLOYEE_RESULTS_TO_GROQ
    assert len(compact["employees"]) == agent.MAX_EMPLOYEE_RESULTS_TO_GROQ
    assert compact["employees"][0] == {
        "employee_id": "EMP-0", "employee_name": "Person 0",
        "skills": [{"skill_name": "Python", "proficiency_level": 4}],
        "weekly_capacity": None,
    }
    assert "role_id" not in compact["employees"][0]


def test_employee_formatter_is_deterministic_and_handles_empty_statuses():
    success = agent.format_employee_search_result({
        "status": "success", "total_matches": 4,
        "employees": [{"employee_id": "EMP-7", "employee_name": "A. Person",
                       "skills": [{"skill_name": "Python"}, {"skill_name": "Java"}]}],
    })
    assert "4 total matches" in success
    assert "EMP-7" in success and "A. Person" in success
    assert "Python" in success and "Java" in success
    assert "Not available" in success
    assert "|---|---|---|" in success

    assert "0 total matches" in agent.format_employee_search_result({"status": "not_found"})
    unknown = agent.format_employee_search_result({
        "status": "unknown_skills", "unknown_skills": ["AI Agent"]
    })
    assert "AI Agent" in unknown
    assert "|---|" not in unknown


def test_employee_formatter_shows_weekly_capacity_from_selected_week(monkeypatch, tmp_path):
    root = _write_query_root(
        tmp_path / "employee-weekly-capacity",
        [_row("EMP-CAP", "Python")],
        talent_rows=[{
            "employee_id": "EMP-CAP", "skill_id": "SK-PY",
            "availability_date": "2027-01-04", "available_hours": 35,
            "allocated_hours": 5, "remaining_hours": 30,
            "skill_available_hours": 15,
        }],
    )
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    result = tools.find_employees_by_skills(
        ["Python"], availability_date="2027-01-04",
    )
    formatted = agent.format_employee_search_result(result)

    assert result["employees"][0]["weekly_capacity"] == {
        "available_hours": 35.0, "allocated_hours": 5.0, "remaining_hours": 30.0,
    }
    assert "available 35.0, allocated 5.0, remaining 30.0 hours" in formatted


def test_recent_conversation_context_is_bounded_and_preserves_clarifications():
    history = [
        {"role": "user", "content": "Find employees with Python and AI Agent."},
        {"role": "assistant", "content": "Which skill do you mean by AI Agent?"},
        {"role": "user", "content": "Artificial Intelligence."},
        {"role": "assistant", "content": "I found two employees with both skills."},
        {"role": "user", "content": "Show their proficiency."},
    ]
    recent = agent.bounded_conversation_context(history, max_turns=2, max_chars=200)
    assert [item["role"] for item in recent] == ["assistant", "user", "assistant", "user"]
    assert "Artificial Intelligence" in " ".join(item["content"] for item in recent)
    assert sum(len(item["content"]) for item in recent) <= 200
    assert len(agent.bounded_conversation_context(history, max_turns=2)) <= 4


def test_pending_skill_clarification_preserves_original_skills_and_filters():
    original = "List employees with Python, AI Agent, and SQL available in January"
    clarification_question = "Which skill do you mean by AI Agent?"
    combined = agent.combine_pending_clarification(
        original, "Artificial Intelligence", clarification_question
    )

    assert original in combined
    assert combined.count(original) == 1
    assert clarification_question in combined
    assert "Manager's clarification: Artificial Intelligence" in combined
    assert "SQL" in combined and "available in January" in combined
    assert agent.is_clarification_response("Which skill do you mean by AI Agent?")
    assert not agent.is_clarification_response("I found 3 matching employees.")
    assert not agent.is_new_workforce_question("Artificial Intelligence.")
    assert not agent.is_new_workforce_question("Artificial Intelligence?")
    assert agent.is_new_workforce_question("How many employees are there?")
    assert agent.is_new_workforce_question("List employees with Java")
    assert agent.is_new_workforce_question("I need the employee count")


def test_agent_preserves_bounded_tool_evidence_and_enforces_round_limit(monkeypatch):
    calls = []
    tool_call = SimpleNamespace(
        id="call-1",
        function=SimpleNamespace(name="analyze_skill_shortage", arguments='{"skill_name":"Python"}'),
    )
    tool_message = SimpleNamespace(tool_calls=[tool_call], content=None)

    def create(**kwargs):
        calls.append(deepcopy(kwargs["messages"]))
        return SimpleNamespace(choices=[SimpleNamespace(message=tool_message)])

    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(agent, "execute_tool", lambda *_, **__: {
        "status": "success", "total_periods": 40,
        "records": [{"demand_week": str(i), "recommendation": "detail"} for i in range(40)],
    })

    answer = agent.run_agent("Analyze Python shortage")

    assert len(calls) == agent.MAX_TOOL_ROUNDS
    assert agent.MAX_TOOL_ROUNDS == 6
    assert "40 total periods" in answer
    # Compact tool evidence remains available across later rounds.
    assert calls[1][-1]["content"] != '{"status":"prior_result_compacted"}'
    assert calls[2][-3]["content"] != '{"status":"prior_result_compacted"}'
    assert len(calls[1][-1]["content"]) < 2000


def test_groq_payload_and_rate_limit_errors_are_friendly(monkeypatch):
    class ProviderError(Exception):
        def __init__(self, status_code, message):
            super().__init__(message)
            self.status_code = status_code

    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(
            ProviderError(413, "sensitive provider payload")
        )))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    too_large = agent.run_agent("Large request")
    assert "too large" in too_large
    assert "sensitive provider payload" not in too_large

    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: (_ for _ in ()).throw(
            ProviderError(429, "sensitive provider payload")
        )))
    ))
    limited = agent.run_agent("Rate limited request")
    assert "rate limited" in limited
    assert "sensitive provider payload" not in limited


def test_non_employee_tool_returns_groqs_natural_final_response(monkeypatch):
    tool_call = SimpleNamespace(
        id="shortage-call",
        function=SimpleNamespace(name="analyze_skill_shortage", arguments='{"skill_name":"Python"}'),
    )
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[tool_call], content=None,
        ))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[], content="Groq's concise workforce explanation.",
        ))]),
    ]
    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: responses.pop(0)))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(agent, "execute_tool", lambda *_, **__: {
        "status": "success", "skill_name": "Python", "total_periods": 1,
        "records": [{"demand_week": "2027-01-04", "remaining_gap": 12}],
    })

    answer = agent.run_agent("Analyze Python shortage")

    assert answer == "Groq's concise workforce explanation."


def test_employee_tool_uses_deterministic_results_over_groq_paraphrase(monkeypatch):
    tool_call = SimpleNamespace(
        id="employees-call",
        function=SimpleNamespace(name="find_employees_by_skills", arguments='{"count_only":true}'),
    )
    responses = [
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[tool_call], content=None,
        ))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
            tool_calls=[], content="Groq claims there are 999 employees.",
        ))]),
    ]
    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **_: responses.pop(0)))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(agent, "execute_tool", lambda *_, **__: {
        "status": "success", "query_type": "employee_count",
        "total_employee_count": 12, "employees": [],
    })

    answer = agent.run_agent("How many employees are there?")

    assert answer == "There are 12 active employees."


def test_provider_failure_after_tool_preserves_verified_local_result(monkeypatch):
    class ProviderError(Exception):
        status_code = 413

    tool_call = SimpleNamespace(
        id="employee-call",
        function=SimpleNamespace(
            name="find_employees_by_skills",
            arguments='{"skill_names":["Python","Machine Learning"]}',
        ),
    )
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[tool_call], content=None))])
    call_count = {"value": 0}

    def create(**_):
        call_count["value"] += 1
        if call_count["value"] == 1:
            return response
        raise ProviderError("temporary provider issue")

    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(agent, "execute_tool", lambda *_, **__: {
        "status": "success", "requested_skills": ["Python", "Machine Learning"],
        "match_mode": "all", "total_matches": 1, "truncated": False,
        "employees": [{
            "employee_id": "EMP-VERIFIED", "employee_name": "Verified Person",
            "skills": [
                {"skill_name": "Python", "proficiency_level": 4},
                {"skill_name": "Machine Learning", "proficiency_level": 3},
            ],
        }],
    })

    answer = agent.run_agent("Find employees with Python and Machine Learning")

    assert "EMP-VERIFIED" in answer
    assert "1 total matches; 1 displayed" in answer
    assert "too large" in answer
    assert "verified local tool output" in answer


def test_organization_shortage_ranking_survives_provider_413(monkeypatch):
    class ProviderError(Exception):
        status_code = 413

    tool_call = SimpleNamespace(
        id="org-shortage-call",
        function=SimpleNamespace(name="analyze_skill_shortage", arguments="{}"),
    )
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        tool_calls=[tool_call], content=None,
    ))])
    calls = {"count": 0}

    def create(**_):
        calls["count"] += 1
        if calls["count"] == 1:
            return response
        raise ProviderError("payload details must stay hidden")

    monkeypatch.setattr(agent, "get_groq_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    ))
    monkeypatch.setenv("GROQ_MODEL", "test-model")
    monkeypatch.setattr(agent, "execute_tool", lambda *_, **__: {
        "status": "success", "analysis_scope": "organization_wide",
        "total_skills": 1, "returned_skills": 1,
        "reporting_period": {"start_week": "2027-01-04", "end_week": "2027-01-11"},
        "skills": [{
            "skill_name": "Python", "cumulative_remaining_gap_hours": 15,
            "weekly_details": [{"demand_week": "2027-01-04", "remaining_gap_hours": 15}],
        }],
    })

    answer = agent.run_agent("Which skills have the highest workforce shortage?")

    assert "Organization-wide shortage ranking" in answer
    assert "Python" in answer and "15" in answer
    assert "too large" in answer
    assert "payload details must stay hidden" not in answer


def test_shortage_and_strategy_tools_remain_dispatchable(monkeypatch):
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "analyze_skill_shortage", lambda **_: {
        "status": "success", "records": [{"skill_id": "SK-1", "gap_hours": 10}]
    })
    monkeypatch.setitem(agent.TOOL_FUNCTIONS, "compare_workforce_strategies", lambda **_: {
        "status": "success", "scenarios": [{"strategy": "training"}]
    })
    assert execute_tool("analyze_skill_shortage", {"skill_name": "Python"})["records"][0]["skill_id"] == "SK-1"
    assert execute_tool("compare_workforce_strategies", {"skill_id": "SK-1", "demand_week": "2027-01-04"})["scenarios"][0]["strategy"] == "training"


def test_strategy_comparison_keeps_valid_recommendation_pair(monkeypatch):
    from engine import what_if_simulator

    recommendations = pd.DataFrame([{
        "skill_id": "SKL-000040", "demand_week": "2027-05-03",
    }])
    monkeypatch.setattr(what_if_simulator, "load_data", lambda: {
        "recommendations": recommendations,
    })
    seen = []
    scenarios = pd.DataFrame([{
        "strategy": "Internal Reallocation", "hours_resolved": 10,
        "remaining_gap": 5, "estimated_cost": 0,
    }])
    def compare(data, demand_week, skill_id):
        seen.append((demand_week, skill_id))
        return scenarios
    monkeypatch.setattr(what_if_simulator, "compare_scenarios", compare)

    result = tools.compare_workforce_strategies("SKL-000040", "2027-05-03")

    assert result["status"] == "success"
    assert seen == [("2027-05-03", "SKL-000040")]
    assert result["scenarios"][0]["strategy"] == "Internal Reallocation"


def test_strategy_comparison_returns_controlled_no_match(monkeypatch):
    from engine import what_if_simulator

    monkeypatch.setattr(what_if_simulator, "load_data", lambda: {
        "recommendations": pd.DataFrame([{
            "skill_id": "SKL-000040", "demand_week": "2027-05-03",
        }]),
    })
    calls = []
    monkeypatch.setattr(what_if_simulator, "compare_scenarios", lambda *_: calls.append(True))

    result = tools.compare_workforce_strategies("SKL-000040", "2026-11-13")

    assert result["status"] == "not_found"
    assert result["message"] == "No workforce recommendation exists for the requested skill and demand week."
    assert calls == []


def test_employee_advanced_filters_are_local_and_weekly(monkeypatch, tmp_path):
    records = [
        _row("EMP-1", "Python", 4), _row("EMP-1", "Java", 5),
        _row("EMP-2", "Python", 3), _row("EMP-2", "Java", 3),
        _row("EMP-3", "Python", 2, qualified=False),
        _row("EMP-4", "Python", 4), _row("EMP-4", "FastAPI", 4),
    ]
    weekly = []
    for employee_id, skill_names, remaining, skill_hours in (
        ("EMP-1", ("Python", "Java"), 20, 10),
        ("EMP-2", ("Python", "Java"), 18, 9),
        ("EMP-4", ("Python", "FastAPI"), 30, 15),
    ):
        for skill_name in skill_names:
            weekly.append({
                "employee_id": employee_id,
                "skill_id": {"Python": "SK-PY", "Java": "SK-JAVA", "FastAPI": "SK-FAST"}[skill_name],
                "availability_date": "2027-01-04", "available_hours": 35,
                "allocated_hours": 5, "remaining_hours": remaining,
                "skill_available_hours": skill_hours,
            })
    root = _write_query_root(tmp_path / "employee-filters", records, talent_rows=weekly)
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    greater_than_two = tools.find_employees_by_skills(
        ["Python"], proficiency_operator="gt", proficiency_value=2,
    )
    in_range = tools.find_employees_by_skills(
        ["Python"], proficiency_operator="range", proficiency_min=3, proficiency_max=4,
    )
    without_java = tools.find_employees_by_skills(["Python"], exclude_skill_names=["Java"])
    sorted_all = tools.find_employees_by_skills(
        ["Python", "Java"], sort_by="proficiency", sort_order="desc",
    )
    capacity_filtered = tools.find_employees_by_skills(
        ["Python", "FastAPI"], availability_date="2027-01-04",
        minimum_skill_available_hours=10, minimum_remaining_hours=25,
    )

    assert {row["employee_id"] for row in greater_than_two["employees"]} == {"EMP-1", "EMP-2", "EMP-4"}
    assert {row["employee_id"] for row in in_range["employees"]} == {"EMP-1", "EMP-2", "EMP-4"}
    assert [row["employee_id"] for row in without_java["employees"]] == ["EMP-4"]
    assert [row["employee_id"] for row in sorted_all["employees"]] == ["EMP-1", "EMP-2"]
    assert [row["employee_id"] for row in capacity_filtered["employees"]] == ["EMP-4"]
    assert capacity_filtered["employees"][0]["weekly_capacity"]["remaining_hours"] == 30
    assert tools.find_employees_by_skills(
        ["Python"], minimum_remaining_hours=10,
    )["status"] == "date_required"


def test_read_only_forecast_capacity_and_skill_intelligence_wrappers(monkeypatch, tmp_path):
    root = Path(tmp_path)
    (root / "raw").mkdir(parents=True)
    (root / "processed").mkdir()
    pd.DataFrame([
        {"skill_id": "SK-PY", "skill_name": "Python"},
        {"skill_id": "SK-JAVA", "skill_name": "Java"},
    ]).to_csv(root / "raw" / "skills.csv", index=False)
    pd.DataFrame([
        {"employee_id": "E1", "status": "active"},
        {"employee_id": "E2", "status": "active"},
        {"employee_id": "E3", "status": "inactive"},
    ]).to_csv(root / "raw" / "employees.csv", index=False)
    pd.DataFrame([
        {"demand_week": "2027-01-04", "skill_id": "SK-PY", "committed_hours": 10, "proposed_hours": 5, "expected_hours": 15},
        {"demand_week": "2027-01-04", "skill_id": "SK-JAVA", "committed_hours": 20, "proposed_hours": 0, "expected_hours": 20},
    ]).to_csv(root / "processed" / "demand_forecast.csv", index=False)
    pd.DataFrame([
        {"availability_date": "2027-01-04", "available_hours": 30, "allocated_hours": 10, "remaining_hours": 20},
        {"availability_date": "2027-01-04", "available_hours": 20, "allocated_hours": 5, "remaining_hours": 15},
    ]).to_csv(root / "processed" / "capacity_analysis.csv", index=False)
    pd.DataFrame([
        {"demand_week": "2027-01-04", "skill_id": "SK-PY", "required_hours": 25, "available_hours": 15, "gap_hours": 10, "gap_status": "Shortage", "qualified_employees": 2},
    ]).to_csv(root / "processed" / "skill_gap_analysis.csv", index=False)
    pd.DataFrame([
        {"employee_id": "E1", "skill_id": "SK-PY", "proficiency_level": 4, "skill_status": "Current", "is_qualified": True},
        {"employee_id": "E2", "skill_id": "SK-PY", "proficiency_level": 3, "skill_status": "Current", "is_qualified": True},
        {"employee_id": "E2", "skill_id": "SK-JAVA", "proficiency_level": 5, "skill_status": "Current", "is_qualified": True},
        {"employee_id": "E3", "skill_id": "SK-JAVA", "proficiency_level": 5, "skill_status": "Current", "is_qualified": True},
    ]).to_csv(root / "processed" / "skill_intelligence.csv", index=False)
    monkeypatch.setattr(tools, "get_data_root", lambda: root)

    forecast = tools.analyze_demand_forecast()
    capacity = tools.analyze_workforce_capacity(skill_names=["Python"], demand_week="2027-01-04")
    intelligence = tools.summarize_skill_intelligence(["Python"])

    assert forecast["skills"][0]["skill_name"] == "Java"
    assert forecast["skills"][0]["expected_hours"] == 20
    assert capacity["weekly_capacity"][0] == {
        "availability_date": "2027-01-04", "available_hours": 50.0,
        "allocated_hours": 15.0, "remaining_hours": 35.0,
    }
    assert capacity["skill_gaps"][0]["skill_available_hours"] == 15
    assert intelligence["skills"][0]["qualified_employee_count"] == 2
    assert intelligence["skills"][0]["proficiency_distribution"] == {"3": 1, "4": 1}


def test_compact_shortage_results_preserve_both_shapes():
    organization = agent.compact_tool_result("analyze_skill_shortage", {
        "status": "success", "analysis_scope": "organization_wide", "total_skills": 9,
        "returned_skills": 5, "skills": [{"skill_name": "Python", "weekly_details": list(range(8))}],
    })
    named = agent.compact_tool_result("analyze_skill_shortage", {
        "status": "success", "total_periods": 20,
        "records": [{"demand_week": str(index)} for index in range(20)],
    })
    assert len(organization["skills"]) == 1
    assert len(organization["skills"][0]["weekly_details"]) == 5
    assert "records" not in organization and organization["truncated"] is True
    assert len(named["records"]) == 12
    assert named["returned_periods"] == 12 and named["truncated"] is True


def test_error_alert_styles_set_contrasting_background_and_foreground():
    app_css = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")

    assert '[data-testid="stAlert"][kind="error"]' in app_css
    assert "#fff1f0" in app_css
    assert "#7f1d1d" in app_css


def test_assistant_markdown_tables_have_theme_independent_contrast():
    app_css = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")

    assert '.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] table' in app_css
    assert "background-color: #ffffff !important;" in app_css
    assert "background-color: #e2e8f0 !important;" in app_css
    assert "background-color: #f8fafc !important;" in app_css
    assert "color: #10243a !important;" in app_css
    assert "border: 1px solid #cbd5e1 !important;" in app_css
