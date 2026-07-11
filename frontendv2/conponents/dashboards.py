import streamlit as st
import pandas as pd
import plotly.express as px


def _bmi_category(bmi):

    if bmi < 18.5:
        return "Underweight"
    elif bmi < 25:
        return "Normal"
    elif bmi < 30:
        return "Overweight"
    else:
        return "Obese"


def render_dashboard(chat):

    st.markdown("### ⚖️ BMI Calculator")

    col1, col2 = st.columns(2)

    with col1:
        weight = st.number_input("Weight (kg)", min_value=1.0, max_value=300.0, value=70.0, step=0.5)

    with col2:
        height = st.number_input("Height (cm)", min_value=50.0, max_value=250.0, value=170.0, step=0.5)

    if height > 0:
        bmi = weight / ((height / 100) ** 2)
        category = _bmi_category(bmi)
        st.metric("Your BMI", f"{bmi:.1f}", category)

    st.divider()

    report = chat.get("report")

    if not report or not report.get("analysis"):
        st.info("📄 Upload a lab report in this chat to see personalized health charts here.")
        return

    st.markdown("### 🧪 Lab Results Overview")

    rows = []

    for section in report["analysis"]:

        report_type = section.get("report_type", "Report")

        for name, info in section.get("parameters", {}).items():

            rows.append({
                "Test": name,
                "Category": report_type,
                "Status": info.get("status", "Normal") or "Normal",
                "Value": info.get("value", "")
            })

    if not rows:
        st.info("No structured lab values were found in this report.")
        return

    df = pd.DataFrame(rows)

    color_map = {"High": "#ef4444", "Low": "#f59e0b", "Borderline": "#f97316", "Normal": "#10b981"}

    status_counts = df["Status"].value_counts().reset_index()
    status_counts.columns = ["Status", "Count"]

    col_a, col_b = st.columns(2)

    with col_a:
        fig_pie = px.pie(
            status_counts,
            names="Status",
            values="Count",
            color="Status",
            color_discrete_map=color_map,
            title="Overall Test Status"
        )
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_b:
        category_counts = df.groupby(["Category", "Status"]).size().reset_index(name="Count")

        fig_bar = px.bar(
            category_counts,
            x="Category",
            y="Count",
            color="Status",
            color_discrete_map=color_map,
            title="Breakdown by Test Category"
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("### 🔎 Abnormal Values")

    abnormal_df = df[df["Status"] != "Normal"][["Test", "Category", "Value", "Status"]]

    if abnormal_df.empty:
        st.success("All values are within normal range! 🎉")
    else:
        st.dataframe(abnormal_df, use_container_width=True, hide_index=True)