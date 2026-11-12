from pathlib import Path
import os

import streamlit as st
from dotenv import load_dotenv

from dashboard.data import (
    load_csv, read_head, get_options, get_employee_count, get_csv_rows,
    shortage_tool, talent_tool, strategy_tool, get_data_root,
)
from dashboard.components import header, metric, section, table, empty_state, inr
from features.project_intelligence.ui import render_project_intelligence_page

load_dotenv()
st.set_page_config(page_title="WorkForceIQ | Workforce Intelligence", page_icon="▦", layout="wide", initial_sidebar_state="expanded")


st.markdown("""

<style>
:root {
    --navy: #10243a;
    --blue: #2864dc;
    --teal: #0b8f8a;
    --ink: #24364b;
    --muted: #52647a;
    --line: #e4eaf0;
    --canvas: #f5f7fa;
}

.stApp {
    background: var(--canvas);
    font-family: 'Segoe UI', Arial, sans-serif;
}

/* Sidebar and navigation */
section[data-testid="stSidebar"] {
    background: var(--navy);
}

section[data-testid="stSidebar"] .brand {
    color: #ffffff;
    font-size: 23px;
    font-weight: 800;
    letter-spacing: -.7px;
    margin: 2px 0;
}

section[data-testid="stSidebar"] .brand span {
    color: #47d6c2;
}

section[data-testid="stSidebar"] .brand-sub {
    color: #c1d0df;
    font-size: 12px;
    letter-spacing: .2px;
    margin-bottom: 24px;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    color: #e8eef7 !important;
    padding: 9px 12px;
    border-radius: 8px;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked),
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radio"][aria-checked="true"] {
    background: #24496d !important;
    color: #ffffff !important;
    font-weight: 700;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) *,
section[data-testid="stSidebar"] [data-testid="stRadio"] [role="radio"][aria-checked="true"] * {
    color: #ffffff !important;
}

section[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #c1d0df !important;
}

/* Main content typography */
.stApp [data-testid="stMain"] {
    color: var(--ink);
}

/* Keep Streamlit error alerts readable against the light dashboard canvas. */
.stApp [data-testid="stAlert"][kind="error"],
.stApp [data-testid="stAlertContentError"] {
    background-color: #fff1f0 !important;
    color: #7f1d1d !important;
    border: 1px solid #b42318 !important;
}

.stApp [data-testid="stAlert"][kind="error"] *,
.stApp [data-testid="stAlertContentError"] * {
    color: #7f1d1d !important;
    opacity: 1 !important;
}

.page-title,
.stApp [data-testid="stMain"] h1,
.stApp [data-testid="stMain"] h2,
.stApp [data-testid="stMain"] h3,
.section-title {
    color: var(--navy) !important;
}

.page-title {
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -.8px;
    margin: 0;
}

.section-title {
    font-size: 16px;
    font-weight: 750;
    margin: 8px 0 4px;
}

.page-sub {
    font-size: 13px;
    margin: 2px 0 10px;
}

.page-sub,
.stApp [data-testid="stMain"] [data-testid="stCaptionContainer"],
.stApp [data-testid="stMain"] small {
    color: var(--muted) !important;
}

.stApp [data-testid="stMain"] .stMarkdown p,
.stApp [data-testid="stMain"] .stMarkdown li,
.stApp [data-testid="stMain"] label,
.stApp [data-testid="stMain"] [data-testid="stWidgetLabel"] p {
    color: #334155;
}


/* Assistant welcome and chat message Markdown */
.assistant-welcome h3,
.assistant-welcome p,
.stApp [data-testid="stMain"] [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
.stApp [data-testid="stMain"] [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] * {
    color: #10243a !important;
    opacity: 1 !important;
    font-weight: 500;
}

.stApp [data-testid="stMain"] [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] a {
    color: #174ea6 !important;
}
/* Force readable assistant response text */
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] span,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] em {
    color: #10243a !important;
    opacity: 1 !important;
}
/* Make assistant response table content readable */
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] table {
    width: 100%;
    border-collapse: collapse;
    background-color: #ffffff !important;
    color: #10243a !important;
    opacity: 1 !important;
    border: 1px solid #94a3b8 !important;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] td {
    color: #10243a !important;
    opacity: 1 !important;
    border: 1px solid #cbd5e1 !important;
    padding: 0.45rem 0.65rem;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] thead,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] thead tr,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th {
    background-color: #e2e8f0 !important;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] tbody,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] tbody tr {
    background-color: #ffffff !important;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] tbody td {
    background-color: #ffffff !important;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] tbody tr:nth-child(even) td {
    background-color: #f8fafc !important;
}

.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] th *,
.stApp [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] td * {
    color: #10243a !important;
    opacity: 1 !important;
}


/* Dashboard cards and metrics */
.card {
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: 10px;
    padding: 12px 14px;
    box-shadow: 0 2px 8px rgba(20, 39, 61, .035);
    height: 100%;
}

.metric-label,
.metric-note {
    color: var(--muted);
}

.metric-label {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: .3px;
}

.metric-value {
    color: var(--navy);
    font-size: 22px;
    font-weight: 800;
    margin-top: 6px;
}

.metric-note {
    font-size: 11px;
    margin-top: 1px;
}

.notice {
    background: #eef5ff;
    border: 1px solid #d5e4fa;
    border-radius: 10px;
    color: #334d6a;
    font-size: 13px;
    padding: 12px 15px;
}

/* Form controls and tables */
.stButton > button {
    border-radius: 8px;
    font-weight: 600;

}
/* AI Assistant suggestion buttons */
.stApp [data-testid="stMain"] .st-key-prompt_0 button,
.stApp [data-testid="stMain"] .st-key-prompt_1 button,
.stApp [data-testid="stMain"] .st-key-prompt_2 button,
.stApp [data-testid="stMain"] .st-key-prompt_3 button {
    background-color: #172b45 !important;
    color: #ffffff !important;
    border: 1px solid #172b45 !important;
    transition: background-color 0.2s ease, border-color 0.2s ease;
}

.stApp [data-testid="stMain"] .st-key-prompt_0 button:hover,
.stApp [data-testid="stMain"] .st-key-prompt_1 button:hover,
.stApp [data-testid="stMain"] .st-key-prompt_2 button:hover,
.stApp [data-testid="stMain"] .st-key-prompt_3 button:hover {
    background-color: #29496d !important;
    color: #ffffff !important;
    border-color: #29496d !important;
}

.stApp [data-testid="stMain"] .st-key-prompt_0 button:focus,
.stApp [data-testid="stMain"] .st-key-prompt_1 button:focus,
.stApp [data-testid="stMain"] .st-key-prompt_2 button:focus,
.stApp [data-testid="stMain"] .st-key-prompt_3 button:focus {
    color: #ffffff !important;
    outline: 2px solid #6b9ed6 !important;
    outline-offset: 2px;
}

.stApp [data-testid="stMain"] .st-key-prompt_0 button:active,
.stApp [data-testid="stMain"] .st-key-prompt_1 button:active,
.stApp [data-testid="stMain"] .st-key-prompt_2 button:active,
.stApp [data-testid="stMain"] .st-key-prompt_3 button:active {
    background-color: #10243a !important;
    color: #ffffff !important;
}

.stApp [data-testid="stMain"] [data-baseweb="select"] input,
.stApp [data-testid="stMain"] [data-baseweb="select"] [role="combobox"],
.stApp [data-testid="stMain"] [role="option"],
.stApp [data-testid="stMain"] [data-testid="stTable"],
.stApp [data-testid="stMain"] table {
    color: #334155;
}

/* Tabs */
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"],
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"] * {
    color: #334155 !important;
}

.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:hover,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:focus,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:focus-visible,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-hovered],
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-focus-visible],
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:hover *,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:focus *,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"]:focus-visible *,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-hovered] *,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-focus-visible] * {
    background-color: #eef4ff !important;
    color: #10243a !important;
}

.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-selected],
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][aria-selected="true"] {
    background-color: #e8f0ff !important;
    color: #17365d !important;
}

.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-selected] *,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][aria-selected="true"] * {
    color: #17365d !important;
}

.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"] .react-aria-SelectionIndicator {
    background-color: transparent !important;
}

.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][data-selected] .react-aria-SelectionIndicator,
.stApp [data-testid="stMain"] [data-testid="stTabs"] [data-testid="stTab"][role="tab"][aria-selected="true"] .react-aria-SelectionIndicator {
    background-color: var(--blue) !important;
    height: 3px;
}

/* Strategy Simulator metric value */
.stApp [data-testid="stMain"] [data-testid="stMetricValue"],
.stApp [data-testid="stMain"] [data-testid="stMetricValue"] * {
    color: #10243a !important;
}

</style>
""", unsafe_allow_html=True)


PAGES = ["Overview", "AI Assistant", "Skill Shortages", "Internal Talent", "Project Intelligence", "Strategy Simulator", "Data & Insights", "About & Settings"]
if "page" not in st.session_state: st.session_state.page = "Overview"
if "chat_messages" not in st.session_state: st.session_state.chat_messages = []


with st.sidebar:
    st.markdown('<div class="brand">WorkForce<span>IQ</span></div><div class="brand-sub">AI Workforce Intelligence</div>', unsafe_allow_html=True)
    page = st.radio("NAVIGATION", PAGES, key="page", label_visibility="collapsed")
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)

    st.caption("PLATFORM STATUS")
    st.markdown("🟢  Application ready")

    ai_ready = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_MODEL"))
    st.markdown(f"{'🟢' if ai_ready else '⚪'}  Groq {'configured' if ai_ready else 'not configured'}")

    if os.getenv("GROQ_MODEL"):
        st.caption(f"Model · {os.getenv('GROQ_MODEL')}")

    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
    st.caption("WORKFORCEIQ · v1.0")


def option_labels():
    skills = get_options("workforce_recommendations.csv", "skill_name")
    weeks = get_options("workforce_recommendations.csv", "demand_week")
    return skills, weeks

def overview():
    header("Workforce Overview", "Get a clear picture of workforce demand, capacity, skill gaps, and planning recommendations.")
    rec = load_csv("workforce_recommendations.csv")
    dem = load_csv("demand_forecast.csv")
    skill = load_csv("skill_intelligence.csv")
    exc = load_csv("workforce_exceptions.csv")
    active_employees = get_employee_count()
    capacity = load_csv("capacity_analysis.csv")
    weeks = sorted(dem.demand_week.dropna().astype(str).unique()) if not dem.empty and "demand_week" in dem else []
    skills = sorted(rec.skill_name.dropna().astype(str).unique()) if not rec.empty and "skill_name" in rec else []
    projects = load_csv("../projects.csv")
    active_projects = projects[projects.project_status.astype(str).str.casefold() == "active"] if not projects.empty and "project_status" in projects else projects
    c1,c2,c3,c4,c5 = st.columns(5)
    metric(c1,"Active employees",f"{active_employees:,}","Active employee records")
    metric(c2,"Tracked skills",f"{skill.skill_id.nunique():,}" if not skill.empty else "—","Unique skill IDs")
    metric(c3,"Active projects",f"{active_projects.project_id.nunique():,}" if not active_projects.empty else "—","From active project register")
    metric(c4,"Shortage records",f"{int((rec.gap_hours>0).sum()):,}" if not rec.empty else "—","Records with a positive gap")
    metric(c5,"Open exceptions",f"{int((exc.resolution_status.astype(str).str.casefold()=='open').sum()):,}" if not exc.empty else "—","Current exception register")
    st.markdown(" ")
    f1,f2=st.columns(2)
    week_pick=f1.selectbox("Demand week",["All weeks"]+weeks,key="ov_week")
    skill_pick=f2.selectbox("Skill",["All skills"]+skills,key="ov_skill")
    filtered=rec.copy()
    if week_pick!="All weeks" and not filtered.empty: filtered=filtered[filtered.demand_week.astype(str)==week_pick]
    if skill_pick!="All skills" and not filtered.empty: filtered=filtered[filtered.skill_name.astype(str)==skill_pick]
    left,right=st.columns(2)
    with left:
        section("Demand outlook", "Expected workload across selected periods")
        d=dem.copy()
        if week_pick!="All weeks" and not d.empty: d=d[d.demand_week.astype(str)==week_pick]
        if skill_pick!="All skills" and not d.empty:
            ids=filtered.skill_id.astype(str).unique() if not filtered.empty else []
            d=d[d.skill_id.astype(str).isin(ids)]
        if not d.empty:
            chart=d.groupby("demand_week",as_index=True)[[c for c in ["committed_hours","proposed_hours","expected_hours"] if c in d]].sum().sort_index()
            st.area_chart(chart, color=["#2864dc","#6f9cf0","#0b8f8a"][:len(chart.columns)], height=290)
            st.caption("Hours by demand week · source: processed demand forecast")
        else: empty_state("No demand forecast records match these filters.")
    with right:
        section("Shortage by skill", "Largest recorded demand gaps")
        if not filtered.empty:
            sg=filtered.groupby("skill_name").gap_hours.sum().sort_values(ascending=False).head(10).sort_values()
            st.bar_chart(sg, color="#0b8f8a", height=290)
            st.caption("Gap hours · recommendations dataset")
        else: empty_state("No shortage records match these filters.")
    left,right=st.columns(2)
    with left:
        section("Recommendation mix", "Existing decision engine outputs")
        if not filtered.empty:
            st.bar_chart(filtered.recommendation.value_counts(), color="#2864dc", height=235)
        else: empty_state("No recommendations to display.")
    with right:
        section("Recent planning insights", "Derived from the selected workforce records")
        if not filtered.empty:
            top=filtered.sort_values("gap_hours",ascending=False).head(4)
            for _,r in top.iterrows():
                st.markdown(f"**{r.skill_name}** · {r.demand_week}  ")
                st.caption(f"{r.gap_hours:,.0f} gap hours · {r.recommendation}")
        else: empty_state("No insights match the current filters.")
    left,right=st.columns(2)
    with left:
        section("Capacity utilization", "Distribution of workforce availability records")
        if not capacity.empty and "utilization_status" in capacity:
            cap=capacity
            if week_pick!="All weeks" and "availability_date" in cap:
                cap=cap[cap.availability_date.astype(str)==week_pick]
            if not cap.empty: st.bar_chart(cap.utilization_status.value_counts(),color="#0b8f8a",height=235)
            else: empty_state("No capacity records match this demand week.")
        else: empty_state("Capacity utilization data is unavailable.")
def assistant():
    header("Workforce AI Assistant", "Ask questions about workforce demand, skill availability, staffing strategies, and planning decisions.")
    st.markdown('<div class="notice">AI outputs support planning decisions. Recommendations and simulations do not assign employees or execute workforce changes.</div>',unsafe_allow_html=True)
    st.caption("Conversation stays in this page session. The assistant uses only a short, bounded recent context for follow-up questions.")
    if not st.session_state.chat_messages:
        st.markdown(
            """<div class="assistant-welcome">
            <h3>Hello! I'm WorkForceIQ, your AI workforce planning assistant.</h3>
            <p>I can help analyze skill shortages, discover qualified internal employees, and compare workforce strategies.</p>
            </div>""",
            unsafe_allow_html=True,
        )
    prompts = [
        "Analyze the Data Visualization skill shortage.",
        "Find qualified employees for Data Visualization.",
        "Compare workforce strategies for an upcoming shortage.",
        "We have a skill shortage next month. What should we do?"
    ]

    with st.container(key="assistant_suggestions"):
       cols = st.columns(2)

    for i, p in enumerate(prompts):
        if cols[i % 2].button(
            p,
            key=f"prompt_{i}",
            use_container_width=True
        ):
            st.session_state.pending_prompt = p
            st.rerun()
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    if st.session_state.chat_messages and st.button("Clear conversation"):
        st.session_state.chat_messages=[]
        st.session_state.pop("assistant_pending_question", None)
        st.rerun()
    prompt=st.chat_input("Ask about workforce demand, skills, or strategies...")
    if prompt is None and st.session_state.get("pending_prompt"):
        prompt=st.session_state.pop("pending_prompt")
    if prompt:
        from services.agent import (
            bounded_conversation_context,
            combine_pending_clarification,
            is_clarification_response,
            is_new_workforce_question,
        )
        pending_question = st.session_state.pop("assistant_pending_question", None)
        if pending_question and not is_new_workforce_question(prompt):
            assistant_question = next((
                message["content"] for message in reversed(st.session_state.chat_messages)
                if message.get("role") == "assistant"
                and is_clarification_response(message.get("content"))
            ), None)
            effective_prompt = combine_pending_clarification(
                pending_question, prompt, assistant_question
            )
            # The original request and clarification are explicit in this prompt.
            recent_context = []
        else:
            effective_prompt = prompt
            # Do not carry an abandoned clarification into a new request.
            recent_context = [] if pending_question else bounded_conversation_context(
                st.session_state.chat_messages
            )
        st.session_state.chat_messages.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Analyzing workforce data…"):
                try:
                    from services.agent import (
                        run_agent,
                    )
                    answer=run_agent(effective_prompt, conversation_context=recent_context)
                except Exception as e:
                    st.error("The workforce assistant could not complete this request. Please try again.")
                    answer="I couldn't generate a response. Please try a more specific workforce question."
                st.markdown(answer)
        if is_clarification_response(answer):
            st.session_state.assistant_pending_question = effective_prompt
        st.session_state.chat_messages.append({"role":"assistant","content":answer})

def shortage_page():
    header("Skill Shortage Analysis", "Identify workforce demand gaps and understand available internal capacity.")
    skills,weeks=option_labels()
    if not skills: empty_state("Skill recommendation data is unavailable."); return
    a,b,c=st.columns([2,1,1])
    skill=a.selectbox("Skill",skills,key="short_skill")
    week=b.selectbox("Demand week",["All weeks"]+weeks,key="short_week")
    run=c.button("Analyze shortage",type="primary",use_container_width=True)
    if run or "shortage_result" not in st.session_state:
        with st.spinner("Loading shortage analysis…"):
            st.session_state.shortage_result=shortage_tool(skill,None if week=="All weeks" else week)
    result=st.session_state.shortage_result
    if result.get("status")!="success": empty_state(result.get("message","No matching shortage records.")); return
    rows=result.get("records",[])
    if not rows: empty_state("No matching records."); return
    df=__import__("pandas").DataFrame(rows)
    row=df.iloc[0]
    cols=st.columns(5)
    for c,(label,val) in zip(cols,[("Skill ID",row.skill_id),("Demand week",row.demand_week),("Required gap",f"{row.gap_hours:,.1f} hrs"),("Internal employees",f"{row.internal_employees:,}"),("Remaining gap",f"{row.remaining_gap:,.1f} hrs")]): metric(c,label,val)
    section("Capacity comparison", "Existing workforce recommendation records")
    cap=__import__("pandas").DataFrame({"Hours":[row.gap_hours,row.internal_available_hours,row.remaining_gap]},index=["Required gap","Internal available","Remaining gap"])
    st.bar_chart(cap,color="#2864dc",height=200)
    st.markdown(f"**Existing recommendation: {row.recommendation}**")
    rec=load_csv("workforce_recommendations.csv")
    match=rec[(rec.skill_id.astype(str)==str(row.skill_id))&(rec.demand_week.astype(str)==str(row.demand_week))]
    if not match.empty and "recommendation_reason" in match: st.info(str(match.iloc[0].recommendation_reason))
    st.caption(f"Potential trainees: {int(row.potential_trainees):,} · Recommendations use the existing decision rules; this page does not recalculate them.")
    section("Matching records")
    table(df)

def talent_page():
    header("Internal Talent Explorer", "Discover qualified employees who may be available to address workforce skill gaps.")
    skills,weeks=option_labels()
    if not skills: empty_state("Skill data is unavailable."); return
    a,b,c,d=st.columns([2,1.4,1,1])
    skill=a.selectbox("Skill",skills,key="tal_skill")
    date=b.selectbox("Availability date",["Any date"]+weeks,key="tal_date")
    prof=c.selectbox("Minimum proficiency",[1,2,3,4,5],index=2,key="tal_prof")
    limit=d.selectbox("Maximum results",[10,20,50,100],index=1,key="tal_limit")
    if st.button("Find internal talent",type="primary"):
        with st.spinner("Searching qualified talent records…"):
            st.session_state.talent_result=talent_tool(skill,None if date=="Any date" else date,int(prof),int(limit))
    result=st.session_state.get("talent_result")
    if not result: empty_state("Choose search criteria and run a talent search."); return
    if result.get("status")!="success": empty_state(result.get("message","No qualified employees found.")); return
    m1,m2,m3=st.columns(3)
    metric(m1,"Qualified employees",f"{result.get('total_qualified_employees',0):,}","Distinct employee records")
    metric(m2,"Returned",f"{result.get('returned_employees',0):,}",f"Up to {limit} results")
    metric(m3,"Skill / date",skill,result.get("availability_date") or "Any available date")
    section("Potential internal candidates")
    table(__import__("pandas").DataFrame(result.get("employees",[])))
    st.markdown('<div class="notice">These employees are potential candidates only. Availability estimates do not reserve capacity or confirm an assignment. Manager review and approval are required.</div>',unsafe_allow_html=True)

def simulator():
    header("Workforce Strategy Simulator", "Compare different ways of addressing a workforce shortage before making a staffing decision.")
    skills,weeks=option_labels()
    if not skills: empty_state("Strategy inputs are unavailable because recommendation data is missing."); return
    rec=load_csv("workforce_recommendations.csv")
    a,b=st.columns(2)
    skill=a.selectbox("Skill",skills,key="sim_skill")
    skill_rows=rec[rec.skill_name.astype(str)==skill] if not rec.empty else rec
    skill_id=str(skill_rows.iloc[0].skill_id) if not skill_rows.empty else ""
    dates=sorted(skill_rows.demand_week.dropna().astype(str).unique()) if not skill_rows.empty else weeks
    week=b.selectbox("Demand week",dates,key="sim_week")
    if st.button("Compare strategies",type="primary"):
        with st.spinner("Running scenario comparison…"):
            st.session_state.strategy_result=strategy_tool(skill_id,week)
    result=st.session_state.get("strategy_result")
    if result and result.get("skill_id")==skill_id and result.get("demand_week")==week:
        if result.get("status")!="success": empty_state(result.get("message","No scenarios found.")); return
        data=__import__("pandas").DataFrame(result.get("scenarios",[]))
        if data.empty: empty_state("No scenario results returned."); return
        data["estimated_cost_inr"]=data.estimated_cost.map(inr)
        st.columns(3)[0].metric("Scenario options",len(data))
        left,right=st.columns(2)
        with left:
            section("Hours resolved")
            st.bar_chart(data.set_index("strategy")[["hours_resolved"]],color="#0b8f8a")
        with right:
            section("Estimated simulation cost")
            st.bar_chart(data.set_index("strategy")[["estimated_cost"]],color="#2864dc")
            st.caption("Estimated cost (INR ₹)")
        section("Scenario comparison")
        table(data[["strategy","hours_resolved","remaining_gap","estimated_cost_inr"]].rename(columns={"estimated_cost_inr":"Estimated cost (INR)"}))
        winner=data.sort_values(["remaining_gap","estimated_cost"]).iloc[0]
        st.info(f"Comparison summary: **{winner.strategy}** has the lowest remaining gap ({winner.remaining_gap:,.1f} hours) among these simulations. Review cost and operational trade-offs before deciding.")
    st.markdown('<div class="notice">These results are planning simulations. Actual employee allocation, training, or hiring decisions require manager review and approval. Costs are estimated simulation costs, not vendor quotes or confirmed expenditure.</div>',unsafe_allow_html=True)

def data_page():
    header("Data & Insights", "Explore the workforce datasets that power WorkForceIQ analytics.")
    tabs=st.tabs(["Workforce Capacity","Demand Forecast","Skill Intelligence","Workforce Exceptions","Recommendations"])
    specs=[("capacity_analysis.csv",["availability_date","utilization_status"]),("demand_forecast.csv",["demand_week","department"]),("skill_intelligence.csv",["skill_status","skill_category"]),("workforce_exceptions.csv",["exception_type","severity"]),("workforce_recommendations.csv",["demand_week","recommendation"])]
    for tab,(filename,filters) in zip(tabs,specs):
        with tab:
            frame=load_csv(filename)
            if frame.empty: empty_state(f"{filename} is not available or contains no rows."); continue
            n=get_csv_rows(filename)
            st.caption(f"{n:,} records · {get_data_root() / 'processed' / filename}")
            view=frame.copy()
            fs=st.columns(len(filters)+1)
            for i,col in enumerate(filters):
                if col in view:
                    opts=sorted(view[col].dropna().astype(str).unique())
                    chosen=fs[i].selectbox(col.replace("_"," ").title(),["All"]+opts,key=f"{filename}_{col}")
                    if chosen!="All": view=view[view[col].astype(str)==chosen]
            query=fs[-1].text_input("Search loaded records",key=f"{filename}_search")
            if query:
                mask=view.astype(str).apply(lambda s:s.str.contains(query,case=False,na=False)).any(axis=1)
                view=view[mask]
            if not view.empty:
                if filename=="capacity_analysis.csv":
                    metrics=st.columns(3)
                    metric(metrics[0],"Available hours",f"{view.available_hours.sum():,.0f}")
                    metric(metrics[1],"Allocated hours",f"{view.allocated_hours.sum():,.0f}")
                    metric(metrics[2],"Remaining hours",f"{view.remaining_hours.sum():,.0f}")
                elif filename=="demand_forecast.csv":
                    section("Expected hours by week")
                    st.line_chart(view.groupby("demand_week").expected_hours.sum().sort_index(),color="#2864dc")
                elif filename=="workforce_exceptions.csv":
                    section("Exception categories")
                    st.bar_chart(view.exception_type.value_counts(),color="#c88018")
                elif filename=="skill_intelligence.csv":
                    section("Skill status distribution")
                    st.bar_chart(view.skill_status.value_counts(),color="#2864dc")
                elif filename=="workforce_recommendations.csv":
                    section("Recommendation categories")
                    st.bar_chart(view.recommendation.value_counts(),color="#0b8f8a")
                table(view.head(500))
                st.caption("Showing at most 500 rows from the loaded dataset view.")
            else: empty_state("No records match these filters.")

def about():
    header("About & Settings", "Application information and local configuration status.")
    rec=load_csv("workforce_recommendations.csv")
    configured = bool(os.getenv("GROQ_API_KEY") and os.getenv("GROQ_MODEL"))
    c1,c2,c3=st.columns(3)
    metric(c1,"Application","Ready","WorkForceIQ · v1.0")
    metric(c2,"Data availability","Available" if not rec.empty else "Unavailable","Processed recommendation data")
    metric(c3,"AI configuration","Configured" if configured else "Not configured","Groq settings presence only")
    section("Product")
    st.write("WorkForceIQ is an AI-powered workforce planning and decision-support platform for demand forecasting, skill gap analysis, internal talent discovery, and scenario comparison.")
    section("Technology")
    st.write("Python · Streamlit · Pandas · Groq · Groq SDK · WorkForceIQ workforce analytics modules")
    st.write("Provider: Groq")
    st.write(f"Model: {os.getenv('GROQ_MODEL') or 'Not configured'}")
    st.write(f"Required configuration present: {'Yes' if configured else 'No'}")
    st.caption("Configuration status checks local environment variable presence. No API key is displayed and no Groq request is made for this status.")
    section("Decision support")
    st.write("Recommendations and simulated outcomes support workforce planning. They do not confirm employee allocation, training enrollment, hiring, or expenditure.")

{
    "Overview": overview,
    "AI Assistant": assistant,
    "Skill Shortages": shortage_page,
    "Internal Talent": talent_page,
    "Project Intelligence": render_project_intelligence_page,
    "Strategy Simulator": simulator,
    "Data & Insights": data_page,
    "About & Settings": about,
}[page]()
