import streamlit as st

STATUS_ICON = {
    "High": "🔴",
    "Low": "🟡",
    "Borderline": "🟠",
    "Normal": "🟢",
    "Unknown": "⚪",
}

STATUS_HELP = {
    "Unknown": "This value could not be interpreted automatically. "
               "It is not a statement that the value is normal.",
}


def show_report(report) -> None:

    if not report or not report.get("analysis"):
        return

    st.divider()
    st.subheader("📊 Medical report")

    unknown_total = 0

    for section in report["analysis"]:

        with st.expander(section.get("report_type", "Report"), expanded=False):

            for name, info in (section.get("parameters") or {}).items():

                if not isinstance(info, dict):
                    continue

                status = info.get("status", "") or ""

                if status == "Unknown":
                    unknown_total += 1

                name_column, value_column, status_column = st.columns([3, 2, 2])

                name_column.write(name)
                value_column.write(f"{info.get('value', '-')} {info.get('unit', '')}".strip())
                status_column.write(
                    f"{STATUS_ICON.get(status, '⚪')} {status}",
                    help=STATUS_HELP.get(status),
                )

    if unknown_total:
        # These used to be reported as "Normal", so a value the analyser
        # could not read looked identical to a healthy one.
        st.warning(
            f"{unknown_total} value(s) could not be interpreted and are marked "
            "**Unknown**. Please confirm them with your clinician."
        )
