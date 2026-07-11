import streamlit as st


STATUS_ICON = {
    "High": "🔴",
    "Low": "🟡",
    "Normal": "🟢"
}


def show_report(report):

    if report is None:
        return

    st.divider()

    st.subheader("📊 Medical Report")

    for section in report["analysis"]:

        with st.expander(
            section["report_type"],
            expanded=False
        ):

            parameters = section["parameters"]

            for name, info in parameters.items():

                value = info.get("value", "-")

                unit = info.get("unit", "")

                status = info.get(
                    "status",
                    ""
                )

                icon = STATUS_ICON.get(
                    status,
                    "⚪"
                )

                col1, col2, col3 = st.columns(
                    [3,2,1]
                )

                col1.write(name)

                col2.write(
                    f"{value} {unit}"
                )

                col3.write(
                    f"{icon} {status}"
                )