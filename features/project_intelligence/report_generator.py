"""Generate the Project Intelligence DOCX management report in memory.

The report consumes the structured result of
``features.project_intelligence.talent_matcher.match_project_requirements`` and
never recalculates matching or qualification. Proposed assignments come from
that result; cross-skill weekly capacity detail is read from the same local,
read-only workforce data root.

The document is produced with the already-installed ``python-docx`` package,
returned as bytes, and never written to disk. No Groq or network call occurs.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

from features.project_intelligence.talent_matcher import (
    MAX_CANDIDATES_PER_TIER,
    MatchingDataError,
    NO_QUALIFIED_MESSAGE,
    load_matching_data,
)

REPORT_TITLE = "Project Intelligence — Workforce Matching Report"

DISCLAIMER = (
    "These results are planning candidates based on workforce records as of the "
    "data coverage period. They do not represent confirmed allocations, reserved "
    "capacity, training enrollment, hiring approval, or an employment contract. "
    "Manager review and approval are required."
)

_LIMITATIONS = [
    "Matching covers active employees only.",
    "Workforce records do not include formal certifications, education, years of "
    "experience, performance ratings or verified delivery history.",
    "Availability is derived from weekly capacity records. Every overlapping "
    "project week is checked; weeks without records are unverified.",
    "Related-skill and training candidates are advisory only and are not "
    "qualified matches. Training does not guarantee qualification.",
    "An employee may support different skill requirements only when combined "
    "weekly hours fit remaining capacity in every overlapping week. An employee "
    "is counted at most once for the same skill requirement.",
    "Candidate tables may show the top 10 of a larger tier; totals remain accurate.",
    "The matching run does not create allocations, reservations, training "
    "enrollments, hiring decisions or database records.",
]

_SECTIONS = [
    "Report overview",
    "Executive summary",
    "Cross-Skill Employee Summary",
    "Project requirements",
    "Skill results",
    "Staffing gap summary",
    "External hiring",
    "Data quality and limitations",
    "Disclaimer",
]

_HEADING_COLOR = RGBColor(0x1F, 0x3B, 0x57)
_ACCENT_FILL = "DCE6F1"
_MUTED = RGBColor(0x59, 0x59, 0x59)


def _as_date(value: date | datetime | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return date.today()
    return date.today()


def _format_date(value: str | date | None) -> str:
    if value is None:
        return "Not provided"
    if isinstance(value, str):
        try:
            parsed = date.fromisoformat(value.strip()[:10])
        except ValueError:
            return "Not provided"
    else:
        parsed = value
    return parsed.strftime("%d %B %Y")


def _format_hours(value: Any) -> str:
    if value is None:
        return "Not specified"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not specified"
    text = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{text} h/week"


def _slug(value: Any) -> str:
    text = re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")
    return (text[:40] or "project").strip("-") or "project"


def _filename(project_name: Any, generated: date) -> str:
    return (
        f"workforceiq-project-intelligence-{_slug(project_name)}-"
        f"{generated.strftime('%Y%m%d')}.docx"
    )


def _configure_styles(document: Document) -> None:
    normal = document.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_after = Pt(4)

    for name, size in (("Heading 1", 15), ("Heading 2", 12), ("Heading 3", 10.5)):
        style = document.styles[name]
        style.font.name = "Calibri"
        style.font.size = Pt(size)
        style.font.color.rgb = _HEADING_COLOR
        style.font.bold = True
        style.paragraph_format.space_before = Pt(12)
        style.paragraph_format.space_after = Pt(4)
        style.paragraph_format.keep_with_next = True

    for section in document.sections:
        section.top_margin = Inches(0.75)
        section.bottom_margin = Inches(0.7)
        section.left_margin = Inches(0.85)
        section.right_margin = Inches(0.85)


def _add_field(paragraph: Any, field_code: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = field_code
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)


def _configure_header_footer(document: Document, project_name: str) -> None:
    section = document.sections[0]
    section.different_first_page_header_footer = False

    header = section.header.paragraphs[0]
    header.text = ""
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = header.add_run(project_name or REPORT_TITLE)
    run.font.size = Pt(8)
    run.font.color.rgb = _MUTED

    footer = section.footer.paragraphs[0]
    footer.text = ""
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    prefix = footer.add_run("Confidential — planning use only  |  Page ")
    prefix.font.size = Pt(8)
    prefix.font.color.rgb = _MUTED
    _add_field(footer, "PAGE")
    middle = footer.add_run(" of ")
    middle.font.size = Pt(8)
    middle.font.color.rgb = _MUTED
    _add_field(footer, "NUMPAGES")
    for run in footer.runs:
        run.font.size = Pt(8)
        run.font.color.rgb = _MUTED


def _shade(cell: Any, fill: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = OxmlElement("w:shd")
    shading.set(qn("w:val"), "clear")
    shading.set(qn("w:color"), "auto")
    shading.set(qn("w:fill"), fill)
    properties.append(shading)


def _repeat_header(row: Any) -> None:
    properties = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    properties.append(header)


def _set_cell(
    cell: Any,
    value: Any,
    *,
    bold: bool = False,
    size: float = 8.5,
    color: RGBColor | None = None,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(1)
    paragraph.paragraph_format.space_after = Pt(1)
    run = paragraph.add_run(str(value if value is not None else ""))
    run.font.size = Pt(size)
    run.font.name = "Calibri"
    run.bold = bold
    if color is not None:
        run.font.color.rgb = color


def _add_table(
    document: Document,
    headers: list[str],
    rows: list[list[Any]],
    widths: list[float],
    *,
    size: float = 8.5,
) -> Any:
    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False

    header_cells = table.rows[0].cells
    for index, header in enumerate(headers):
        _set_cell(header_cells[index], header, bold=True, size=size)
        _shade(header_cells[index], _ACCENT_FILL)
    _repeat_header(table.rows[0])

    for values in rows:
        cells = table.add_row().cells
        for index, value in enumerate(values):
            _set_cell(cells[index], value, size=size)

    for row in table.rows:
        for index, width in enumerate(widths[: len(headers)]):
            row.cells[index].width = Inches(width)

    document.add_paragraph().paragraph_format.space_after = Pt(2)
    return table


def _note(document: Document, text: str, *, bold: bool = False, italic: bool = False) -> None:
    paragraph = document.add_paragraph()
    run = paragraph.add_run(text)
    run.font.size = Pt(9.5)
    run.bold = bold
    run.italic = italic
    return


def _add_title(document: Document, project_name: str, generated: date) -> None:
    title = document.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.LEFT
    title_run = title.add_run(REPORT_TITLE)
    title_run.font.size = Pt(20)
    title_run.font.bold = True
    title_run.font.color.rgb = _HEADING_COLOR

    subtitle = document.add_paragraph()
    subtitle_run = subtitle.add_run(project_name or "Project requirements")
    subtitle_run.font.size = Pt(13)
    subtitle_run.font.color.rgb = _MUTED

    meta = document.add_paragraph()
    meta_run = meta.add_run(f"Generated on {_format_date(generated)}")
    meta_run.font.size = Pt(9)
    meta_run.font.color.rgb = _MUTED

    rule = document.add_paragraph()
    rule.paragraph_format.space_after = Pt(6)
    rule_run = rule.add_run("_" * 86)
    rule_run.font.size = Pt(8)
    rule_run.font.color.rgb = _MUTED


def _overall_recommendation(result: dict[str, Any]) -> str:
    summary = result.get("summary") or {}
    requested = int(summary.get("positions_requested") or 0)
    filled = int(summary.get("positions_filled") or 0)
    unfilled = int(summary.get("positions_unfilled") or 0)

    if requested == 0:
        return (
            "No positions were requested. Confirm the project requirements before "
            "planning work."
        )
    if unfilled == 0:
        return (
            f"All {requested} requested position(s) can be covered by fully "
            "available, qualified internal employees under the verified matching "
            "rules. Manager confirmation is still required."
        )
    if filled > 0:
        return (
            f"{filled} of {requested} requested position(s) can be covered by fully "
            f"available, qualified internal employees. {unfilled} position(s) "
            "remain unfilled and require verification, training or external hiring."
        )
    return (
        f"None of the {requested} requested position(s) can be filled by a fully "
        "available, qualified internal employee on the current records. Training "
        "and external hiring options are reported separately."
    )


def _candidate_availability_label(candidate: dict[str, Any]) -> str:
    status = str(candidate.get("availability_status") or "unknown").strip()
    labels = {
        "available": "Available",
        "limited": "Limited",
        "unavailable": "Unavailable",
        "unknown": "Unknown",
    }
    return labels.get(status.casefold(), status.title() if status else "Unknown")


def _coverage_label(candidate: dict[str, Any]) -> str:
    coverage = str(candidate.get("coverage_status") or "not_verified")
    return {
        "fully_verified": "Fully verified",
        "partially_verified": "Partially verified",
        "not_verified": "Not verified",
    }.get(coverage, "Not verified")


def _weeks_label(candidate: dict[str, Any]) -> str:
    expected = int(candidate.get("weeks_expected") or 0)
    data = int(candidate.get("weeks_with_data") or 0)
    return f"{data} of {expected}"


def _add_report_overview(
    document: Document,
    project: dict[str, Any],
    generated: date,
) -> None:
    document.add_heading("1. Report overview", level=1)
    rows = [
        ["Project", project.get("project_name") or "Not provided"],
        ["Project start", _format_date(project.get("project_start_date"))],
        ["Project end", _format_date(project.get("project_end_date"))],
        [
            "Project duration",
            f"{project['project_duration_weeks']} week(s)"
            if project.get("project_duration_weeks")
            else "Not specified",
        ],
        ["Report generated", _format_date(generated)],
        [
            "Data coverage",
            f"{_format_date(project.get('data_horizon_start'))} to "
            f"{_format_date(project.get('data_horizon_end'))}",
        ],
        ["Overlapping availability weeks", str(project.get("availability_weeks", 0))],
    ]
    _add_table(document, ["Item", "Detail"], rows, [1.9, 4.4], size=9)


def _add_executive_summary(document: Document, result: dict[str, Any]) -> None:
    document.add_heading("2. Executive summary", level=1)
    summary = result.get("summary") or {}
    qualified_matches = int(summary.get("qualified_candidate_matches", 0))

    rows = [
        ["Requested positions", str(summary.get("positions_requested", 0))],
        ["Positions covered by verified internal candidates", str(summary.get("positions_filled", 0))],
        ["Unfilled positions", str(summary.get("positions_unfilled", 0))],
        ["Skills requested", str(summary.get("skills_requested", 0))],
        ["Skills resolved", str(summary.get("skills_resolved", 0))],
    ]
    _add_table(document, ["Measure", "Value"], rows, [3.6, 2.7], size=9)
    _note(
        document,
        f"{qualified_matches} skill-specific qualified candidate matches "
        "(not deduplicated; employees may appear in multiple skill pools).",
        italic=True,
    )

    _note(document, _overall_recommendation(result), bold=True)


def _cross_skill_employee_assignments(
    result: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    employees: dict[str, dict[str, Any]] = {}
    for skill in result.get("skills") or []:
        skill_id = str(skill.get("resolved_skill_id") or "")
        if skill.get("resolution") != "exact" or not skill_id:
            continue
        candidate_names = {
            str(candidate.get("employee_id")): candidate.get("employee_name")
            for candidate in skill.get("qualified_candidates") or []
            if candidate.get("employee_id")
        }
        for employee_id in skill.get("recommended_employee_ids") or []:
            employee_id = str(employee_id)
            entry = employees.setdefault(
                employee_id,
                {"employee_name": candidate_names.get(employee_id), "skills": {}},
            )
            if not entry.get("employee_name") and candidate_names.get(employee_id):
                entry["employee_name"] = candidate_names[employee_id]
            entry["skills"].setdefault(
                skill_id,
                {
                    "skill_name": skill.get("skill_name") or skill_id,
                    "weekly_hours": skill.get("required_weekly_hours_per_position"),
                },
            )
    return {
        employee_id: entry
        for employee_id, entry in employees.items()
        if len(entry["skills"]) > 1
    }


def _overlapping_capacity_weeks(
    capacity: Any, project: dict[str, Any]
) -> list[date]:
    start_text = project.get("project_start_date")
    end_text = project.get("project_end_date")
    if not start_text or not end_text:
        return []
    start, end = date.fromisoformat(str(start_text)), date.fromisoformat(str(end_text))
    weeks: set[date] = set()
    for value in capacity["availability_date"].dropna().unique():
        week = value.date() if hasattr(value, "date") else date.fromisoformat(str(value)[:10])
        if week <= end and week + timedelta(days=6) >= start:
            weeks.add(week)
    return sorted(weeks)


def _add_cross_skill_employee_summary(
    document: Document,
    result: dict[str, Any],
    *,
    data_root: Path | str | None,
) -> None:
    document.add_heading("Cross-Skill Employee Summary", level=1)
    assignments = _cross_skill_employee_assignments(result)
    if not assignments:
        _note(document, "No employee is proposed for more than one distinct required skill.")
        return

    _note(
        document,
        "Repeated appearances in the individual skill tables refer to the same "
        "employee, not separate people. These assignments are proposed only when "
        "combined weekly hours fit the recorded capacity in every overlapping week.",
        italic=True,
    )

    try:
        frames = load_matching_data(data_root)
        capacity = frames["capacity"]
        employees = frames["employees"]
        weeks = _overlapping_capacity_weeks(capacity, result.get("project") or {})
        names = dict(
            zip(employees["employee_id"].astype(str), employees["employee_name"].astype(str))
        )
        weekly_capacity = {
            (str(row.employee_id), row.availability_date.date()): float(row.remaining_hours)
            for row in capacity.dropna(subset=["remaining_hours"]).itertuples(index=False)
            if str(row.employee_id) in assignments
        }
    except (MatchingDataError, KeyError, OSError, ValueError):
        capacity = None
        weeks = []
        names = {}
        weekly_capacity = {}

    rows: list[list[Any]] = []
    for employee_id, entry in assignments.items():
        skills = list(entry["skills"].values())
        hours = [skill["weekly_hours"] for skill in skills]
        known_hours = all(isinstance(value, (int, float)) for value in hours)
        combined = sum(float(value) for value in hours) if known_hours else None
        employee_name = entry.get("employee_name") or names.get(employee_id) or "—"
        assigned_skills = "; ".join(
            f"{skill['skill_name']}: {_format_hours(skill['weekly_hours'])}"
            for skill in skills
        )
        if not weeks or capacity is None:
            rows.append(
                [employee_id, employee_name, assigned_skills,
                 _format_hours(combined), "Not available", "Not available", "Not available"]
            )
            continue
        for week in weeks:
            available = weekly_capacity.get((employee_id, week))
            remaining = available - combined if available is not None and combined is not None else None
            rows.append(
                [
                    employee_id,
                    employee_name,
                    assigned_skills,
                    _format_hours(combined),
                    _format_date(week),
                    _format_hours(available) if available is not None else "Not verified",
                    _format_hours(remaining) if remaining is not None else "Not verified",
                ]
            )

    _add_table(
        document,
        [
            "Employee ID", "Name", "Assigned skills (weekly hours)",
            "Combined weekly hours", "Overlapping week", "Available capacity",
            "Remaining capacity",
        ],
        rows,
        [0.75, 0.9, 1.55, 0.9, 0.85, 0.85, 0.85],
        size=8,
    )


def _add_requirements_section(
    document: Document,
    result: dict[str, Any],
    requirements: dict[str, Any],
) -> None:
    document.add_heading("3. Project requirements", level=1)
    _note(
        document,
        "Requirements below are taken from the approved requirement set. "
        "Skill resolution against the workforce taxonomy is shown for each row.",
        italic=True,
    )

    rows: list[list[Any]] = []
    for index, skill in enumerate(result.get("skills") or [], start=1):
        resolution = "Exact match" if skill.get("resolution") == "exact" else "Unresolved"
        rows.append(
            [
                str(index),
                skill.get("skill_name") or "Unspecified",
                skill.get("skill_category") or "—",
                skill.get("min_proficiency_level") or "—",
                skill.get("employees_needed") or 0,
                _format_hours(skill.get("required_weekly_hours_per_position")),
                resolution,
            ]
        )

    if rows:
        _add_table(
            document,
            ["#", "Required skill", "Category", "Min level", "Headcount", "Weekly hours", "Resolution"],
            rows,
            [0.3, 1.45, 1.25, 0.55, 0.7, 0.95, 1.1],
        )
    else:
        _note(document, "No skill requirements were supplied.", italic=True)

    notes = requirements.get("skills_required") or []
    noted = [
        (item.get("skill_name"), item.get("notes"))
        for item in notes
        if isinstance(item, dict) and item.get("notes")
    ]
    if noted:
        document.add_heading("Requirement notes", level=3)
        for name, note in noted:
            _note(document, f"{name}: {note}")


def _add_qualified_section(document: Document, skill: dict[str, Any]) -> None:
    document.add_heading("Qualified internal employee recommendations", level=3)
    candidates = skill.get("qualified_candidates") or []
    total = int(skill.get("qualified_candidates_total") or 0)
    reason = str(skill.get("recommendation_reason") or "")

    if int(skill.get("matched_count") or 0) > 0:
        _note(
            document,
            f"{skill.get('matched_count')} of {skill.get('employees_needed')} "
            "position(s) are covered by the candidates marked as proposed below.",
        )
    else:
        _note(document, "No qualified candidate could be counted toward headcount.")
        if NO_QUALIFIED_MESSAGE not in reason:
            _note(document, NO_QUALIFIED_MESSAGE, bold=True)

    if total == 0:
        _note(document, "No qualified candidates to display.", italic=True)
        return

    rows = []
    for candidate in candidates:
        rows.append(
            [
                candidate.get("employee_id") or "—",
                candidate.get("employee_name") or "—",
                candidate.get("role_name") or candidate.get("role_id") or "—",
                candidate.get("employment_type") or "—",
                candidate.get("proficiency_level") or "—",
                _candidate_availability_label(candidate),
                _coverage_label(candidate),
                _format_hours(candidate.get("min_remaining_hours")),
                _weeks_label(candidate),
                "Yes" if candidate.get("selected_for_position") else "No",
            ]
        )

    _add_table(
        document,
        [
            "Employee ID",
            "Name",
            "Role",
            "Type",
            "Prof.",
            "Availability",
            "Coverage",
            "Min weekly",
            "Weeks",
            "Proposed",
        ],
        rows,
        [0.75, 0.95, 0.95, 0.55, 0.4, 0.8, 0.75, 0.65, 0.55, 0.55],
        size=8,
    )

    if total > len(candidates):
        _note(
            document,
            f"Showing top {len(candidates)} of {total} qualified candidates.",
            italic=True,
        )


def _add_training_section(document: Document, skill: dict[str, Any]) -> None:
    document.add_heading("Potential training candidates (not yet qualified)", level=3)
    _note(
        document,
        "These employees are not qualified for the requirement. Training is "
        "advisory only and does not guarantee qualification.",
        italic=True,
    )

    exact = skill.get("training_candidates") or []
    exact_total = int(skill.get("training_candidates_total") or 0)
    related = skill.get("related_skill_candidates") or []
    related_total = int(skill.get("related_skill_candidates_total") or 0)

    if exact:
        rows = [
            [
                candidate.get("employee_id") or "—",
                candidate.get("employee_name") or "—",
                candidate.get("proficiency_level") or "—",
                candidate.get("skill_status") or "—",
                candidate.get("training_status") or "No active record",
            ]
            for candidate in exact
        ]
        _add_table(
            document,
            ["Employee ID", "Name", "Current level", "Skill status", "Training status"],
            rows,
            [0.9, 1.3, 0.8, 0.9, 1.5],
        )
        if exact_total > len(exact):
            _note(document, f"Showing top {len(exact)} of {exact_total} training candidates.", italic=True)
    else:
        _note(document, "No exact-skill training candidates identified.", italic=True)

    if related:
        document.add_heading("Related-skill candidates (not yet qualified)", level=3)
        _note(
            document,
            "Related skills in the same category are advisory only and are not "
            "qualified matches for the required skill.",
            italic=True,
        )
        rows = [
            [
                candidate.get("employee_id") or "—",
                candidate.get("employee_name") or "—",
                candidate.get("skill_name") or "—",
                candidate.get("skill_category") or "—",
                candidate.get("proficiency_level") or "—",
                candidate.get("training_status") or "No active record",
            ]
            for candidate in related
        ]
        _add_table(
            document,
            ["Employee ID", "Name", "Related skill", "Category", "Level", "Training status"],
            rows,
            [0.85, 1.05, 1.15, 1.05, 0.5, 1.3],
        )
        if related_total > len(related):
            _note(document, f"Showing top {len(related)} of {related_total} related-skill candidates.", italic=True)
    else:
        _note(document, "No related-skill candidates identified.", italic=True)


def _add_stale_section(document: Document, skill: dict[str, Any]) -> None:
    document.add_heading("Stale or expired skill records (advisory only)", level=3)
    candidates = skill.get("stale_candidates") or []
    total = int(skill.get("stale_candidates_total") or 0)

    if not candidates:
        _note(document, "No stale or expired records identified.", italic=True)
        return

    _note(
        document,
        "These records are not current and are never counted as qualified matches. "
        "Re-verification or training may be required.",
        italic=True,
    )
    rows = [
        [
            candidate.get("employee_id") or "—",
            candidate.get("employee_name") or "—",
            candidate.get("proficiency_level") or "—",
            candidate.get("skill_status") or "—",
            candidate.get("days_since_verified") if candidate.get("days_since_verified") is not None else "—",
            candidate.get("reason") or "—",
        ]
        for candidate in candidates
    ]
    _add_table(
        document,
        ["Employee ID", "Name", "Level", "Status", "Days since verified", "Advisory note"],
        rows,
        [0.8, 1.0, 0.45, 0.6, 0.95, 2.5],
        size=8,
    )
    if total > len(candidates):
        _note(document, f"Showing top {len(candidates)} of {total} stale records.", italic=True)


def _add_excluded_section(document: Document, skill: dict[str, Any]) -> None:
    document.add_heading("Candidates not counted", level=3)
    excluded = skill.get("excluded_candidates") or []
    total = int(skill.get("excluded_candidates_total") or 0)
    summary = skill.get("exclusion_summary") or {}

    if not excluded and not summary:
        _note(document, "No candidates were excluded.", italic=True)
        return

    if summary:
        pretty = ", ".join(
            f"{str(reason).replace('_', ' ')} ({count})" for reason, count in sorted(summary.items())
        )
        _note(document, f"Exclusion reasons: {pretty}.", italic=True)

    if excluded:
        rows = [
            [
                candidate.get("employee_id") or "—",
                candidate.get("employee_name") or "—",
                candidate.get("reason") or "Not specified",
            ]
            for candidate in excluded
        ]
        _add_table(
            document,
            ["Employee ID", "Name", "Reason"],
            rows,
            [1.0, 1.4, 4.0],
            size=8,
        )
        if total > len(excluded):
            _note(document, f"Showing top {len(excluded)} of {total} excluded candidates.", italic=True)


def _add_skill_results(document: Document, result: dict[str, Any]) -> None:
    document.add_heading("4. Skill results", level=1)
    _note(
        document,
        "Each skill is reported separately. An employee may be proposed for "
        "different skills when combined weekly hours fit remaining capacity in "
        "every overlapping week; each employee counts at most once per skill.",
        italic=True,
    )

    skills = result.get("skills") or []
    if not skills:
        _note(document, "No skill results are available.", italic=True)
        return

    for index, skill in enumerate(skills, start=1):
        resolved = skill.get("resolution") == "exact"
        heading = f"4.{index} {skill.get('skill_name') or 'Unspecified skill'}"
        document.add_heading(heading, level=2)

        if not resolved:
            _note(
                document,
                "This skill is unresolved in the workforce taxonomy. Internal supply "
                "cannot be assessed for this requirement.",
                bold=True,
            )
            _note(document, skill.get("recommendation_reason") or "", italic=True)
            continue

        summary_rows = [
            ["Skill category", skill.get("skill_category") or "—"],
            ["Required proficiency", str(skill.get("min_proficiency_level") or "—")],
            ["Required headcount", str(skill.get("employees_needed") or 0)],
            ["Matched headcount", str(skill.get("matched_count") or 0)],
            ["Unfilled headcount", str(skill.get("remaining_gap") or 0)],
            ["Weekly hours per position", _format_hours(skill.get("required_weekly_hours_per_position"))],
            ["Recommendation", skill.get("recommendation") or "—"],
        ]
        _add_table(document, ["Requirement", "Value"], summary_rows, [2.2, 4.1], size=9)

        _note(document, skill.get("recommendation_reason") or "", italic=True)

        _add_qualified_section(document, skill)
        _add_training_section(document, skill)
        _add_stale_section(document, skill)
        _add_excluded_section(document, skill)


def _add_gap_summary(document: Document, result: dict[str, Any]) -> None:
    document.add_heading("5. Staffing gap summary", level=1)
    rows = []
    for skill in result.get("skills") or []:
        rows.append(
            [
                skill.get("skill_name") or "Unspecified",
                skill.get("employees_needed") or 0,
                skill.get("matched_count") or 0,
                skill.get("remaining_gap") or 0,
                skill.get("recommendation") or "—",
            ]
        )

    if rows:
        _add_table(
            document,
            ["Skill", "Required", "Filled", "Unfilled", "Recommendation"],
            rows,
            [1.9, 0.8, 0.7, 0.8, 2.1],
            size=9,
        )
    else:
        _note(document, "No skill requirements to summarise.", italic=True)

    summary = result.get("summary") or {}
    _note(
        document,
        f"Totals: {summary.get('positions_requested', 0)} requested, "
        f"{summary.get('positions_filled', 0)} filled, "
        f"{summary.get('positions_unfilled', 0)} unfilled.",
        bold=True,
    )


def _add_external_hiring(document: Document, result: dict[str, Any]) -> None:
    document.add_heading("6. External hiring", level=1)
    gaps = [skill for skill in result.get("skills") or [] if int(skill.get("remaining_gap") or 0) > 0]

    if not gaps:
        _note(document, "No unfilled positions; no external hiring recommendation is required.", italic=True)
        return

    _note(
        document,
        "External hiring is recommended only for positions that remain unfilled by "
        "verified internal candidates. No hiring decision has been made.",
        italic=True,
    )
    rows = [
        [
            skill.get("skill_name") or "Unspecified",
            skill.get("resolved_skill_id") or "Unresolved",
            skill.get("remaining_gap") or 0,
            skill.get("recommendation") or "—",
        ]
        for skill in gaps
    ]
    _add_table(
        document,
        ["Skill", "Skill ID", "Unfilled positions", "Recommendation"],
        rows,
        [2.0, 1.0, 1.1, 2.2],
        size=9,
    )


def _add_data_quality(document: Document, result: dict[str, Any], requirements: dict[str, Any]) -> None:
    document.add_heading("7. Data quality and limitations", level=1)

    warnings = list(result.get("warnings") or [])
    unresolved = list((result.get("summary") or {}).get("unresolved_skills") or [])
    requirement_warnings = list(requirements.get("warnings") or [])

    if unresolved:
        _note(document, "Unresolved skills", bold=True)
        for name in unresolved:
            _note(document, f"• {name}: internal supply was not assessed.")
    else:
        _note(document, "All required skills resolved to the workforce taxonomy.", italic=True)

    if warnings or requirement_warnings:
        _note(document, "Warnings", bold=True)
        for warning in dict.fromkeys(warnings + requirement_warnings):
            _note(document, f"• {warning}")

    _note(document, "Limitations", bold=True)
    for limitation in _LIMITATIONS:
        _note(document, f"• {limitation}")


def _add_disclaimer(document: Document) -> None:
    document.add_heading("8. Disclaimer", level=1)
    paragraph = document.add_paragraph()
    run = paragraph.add_run(DISCLAIMER)
    run.font.size = Pt(9)
    run.italic = True


def _build_success_document(
    requirements: dict[str, Any],
    result: dict[str, Any],
    generated: date,
    *,
    data_root: Path | str | None = None,
) -> Document:
    project = result.get("project") or {}
    project_name = str(project.get("project_name") or requirements.get("project_name") or "")

    document = Document()
    _configure_styles(document)
    _configure_header_footer(document, project_name)

    document.core_properties.title = REPORT_TITLE
    document.core_properties.author = "WorkForceIQ"
    document.core_properties.subject = "Project Intelligence workforce matching"

    _add_title(document, project_name, generated)
    _add_report_overview(document, project, generated)
    _add_executive_summary(document, result)
    _add_cross_skill_employee_summary(document, result, data_root=data_root)
    _add_requirements_section(document, result, requirements)
    _add_skill_results(document, result)
    _add_gap_summary(document, result)
    _add_external_hiring(document, result)
    _add_data_quality(document, result, requirements)
    _add_disclaimer(document)
    return document


def _build_error_document(
    message: str,
    generated: date,
    *,
    project_name: str = "",
    errors: list[str] | None = None,
    warnings: list[str] | None = None,
    status_label: str = "Matching could not be completed",
) -> Document:
    document = Document()
    _configure_styles(document)
    _configure_header_footer(document, project_name)

    document.core_properties.title = REPORT_TITLE
    document.core_properties.author = "WorkForceIQ"

    _add_title(document, project_name, generated)
    document.add_heading("1. Report overview", level=1)
    _add_table(
        document,
        ["Item", "Detail"],
        [
            ["Report generated", _format_date(generated)],
            ["Report status", status_label],
            ["Project", project_name or "Not provided"],
        ],
        [1.9, 4.4],
        size=9,
    )

    document.add_heading("2. Matching status", level=1)
    _note(document, message, bold=True)
    _note(
        document,
        "No candidate recommendations, headcount coverage or workforce "
        "recommendations are reported because matching could not be completed "
        "reliably.",
    )

    if errors:
        _note(document, "Validation issues", bold=True)
        for error in errors:
            _note(document, f"• {error}")

    if warnings:
        _note(document, "Warnings", bold=True)
        for warning in dict.fromkeys(warnings):
            _note(document, f"• {warning}")

    document.add_heading("3. Disclaimer", level=1)
    paragraph = document.add_paragraph()
    run = paragraph.add_run(DISCLAIMER)
    run.font.size = Pt(9)
    run.italic = True
    return document


def _save_bytes(document: Document) -> bytes:
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def generate_management_report(
    requirements: dict[str, Any],
    match_result: dict[str, Any],
    *,
    generated_on: date | datetime | str | None = None,
    data_root: Path | str | None = None,
) -> dict[str, Any]:
    """Build the DOCX management report in memory.

    Returns ``{status, bytes, filename, error, generated_on, sections}``.
    ``status`` is ``success``, ``data_error`` or ``invalid_requirements``.
    A readable DOCX is still returned for error states, clearly disclosing that
    matching could not be completed.
    """
    generated = _as_date(generated_on)
    requirements = requirements if isinstance(requirements, dict) else {}

    if not isinstance(match_result, dict) or "project" not in match_result:
        message = (
            "The matching result is missing or malformed, so no workforce "
            "recommendation can be reported."
        )
        document = _build_error_document(message, generated)
        return {
            "status": "data_error",
            "bytes": _save_bytes(document),
            "filename": _filename(requirements.get("project_name"), generated),
            "error": message,
            "generated_on": generated.isoformat(),
            "sections": ["Report overview", "Matching status", "Disclaimer"],
        }

    status = str(match_result.get("status") or "")
    project = match_result.get("project") or {}
    project_name = str(project.get("project_name") or requirements.get("project_name") or "")

    if status == "data_error":
        message = str(
            match_result.get("data_error")
            or "The workforce data required for matching could not be read reliably."
        )
        document = _build_error_document(
            message,
            generated,
            project_name=project_name,
            warnings=list(match_result.get("warnings") or []),
        )
        return {
            "status": "data_error",
            "bytes": _save_bytes(document),
            "filename": _filename(project_name, generated),
            "error": message,
            "generated_on": generated.isoformat(),
            "sections": ["Report overview", "Matching status", "Disclaimer"],
        }

    if status == "invalid_requirements":
        message = (
            "The project requirements are invalid, so matching was not performed."
        )
        document = _build_error_document(
            message,
            generated,
            project_name=project_name,
            errors=[str(error) for error in match_result.get("errors") or []],
            status_label="Requirements could not be validated",
        )
        return {
            "status": "invalid_requirements",
            "bytes": _save_bytes(document),
            "filename": _filename(project_name, generated),
            "error": message,
            "generated_on": generated.isoformat(),
            "sections": ["Report overview", "Matching status", "Disclaimer"],
        }

    document = _build_success_document(
        requirements, match_result, generated, data_root=data_root
    )
    return {
        "status": "success",
        "bytes": _save_bytes(document),
        "filename": _filename(project_name, generated),
        "error": None,
        "generated_on": generated.isoformat(),
        "sections": list(_SECTIONS),
    }
