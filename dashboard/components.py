import pandas as pd
import streamlit as st


def header(title: str, subtitle: str) -> None:
    st.markdown(f'<h1 class="page-title">{title}</h1><div class="page-sub">{subtitle}</div>', unsafe_allow_html=True)


def metric(container, label: str, value: str, note: str = "") -> None:
    container.markdown(
        f'<div class="card"><div class="metric-label">{label}</div>'
        f'<div class="metric-value">{value}</div><div class="metric-note">{note}</div></div>',
        unsafe_allow_html=True,
    )


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f'<div class="section-title">{title}</div>', unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def table(frame: pd.DataFrame) -> None:
    if frame is None or frame.empty:
        empty_state("No records to display.")
        return
    st.dataframe(frame, use_container_width=True, hide_index=True, height=min(420, 40 + 35 * min(len(frame), 10)))


def empty_state(message: str) -> None:
    st.info(message)


def inr(value) -> str:
    try:
        amount = int(round(float(value)))
    except (TypeError, ValueError):
        return "—"
    sign = "−" if amount < 0 else ""
    digits = str(abs(amount))
    if len(digits) <= 3:
        grouped = digits
    else:
        grouped = digits[-3:]
        digits = digits[:-3]
        while digits:
            grouped = digits[-2:] + "," + grouped
            digits = digits[:-2]
    return f"{sign}₹{grouped}"
