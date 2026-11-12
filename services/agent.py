

import json
import logging
import os
import re
import uuid

AGENT_INSTRUCTIONS = """
You are WorkForceIQ, a helpful workforce intelligence assistant. Answer
conversationally and clearly, using local workforce tools whenever a claim
depends on workforce data. Never invent data or claim a simulated strategy
has allocated employees.

Available tools:
- analyze_skill_shortage: analyze a named skill or, when skill_name is
  omitted, rank all skills by cumulative weekly remaining_gap.
- find_internal_talent: find qualified internal candidates for one skill,
  optionally filtered by availability date and proficiency.
- find_employees_by_skills: search all active employees' current qualified
  skills, return an active employee count, or find employees with a minimum
  number of qualified skills.
- compare_workforce_strategies: compare simulated strategies for a skill ID
  and demand week; it does not create allocations.

For multiple named skills, use find_employees_by_skills and require ALL
unless the user explicitly requests ANY. Use exact workforce skill names;
do not guess or silently substitute a related skill. Interpret “more than
one skill” as at least two distinct current qualified skills. For an
employee-count question, use count_only=true without a result limit.
Broad shortage questions use analyze_skill_shortage without skill_name;
named skill and optional week requests retain their specific scope.
Pass demand_week only when the user explicitly specifies a reporting date;
never infer or insert a week. Strategy comparisons require both a skill ID
and demand week. Use a skill ID grounded in workforce tool results, and ask
for missing skill or week information rather than guessing.

Use the stated defaults and ask only for information needed to resolve a
genuine ambiguity. Preserve original filters when a user answers a
clarification, replacing only the clarified term with an exact workforce
skill name. Use tool evidence for workforce claims and display costs in INR.
Respond naturally; keep explanations concise and distinguish estimates from
confirmed employee data.
"""

from services.tools import (
    analyze_skill_shortage,
    find_internal_talent,
    find_employees_by_skills,
    compare_workforce_strategies,
)

from services.llm_service import get_groq_client


# Keep the original workforce tool schemas.
WORKFORCE_TOOLS = [
    {
        "name": "analyze_skill_shortage",
        "description": (
            "Analyze workforce shortages. If skill_name is omitted, rank all "
            "skills by cumulative remaining_gap hours across the reporting "
            "period and return the top five. Supply skill_name for the "
            "existing single-skill analysis. Pass demand_week only when the "
            "user explicitly specifies a reporting date."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "skill_name": {
                    "type": "STRING",
                    "description": "Name of the workforce skill."
                },
                "demand_week": {
                    "type": "STRING",
                    "description": "Optional demand week in YYYY-MM-DD format."
                }
            },
            "required": []
        }
    },
    {
        "name": "find_internal_talent",
        "description": (
            "Find qualified internal employees for a skill "
            "based on proficiency and availability."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "skill_name": {
                    "type": "STRING",
                    "description": "Name of the workforce skill."
                },
                "availability_date": {
                    "type": "STRING",
                    "description": "Optional availability date in YYYY-MM-DD format."
                },
                "min_proficiency": {
                    "type": "INTEGER",
                    "description": "Minimum skill proficiency level."
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum number of employees to return."
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "find_employees_by_skills",
        "description": (
            "Search the complete configured workforce dataset for employees "
            "qualified in all or any named skills, or for employees with at "
            "least N distinct current, qualified skills. Returns employee IDs, "
            "verified current skill details, and the total match count. For a "
            "total active employee count without a list, use count_only=true."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "skill_names": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Optional skill names. Multiple names match all by default; use match_mode='any' only when requested."
                },
                "match_mode": {
                    "type": "STRING",
                    "enum": ["all", "any"],
                    "description": "Whether employees must have all or any named skills. Defaults to all."
                },
                "minimum_skill_count": {
                    "type": "INTEGER",
                    "description": "Minimum number of distinct current, qualified skills; defaults to 2 when no names are specified."
                },
                "count_only": {
                    "type": "BOOLEAN",
                    "description": "Return only the total number of active employees; use for workforce employee-count questions."
                },
                "limit": {
                    "type": "INTEGER",
                    "description": "Maximum employees returned after the complete matching set and total count are calculated."
                },
                "exclude_skill_names": {
                    "type": "ARRAY", "items": {"type": "STRING"},
                    "description": "Exclude employees with any of these exact current qualified skills."
                },
                "proficiency_operator": {
                    "type": "STRING", "enum": ["gt", "gte", "lt", "lte", "range"],
                    "description": "Comparison applied locally to proficiency."
                },
                "proficiency_value": {"type": "INTEGER", "description": "Threshold for gt/gte/lt/lte."},
                "proficiency_min": {"type": "INTEGER", "description": "Inclusive lower bound for a proficiency range."},
                "proficiency_max": {"type": "INTEGER", "description": "Inclusive upper bound for a proficiency range."},
                "sort_by": {"type": "STRING", "enum": ["employee_id", "proficiency"], "description": "Sort by employee ID or average proficiency across relevant skills."},
                "sort_order": {"type": "STRING", "enum": ["asc", "desc"]},
                "availability_date": {"type": "STRING", "description": "Optional availability week, YYYY-MM-DD."},
                "minimum_skill_available_hours": {"type": "NUMBER", "description": "Minimum per-skill available hours for availability_date."},
                "minimum_remaining_hours": {"type": "NUMBER", "description": "Minimum overall remaining capacity for availability_date."}
            },
            "required": []
        }
    },
    {
        "name": "compare_workforce_strategies",
        "description": (
            "Compare internal reallocation, employee training, "
            "external hiring, and combined workforce strategies."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "skill_id": {
                    "type": "STRING",
                    "description": "Unique workforce skill ID."
                },
                "demand_week": {
                    "type": "STRING",
                    "description": "Demand week in YYYY-MM-DD format."
                }
            },
            "required": ["skill_id", "demand_week"]
        }
    }
]


def normalize_schema(value):
    """Convert schema types to JSON Schema types."""

    type_mapping = {
        "OBJECT": "object",
        "STRING": "string",
        "INTEGER": "integer",
        "NUMBER": "number",
        "BOOLEAN": "boolean",
        "ARRAY": "array"
    }

    if isinstance(value, dict):
        return {
            key: normalize_schema(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [normalize_schema(item) for item in value]

    if isinstance(value, str):
        return type_mapping.get(value, value)

    return value


TOOL_DECLARATIONS = [
    {
        "type": "function",
        "function": {
            "name": tool["name"],
            "description": tool["description"],
            "parameters": normalize_schema(tool["parameters"])
        }
    }
    for tool in WORKFORCE_TOOLS
]


TOOL_FUNCTIONS = {
    "analyze_skill_shortage": analyze_skill_shortage,
    "find_internal_talent": find_internal_talent,
    "find_employees_by_skills": find_employees_by_skills,
    "compare_workforce_strategies": compare_workforce_strategies
}

MAX_TOOL_ROUNDS = 6
MAX_EMPLOYEE_RESULTS_TO_GROQ = 8
MAX_EMPLOYEE_RESULTS_TO_DISPLAY = 50
logger = logging.getLogger(__name__)


def bounded_conversation_context(chat_messages, max_turns=3, max_chars=3600):
    """Keep only a small recent context window; never forward the full transcript."""
    selected = []
    remaining = max_chars
    for message in (chat_messages or [])[-max_turns * 2:]:
        role = message.get("role")
        content = message.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or remaining <= 0:
            continue
        content = content.strip()[:min(1200, remaining)]
        if content:
            selected.append({"role": role, "content": content})
            remaining -= len(content)
    return selected


def combine_pending_clarification(original_question, clarification, assistant_question=None):
    """Retain the original workforce request when the user answers a clarification."""
    original = str(original_question or "").strip()
    answer = str(clarification or "").strip()
    if not original:
        return answer
    if not answer:
        return original
    context = f"Original workforce request: {original}\n"
    if assistant_question:
        context += f"Assistant's clarification question: {str(assistant_question).strip()}\n"
    return context + (
        f"Manager's clarification: {answer}\n"
        "Continue the original request, retaining all other skills and filters."
    )


def is_clarification_response(answer):
    """Identify explicit assistant clarification questions for UI session state."""
    text = str(answer or "").casefold()
    if "?" not in text:
        return False
    return any(marker in text for marker in (
        "clarify", "which skill", "which one", "what do you mean",
        "did you mean", "could you specify", "please specify",
    ))


def is_new_workforce_question(prompt):
    """Recognize a new request so it is not consumed as a clarification answer."""
    text = str(prompt or "").strip().casefold()
    return bool(re.match(
        r"^(how|what|which|who|where|when|why|show|list|find|give|tell|"
        r"analy[sz]e|compare|count|do|does|can|could|is|are|please\s+"
        r"(show|list|find|give|compare|analy[sz]e)|i\s+(need|want)|"
        r"(new|another|separate)\s+question)\b",
        text,
    ))


def is_organization_wide_shortage_request(prompt):
    """Identify broad skill-shortage rankings that must use the shortage tool."""
    text = str(prompt or "").casefold()
    if not re.search(r"\bshortages?\b", text):
        return False
    if re.search(r"\b(compare|comparison)\b.{0,40}\bstrateg(?:y|ies)\b", text):
        return False
    asks_about_multiple_skills = bool(re.search(r"\bskills\b", text))
    asks_for_scope_or_ranking = bool(re.search(
        r"\b(all|across|organization(?:-wide)?|highest|top|rank\w*|most|which)\b", text
    ))
    return asks_about_multiple_skills and asks_for_scope_or_ranking


def compact_tool_result(function_name, result):
    """Bound data sent to Groq while retaining status and complete totals."""
    if not isinstance(result, dict):
        return {"status": "error", "message": "Tool returned an invalid result."}
    if function_name == "find_employees_by_skills":
        employees = result.get("employees", [])
        return {
            key: result[key] for key in (
                "status", "message", "unknown_skills", "requested_skills",
                "match_mode", "minimum_skill_count", "total_matches",
                "truncated", "query_type", "total_employee_count",
            ) if key in result
        } | {"employees": [
            {
                "employee_id": employee.get("employee_id"),
                "employee_name": employee.get("employee_name"),
                "skills": [{key: skill.get(key) for key in (
                    "skill_name", "proficiency_level", "skill_available_hours"
                ) if key in skill} for skill in employee.get("skills", [])],
                "weekly_capacity": employee.get("weekly_capacity"),
            }
            for employee in employees[:MAX_EMPLOYEE_RESULTS_TO_GROQ]
        ], "returned_employees": min(len(employees), MAX_EMPLOYEE_RESULTS_TO_GROQ),
            "display_note": "Employee records are verified; total_matches covers the full dataset."}
    if function_name == "find_internal_talent":
        employees = result.get("employees", [])
        compact = {key: value for key, value in result.items() if key != "employees"}
        compact["employees"] = [
            {key: employee.get(key) for key in (
                "employee_id", "employee_name", "skill_name", "proficiency_level",
                "availability_date", "available_hours", "allocated_hours",
                "remaining_hours", "estimated_skill_hours",
            ) if key in employee}
            for employee in employees[:5]
        ]
        compact["returned_employees"] = len(compact["employees"])
        compact["truncated"] = len(employees) > 5 or bool(result.get("total_qualified_employees", 0) > 5)
        return compact
    if function_name == "analyze_skill_shortage":
        if "skills" in result:
            skills = result.get("skills", [])
            compact = {key: value for key, value in result.items() if key != "skills"}
            compact["skills"] = [
                {**skill, "weekly_details": skill.get("weekly_details", [])[:5]}
                for skill in skills[:5]
            ]
            compact["returned_skills"] = len(compact["skills"])
            compact["truncated"] = result.get("total_skills", len(skills)) > len(compact["skills"])
            return compact
        if "records" in result:
            records = result.get("records", [])
            compact = {key: value for key, value in result.items() if key != "records"}
            compact["records"] = records[:12]
            compact["returned_periods"] = len(compact["records"])
            compact["truncated"] = result.get("total_periods", len(records)) > len(compact["records"])
            return compact
        return result
    array_fields = {
        "analyze_demand_forecast": ("skills", 5),
        "analyze_workforce_capacity": ("weekly_capacity", 10),
        "summarize_skill_intelligence": ("skills", 10),
    }
    if function_name in array_fields:
        field, limit = array_fields[function_name]
        compact = dict(result)
        if field in compact:
            values = compact[field]
            compact[field] = values[:limit]
            compact[f"returned_{field}"] = len(compact[field])
            compact[f"truncated_{field}"] = len(values) > limit
        if function_name == "analyze_workforce_capacity" and "skill_gaps" in compact:
            gaps = compact["skill_gaps"]
            compact["skill_gaps"] = gaps[:10]
            compact["returned_skill_gaps"] = len(compact["skill_gaps"])
            compact["truncated_skill_gaps"] = len(gaps) > 10
        return compact
    return result


def _md(value):
    return str(value if value is not None else "").replace("|", "\\|").replace("\n", " ")


def _render_table(headers, rows):
    if not rows:
        return "No matching records."
    return "\n".join([
        "| " + " | ".join(headers) + " |",
        "|" + "|".join("---" for _ in headers) + "|",
        *("| " + " | ".join(_md(value) for value in row) + " |" for row in rows),
    ])


def format_employee_search_result(result):
    status = result.get("status")
    if status == "success" and result.get("query_type") == "employee_count":
        return f"There are {int(result.get('total_employee_count', 0))} active employees."
    if status == "unknown_skills":
        return "Unknown skill(s): " + ", ".join(result.get("unknown_skills", [])) + "."
    if status == "ambiguous_skills":
        return "Ambiguous skill name(s): " + ", ".join(result.get("ambiguous_skills", [])) + "."
    if status == "date_required":
        return result.get("message", "Provide a reporting week to apply the requested capacity filters.")
    if status == "not_found":
        return "No employees matched the current, qualified skill filters (0 total matches; 0 displayed)."
    if status != "success":
        return result.get("message", "Employee search could not be completed.")
    employees = result.get("employees", [])[:MAX_EMPLOYEE_RESULTS_TO_DISPLAY]
    total = int(result.get("total_matches", 0))
    rows = []
    for employee in employees:
        skill_labels = []
        for skill in employee.get("skills", []):
            label = str(skill.get("skill_name") or "")
            if skill.get("proficiency_level") is not None:
                label += f" (level {skill['proficiency_level']})"
            if skill.get("skill_available_hours") is not None:
                label += f", {skill['skill_available_hours']} skill hours"
            if label:
                skill_labels.append(label)
        skills = "; ".join(skill_labels)
        capacity = employee.get("weekly_capacity") or {}
        capacity_parts = [
            f"{label} {capacity[key]}"
            for key, label in (
                ("available_hours", "available"),
                ("allocated_hours", "allocated"),
                ("remaining_hours", "remaining"),
            )
            if capacity.get(key) is not None and str(capacity.get(key)).strip()
        ]
        capacity_text = (
            f"{', '.join(capacity_parts)} hours" if capacity_parts else "Not available"
        )
        rows.append((employee.get("employee_id"), employee.get("employee_name") or "Name unavailable",
                     skills, capacity_text))
    if not rows:
        return f"{total} total matching employees; 0 displayed."
    return "Employee search — " + str(total) + " total matches; " + str(len(rows)) + " displayed.\n\n" + _render_table(
        ["Employee ID", "Name", "Relevant qualified skills", "Weekly capacity"], rows
    )


def format_talent_result(result):
    if result.get("status") == "unknown_skills":
        return "Unknown skill(s): " + ", ".join(result.get("unknown_skills", [])) + "."
    if result.get("status") == "not_found":
        return "No qualified internal talent matched that skill and availability filter (0 total matches; 0 displayed)."
    if result.get("status") != "success":
        return result.get("message", "Internal talent search could not be completed.")
    employees = result.get("employees", [])
    rows = [(
        row.get("employee_id"), row.get("employee_name") or "Name unavailable",
        f"{row.get('skill_name')} (level {row.get('proficiency_level')})",
        row.get("availability_date"), row.get("available_hours"),
        row.get("remaining_hours"), row.get("estimated_skill_hours"),
    ) for row in employees]
    return (f"Internal talent — {result.get('total_qualified_employees', 0)} total matches; "
            f"{len(rows)} displayed.\n\n" + _render_table(
                ["Employee ID", "Name", "Skill", "Week", "Available hours", "Remaining capacity", "Skill available hours"], rows
            ))


def format_shortage_result(result):
    if result.get("status") != "success":
        return result.get("message", "No workforce shortage records matched the request.")
    if result.get("analysis_scope") == "organization_wide":
        period = result.get("reporting_period", {})
        rows = []
        for rank, skill in enumerate(result.get("skills", []), 1):
            details = "; ".join(
                f"{item.get('demand_week')}: {item.get('remaining_gap_hours')} h"
                for item in skill.get("weekly_details", [])
            )
            rows.append((rank, skill.get("skill_name"), skill.get("cumulative_remaining_gap_hours"),
                         f"{period.get('start_week')}–{period.get('end_week')}", details))
        title = (f"Organization-wide shortage ranking — {result.get('total_skills', 0)} total skills; "
                 f"{len(rows)} displayed. Cumulative weekly remaining gap.\n\n")
        return title + _render_table(["Rank", "Skill", "Cumulative remaining gap (hours)", "Reporting period", "Largest weekly gaps"], rows)
    records = result.get("records", [])[:12]
    rows = [(row.get("demand_week"), row.get("skill_name"), row.get("gap_hours"),
             row.get("internal_available_hours"), row.get("remaining_gap"), row.get("recommendation"))
            for row in records]
    return (f"{result.get('skill_name')} shortage — {result.get('total_periods', 0)} total periods; "
            f"{len(rows)} displayed.\n\n" + _render_table(
                ["Week", "Skill", "Demand gap (hours)", "Internal hours", "Remaining gap (hours)", "Recommendation"], rows
            ))


def format_tool_result(function_name, result):
    if function_name == "find_employees_by_skills":
        return format_employee_search_result(result)
    if function_name == "find_internal_talent":
        return format_talent_result(result)
    if function_name == "analyze_skill_shortage":
        return format_shortage_result(result)
    if result.get("status") in {"unknown_skills", "ambiguous_skills", "not_found", "date_required", "error"}:
        return result.get("message") or f"{function_name.replace('_', ' ').title()} returned no matching data."
    if function_name == "compare_workforce_strategies":
        rows = [(x.get("strategy"), x.get("hours_resolved"), x.get("estimated_cost"), x.get("remaining_gap"))
                for x in result.get("scenarios", [])]
        return "Workforce strategy comparison (simulation only; no allocations made).\n\n" + _render_table(
            ["Strategy", "Hours resolved", "Estimated cost (INR)", "Remaining gap (hours)"], rows
        )
    if function_name == "analyze_demand_forecast":
        rows = [(x.get("skill_name"), x.get("expected_hours"), x.get("committed_hours"),
                 x.get("proposed_hours"), x.get("weeks_included")) for x in result.get("skills", [])]
        period = result.get("reporting_period", {})
        return (f"Demand forecast — {result.get('total_skills', 0)} total skills; {len(rows)} displayed; "
                f"{period.get('start_week')}–{period.get('end_week')}.\n\n" + _render_table(
                    ["Skill", "Expected hours", "Committed hours", "Proposed hours", "Weeks"], rows
                ))
    if function_name == "analyze_workforce_capacity":
        week_rows = [(x.get("availability_date"), x.get("available_hours"), x.get("allocated_hours"), x.get("remaining_hours"))
                     for x in result.get("weekly_capacity", [])]
        gap_rows = [(x.get("demand_week"), x.get("skill_name"), x.get("required_hours"),
                     x.get("skill_available_hours"), x.get("gap_hours"), x.get("gap_status"))
                    for x in result.get("skill_gaps", [])]
        return ("Weekly organization capacity — available, allocated and remaining hours are distinct.\n\n" +
                _render_table(["Week", "Available", "Allocated", "Remaining"], week_rows) +
                "\n\nSkill-level demand gaps (skill-specific available hours):\n\n" +
                _render_table(["Week", "Skill", "Required", "Skill available", "Gap", "Status"], gap_rows))
    if function_name == "summarize_skill_intelligence":
        rows = [(x.get("skill_name"), x.get("qualified_employee_count"),
                 ", ".join(f"Level {level}: {count}" for level, count in sorted(
                     x.get("proficiency_distribution", {}).items(), key=lambda item: int(item[0])
                 ))) for x in result.get("skills", [])]
        return (f"Qualified skill intelligence — {result.get('total_skills', 0)} total skills; {len(rows)} displayed.\n\n" +
                _render_table(["Skill", "Qualified active employees", "Observed proficiency levels"], rows))
    return "The workforce query completed, but no deterministic display formatter is available for this result."


def _format_local_tool_results(tool_results):
    return "\n\n".join(
        format_tool_result(name, result) for name, result in tool_results
    )


def _final_tool_response(assistant_content, tool_results):
    """Keep Groq's explanation while rendering employee data deterministically."""
    employee_results = [
        (name, result) for name, result in tool_results
        if name == "find_employees_by_skills"
    ]
    other_results = [
        (name, result) for name, result in tool_results
        if name != "find_employees_by_skills"
    ]
    verified_employees = _format_local_tool_results(employee_results)
    if employee_results and not other_results:
        return verified_employees
    explanation = str(assistant_content or "").strip()
    if employee_results:
        return (explanation + "\n\n" if explanation else "") + verified_employees
    return explanation or _format_local_tool_results(tool_results)


def _provider_error_message(error, correlation_id=None):
    status = getattr(error, "status_code", getattr(error, "status", None))
    raw_code = getattr(error, "code", None)
    if raw_code is None and isinstance(getattr(error, "body", None), dict):
        body_error = error.body.get("error")
        if isinstance(body_error, dict):
            raw_code = body_error.get("code")
    safe_code = str(raw_code)[:80] if raw_code is not None and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(raw_code)) else None
    try:
        safe_status = int(status) if status is not None else None
    except (TypeError, ValueError):
        safe_status = None
    logger.error(
        "Groq request failed correlation_id=%s exception_class=%s status=%s error_code=%s",
        correlation_id or "unassigned", type(error).__name__, safe_status, safe_code,
    )
    status = safe_status
    message = str(error).casefold()
    reference = f" Reference ID: {correlation_id}." if correlation_id else ""
    if status == 413 or "413" in message or "request too large" in message or "context length" in message:
        return "This workforce request is too large to process at once. Please narrow the skills, date range, or requested detail." + reference
    if status == 429 or "429" in message or "rate limit" in message or "too many requests" in message:
        return "The workforce assistant is temporarily rate limited. Please wait briefly and try again." + reference
    if status in {401, 403} or "authentication" in message or "unauthorized" in message or "invalid api key" in message or "missing api key" in message:
        return "The workforce assistant is not authenticated. Please check its server configuration." + reference
    error_name = type(error).__name__.casefold()
    if "connection" in error_name or "connect" in error_name or "timeout" in error_name or "network" in error_name or isinstance(error, (ConnectionError, TimeoutError)):
        return "The workforce service could not be reached. Please try again shortly." + reference
    return "The workforce assistant could not complete this request. Please try again." + reference


def execute_tool(function_name, arguments, correlation_id=None):

    if function_name not in TOOL_FUNCTIONS:
        return {
            "status": "error",
            "message": f"Unknown tool: {function_name}"
        }

    try:
        tool_function = TOOL_FUNCTIONS[function_name]
        return tool_function(**arguments)

    except Exception as error:
        logger.error(
            "Workforce tool failed correlation_id=%s tool=%s exception_class=%s",
            correlation_id or "unassigned", function_name, type(error).__name__,
        )
        return {
            "status": "error",
            "message": "The workforce data query failed. No match conclusion was produced."
        }



def run_agent(user_message, conversation_context=None):
    """
    Run WorkForceIQ using Groq and its workforce tools.
    """

    model = os.getenv("GROQ_MODEL")

    if not model:
        return "The workforce assistant is not configured with a model. Please check server configuration."

    correlation_id = uuid.uuid4().hex
    try:
        client = get_groq_client()
    except Exception as error:
        return _provider_error_message(error, correlation_id)

    messages = [
        {
            "role": "system",
            "content": AGENT_INSTRUCTIONS
        },
        *bounded_conversation_context(conversation_context),
        {
            "role": "user",
            "content": user_message
        }
    ]
    organization_wide_shortage = is_organization_wide_shortage_request(user_message)

    tool_results = []
    # Keep each bounded result for subsequent reasoning; do not erase evidence
    # that a later capacity or strategy step depends on.
    for round_index in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOL_DECLARATIONS,
                tool_choice=(
                    {"type": "function", "function": {"name": "analyze_skill_shortage"}}
                    if organization_wide_shortage else "auto"
                ),
                parallel_tool_calls=False
            )
        except Exception as error:
            message = _provider_error_message(error, correlation_id)
            if tool_results:
                verified = _format_local_tool_results(tool_results)
                return verified + "\n\nThe assistant could not continue its explanation; the displayed results are the verified local tool output. " + message
            return message

        try:
            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []
        except Exception as error:
            logger.error("Groq response handling failed correlation_id=%s exception_class=%s",
                         correlation_id, type(error).__name__)
            if tool_results:
                return _format_local_tool_results(tool_results)
            return "The workforce assistant received an invalid response. Please try again."

        messages.append(assistant_message)

        if not tool_calls:
            if tool_results:
                return _final_tool_response(assistant_message.content, tool_results)
            return assistant_message.content or ""

        for tool_call in tool_calls:

            function_name = tool_call.function.name
            raw_arguments = tool_call.function.arguments

            try:
                arguments = (
                    json.loads(raw_arguments)
                    if isinstance(raw_arguments, str)
                    else raw_arguments
                )

                if not isinstance(arguments, dict):
                    raise ValueError(
                        "Tool arguments must be a JSON object."
                    )

                if organization_wide_shortage and function_name != "analyze_skill_shortage":
                    shortage_result = execute_tool(
                        "analyze_skill_shortage", {}, correlation_id=correlation_id
                    )
                    if shortage_result.get("status") == "error":
                        return shortage_result.get("message", "The workforce shortage query failed.")
                    return format_shortage_result(shortage_result)

                if function_name == "analyze_skill_shortage":
                    if organization_wide_shortage:
                        arguments.pop("skill_name", None)
                    explicit_weeks = set(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", str(user_message or "")))
                    if len(explicit_weeks) == 1:
                        arguments["demand_week"] = explicit_weeks.pop()
                    else:
                        arguments.pop("demand_week", None)

                if function_name == "compare_workforce_strategies":
                    has_skill = isinstance(arguments.get("skill_id"), str) and bool(arguments["skill_id"].strip())
                    has_week = isinstance(arguments.get("demand_week"), str) and bool(arguments["demand_week"].strip())
                    if not has_skill or not has_week:
                        if not has_skill and not has_week:
                            return "Which skill and demand week should I use for the strategy comparison?"
                        if not has_skill:
                            return "Which skill should I use for the strategy comparison?"
                        return "Which demand week should I use for the strategy comparison?"

                tool_result = execute_tool(
                    function_name,
                    arguments,
                    correlation_id=correlation_id,
                )

            except Exception as error:
                logger.error("Tool arguments invalid correlation_id=%s tool=%s exception_class=%s",
                             correlation_id, function_name, type(error).__name__)
                tool_result = {
                    "status": "error",
                    "message": "The requested workforce lookup could not be completed."
                }

            if tool_result.get("status") == "error":
                return tool_result.get("message", "The workforce data query failed. No match conclusion was produced.")

            tool_results.append((function_name, tool_result))

            tool_result = compact_tool_result(function_name, tool_result)

            tool_message = {
                "role": "tool",
                "name": function_name,
                "content": json.dumps(
                    tool_result,
                    ensure_ascii=False,
                    default=str
                ),
                "tool_call_id": tool_call.id
            }
            try:
                # Ensure the compact evidence is serializable before another
                # provider request is attempted.
                json.loads(tool_message["content"])
            except Exception as error:
                logger.error("Tool result serialization failed correlation_id=%s tool=%s exception_class=%s",
                             correlation_id, function_name, type(error).__name__)
                return "A workforce result could not be safely formatted. No conclusion was produced."
            messages.append(tool_message)

    if tool_results:
        return _format_local_tool_results(tool_results)
    return "The workforce assistant reached its analysis step limit. Please narrow the request and try again."
