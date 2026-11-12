"""Streamlit interface for local Project Intelligence workflows.

Imports are intentionally deferred until the page is rendered or an action is
requested, so an optional feature dependency cannot prevent the main app from
starting.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Any


def _clear_results(st: Any, *, clear_requirements: bool = False) -> None:
    for key in ("pi_confirmed", "pi_confirmed_signature", "pi_match_results",
                "pi_report_bytes", "pi_report_filename"):
        st.session_state.pop(key, None)
    if clear_requirements:
        for key in ("pi_document_extraction", "pi_extracted_text", "pi_requirements_seed"):
            st.session_state.pop(key, None)


def _signature(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _render_skill_results(st: Any, result: dict[str, Any]) -> None:
    summary = result.get("summary") or {}
    cols = st.columns(4)
    for col, label, key in zip(
        cols,
        ("Positions requested", "Positions filled", "Positions unfilled", "Skills resolved"),
        ("positions_requested", "positions_filled", "positions_unfilled", "skills_resolved"),
    ):
        col.metric(label, summary.get(key, 0))

    for index, skill in enumerate(result.get("skills") or [], start=1):
        name = skill.get("skill_name") or "Unresolved skill"
        with st.expander(f"{index}. {name} · {skill.get('recommendation', 'Review required')}", expanded=True):
            st.write(skill.get("recommendation_reason") or "No recommendation explanation was returned.")
            st.write(
                f"Requested: {skill.get('employees_needed', 0)} · "
                f"Matched: {skill.get('matched_count', 0)} · "
                f"Remaining gap: {skill.get('remaining_gap', 0)}"
            )
            availability = skill.get("availability") or {}
            st.caption(
                f"Availability weeks checked: {availability.get('weeks_expected', 0)} · "
                f"Coverage fully verified: {'Yes' if availability.get('fully_verified') else 'No'} · "
                f"Required hours/position/week: {skill.get('required_weekly_hours_per_position') or 'Not specified'}"
            )
            tiers = (
                ("Qualified candidates", "qualified_candidates", "qualified_candidates_total"),
                ("Training candidates (advisory only)", "training_candidates", "training_candidates_total"),
                ("Related skill candidates (advisory only)", "related_skill_candidates", "related_skill_candidates_total"),
                ("Stale or expired skill records (advisory only)", "stale_candidates", "stale_candidates_total"),
            )
            for title, key, total_key in tiers:
                rows = skill.get(key) or []
                st.markdown(f"**{title}** · {skill.get(total_key, len(rows))} total")
                if rows:
                    st.dataframe(rows, use_container_width=True, hide_index=True)
                else:
                    st.caption("No candidates in this category.")
            if skill.get("warnings"):
                for warning in skill["warnings"]:
                    st.warning(warning)
    st.info(
        "These results are planning candidates based on workforce records. They do not "
        "represent confirmed allocations, reserved capacity, training enrollment, hiring "
        "approval, or an employment contract. Related skills and training are advisory; "
        "availability may be partial or unverified. No employee data was sent to Groq. "
        "This feature does not create allocations. Manager review and approval are required."
    )


def render_project_intelligence_page() -> None:
    """Render upload, review, local matching, and report download workflow."""
    import streamlit as st

    st.title("Project Intelligence")
    st.write("Review project requirements, assess local workforce matches, and create a management report.")
    st.caption("Matching is read-only. Only project document text may be sent to Groq for requirement extraction; employee data stays local.")

    try:
        from features.project_intelligence import document_extractor, requirement_extractor
    except (ImportError, ModuleNotFoundError) as exc:
        st.error(f"Project Intelligence dependencies are unavailable: {exc}. The rest of WorkForceIQ remains available.")
        return

    upload = st.file_uploader("Upload project requirements", type=["pdf", "docx"], key="pi_upload_widget")
    if upload is None:
        _clear_results(st, clear_requirements=True)
        st.session_state.pop("pi_source_signature", None)
        st.info("Upload a PDF or DOCX file to begin, or use manual entry after selecting a document.")
        return

    file_bytes = upload.getvalue()
    source_signature = hashlib.sha256(upload.name.encode("utf-8") + b"\0" + file_bytes).hexdigest()
    if st.session_state.get("pi_source_signature") != source_signature:
        _clear_results(st, clear_requirements=True)
        st.session_state.pi_source_signature = source_signature
        for key in ("pi_project_name", "pi_start", "pi_end", "pi_unknown_start", "pi_unknown_end",
                    "pi_skills_editor", "pi_manager_confirm_checkbox"):
            st.session_state.pop(key, None)

    with st.expander("Document text extraction", expanded="pi_extracted_text" not in st.session_state):
        if st.button("Extract document text", key="pi_extract_document"):
            with st.spinner("Reading the uploaded document locally…"):
                extraction = document_extractor.extract_document(file_bytes, upload.name)
            st.session_state.pi_document_extraction = extraction
            st.session_state.pop("pi_extracted_text", None)
            _clear_results(st)
            if extraction.get("status") == "success":
                st.session_state.pi_extracted_text = extraction.get("text", "")
            else:
                st.error(extraction.get("error") or "The document could not be read.")
        extraction = st.session_state.get("pi_document_extraction")
        if extraction and extraction.get("status") == "success":
            metadata = extraction.get("metadata", {})
            st.caption(f"{metadata.get('characters', 0):,} characters extracted")
            st.text_area("Extracted text preview", st.session_state.get("pi_extracted_text", ""), height=180, disabled=True, key="pi_text_preview")

    if "pi_extracted_text" not in st.session_state:
        st.info("Extract document text to continue. If parsing fails, you can still use manual requirement entry below.")

    left, right = st.columns(2)
    with left:
        if st.button("Extract requirements with Groq", disabled=not bool(st.session_state.get("pi_extracted_text")), key="pi_extract_requirements"):
            try:
                with st.spinner("Extracting project requirements…"):
                    response = requirement_extractor.extract_requirements(st.session_state.pi_extracted_text)
            except (ImportError, ModuleNotFoundError) as exc:
                st.error(f"Requirement extraction dependency is unavailable: {exc}. Use manual entry instead.")
            else:
                if response.get("status") == "success" and response.get("requirements"):
                    st.session_state.pi_requirements_seed = response["requirements"]
                    st.session_state.pi_requirement_extraction = response
                    _clear_results(st)
                    for key in ("pi_project_name", "pi_start", "pi_end", "pi_unknown_start", "pi_unknown_end", "pi_skills_editor", "pi_manager_confirm_checkbox"):
                        st.session_state.pop(key, None)
                    st.success("Draft requirements extracted. Review and edit every field below.")
                else:
                    st.error(response.get("error") or "Requirement extraction did not return usable requirements.")
    with right:
        if st.button("Start manual entry", key="pi_manual_entry"):
            st.session_state.pi_requirements_seed = requirement_extractor.empty_requirements_template()
            _clear_results(st)
            for key in ("pi_project_name", "pi_start", "pi_end", "pi_unknown_start", "pi_unknown_end", "pi_skills_editor", "pi_manager_confirm_checkbox"):
                st.session_state.pop(key, None)

    seed = st.session_state.get("pi_requirements_seed")
    if not isinstance(seed, dict):
        return

    st.subheader("Review and edit requirements")
    project_name = st.text_input("Project name", value=seed.get("project_name") or "", key="pi_project_name")
    c1, c2 = st.columns(2)
    start_unknown = c1.checkbox("Start date unknown", value=not bool(seed.get("project_start_date")), key="pi_unknown_start")
    start_date = c1.text_input("Start date (YYYY-MM-DD)", value=seed.get("project_start_date") or "", disabled=start_unknown, key="pi_start")
    end_unknown = c2.checkbox("End date unknown", value=not bool(seed.get("project_end_date")), key="pi_unknown_end")
    end_date = c2.text_input("End date (YYYY-MM-DD)", value=seed.get("project_end_date") or "", disabled=end_unknown, key="pi_end")

    skills = seed.get("skills_required") or []
    editor_rows = []
    for row in skills:
        editor_rows.append({
            "skill_name": row.get("skill_name") or "",
            "min_proficiency_level": row.get("min_proficiency_level", 3),
            "employees_needed": row.get("employees_needed", 1),
            "required_weekly_hours_per_position": row.get("required_weekly_hours_per_position"),
            "notes": row.get("notes") or "",
        })
    import pandas as pd
    edited_skills = st.data_editor(
        pd.DataFrame(editor_rows, columns=["skill_name", "min_proficiency_level", "employees_needed", "required_weekly_hours_per_position", "notes"]),
        num_rows="dynamic", use_container_width=True, hide_index=True, key="pi_skills_editor",
        column_config={
            "skill_name": st.column_config.TextColumn("Skill name", required=True),
            "min_proficiency_level": st.column_config.NumberColumn("Minimum proficiency", min_value=1, max_value=5, step=1, required=True),
            "employees_needed": st.column_config.NumberColumn("Employees needed", min_value=1, max_value=100, step=1, required=True),
            "required_weekly_hours_per_position": st.column_config.NumberColumn("Weekly hours per position (optional)", min_value=0.01, max_value=168.0, step=0.5),
            "notes": st.column_config.TextColumn("Notes"),
        },
    )
    rows = edited_skills.to_dict(orient="records")
    for row in rows:
        for key in ("min_proficiency_level", "employees_needed"):
            value = row.get(key)
            if pd.notna(value) and float(value).is_integer():
                row[key] = int(value)
        if pd.isna(row.get("required_weekly_hours_per_position")):
            row["required_weekly_hours_per_position"] = None
        if pd.isna(row.get("notes")):
            row["notes"] = None

    payload = {
        "project_name": project_name.strip() or None,
        "project_start_date": None if start_unknown else (start_date.strip() or None),
        "project_end_date": None if end_unknown else (end_date.strip() or None),
        "project_duration_weeks": seed.get("project_duration_weeks"),
        "skills_required": rows,
    }
    signature = _signature(payload)
    if st.session_state.get("pi_current_edit_signature") != signature:
        _clear_results(st)
        st.session_state.pop("pi_requirement_extraction", None)
        st.session_state.pi_current_edit_signature = signature

    validated, errors = requirement_extractor.validate_requirements(payload)
    if errors:
        for error in errors:
            st.error(error)
    elif validated:
        for warning in validated.get("warnings", []):
            st.warning(warning)

    st.caption("Skill names are matched only by the existing exact-name resolver; unmatched names remain unresolved and will not count as qualified matches.")
    manager_confirmed = st.checkbox("I reviewed and confirm these requirements for local matching.", key="pi_manager_confirm_checkbox", disabled=bool(errors))
    if not manager_confirmed:
        _clear_results(st)
    confirmed = st.button(
        "Confirm requirements",
        type="primary",
        disabled=bool(errors) or not st.session_state.get("pi_manager_confirm_checkbox", False),
        key="pi_confirm_requirements",
    )
    if confirmed and validated:
        st.session_state.pi_confirmed = validated
        st.session_state.pi_confirmed_signature = signature
        st.session_state.pop("pi_match_results", None)
        st.session_state.pop("pi_report_bytes", None)
        st.success("Requirements confirmed. Matching will use local workforce records only.")

    is_confirmed = (
        st.session_state.get("pi_confirmed_signature") == signature
        and isinstance(st.session_state.get("pi_confirmed"), dict)
    )
    if is_confirmed and st.button("Run local matching", type="primary", key="pi_run_matching"):
        try:
            from features.project_intelligence import talent_matcher
            with st.spinner("Matching against local workforce records…"):
                st.session_state.pi_match_results = talent_matcher.match_project_requirements(
                    st.session_state.pi_confirmed
                )
            st.session_state.pop("pi_report_bytes", None)
        except (ImportError, ModuleNotFoundError) as exc:
            st.error(f"Local matching dependency is unavailable: {exc}.")

    match_result = st.session_state.get("pi_match_results") if is_confirmed else None
    if match_result:
        if match_result.get("status") == "ok":
            _render_skill_results(st, match_result)
        elif match_result.get("status") == "data_error":
            st.error(f"Local workforce data could not be used: {match_result.get('data_error')}")
        else:
            st.error("Matching did not complete. Review and reconfirm the requirements.")
        if st.button("Generate DOCX report", key="pi_generate_report"):
            try:
                from features.project_intelligence import report_generator
                report = report_generator.generate_management_report(st.session_state.pi_confirmed, match_result)
                if report.get("bytes"):
                    st.session_state.pi_report_bytes = report["bytes"]
                    st.session_state.pi_report_filename = report.get("filename", "project_intelligence_report.docx")
                    if report.get("status") != "success":
                        st.warning(report.get("error") or "The report documents an unsuccessful matching status.")
                else:
                    st.error(report.get("error") or "Report generation did not return a document.")
            except (ImportError, ModuleNotFoundError) as exc:
                st.error(f"DOCX report dependency is unavailable: {exc}. Install python-docx to use report downloads.")
        if st.session_state.get("pi_report_bytes"):
            st.download_button(
                "Download DOCX report",
                data=st.session_state.pi_report_bytes,
                file_name=st.session_state.pi_report_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                key="pi_download_report",
            )
