"""DataPulse AI — Streamlit Analytics Dashboard Application.

Intelligent Data Quality Monitoring, Statistical Profiling, Anomaly Diagnostics,
and Safe Data Remediation with Secure JWT Authentication & Isolated Guest Sandbox.
"""

import os
import sys
from pathlib import Path
import json
from typing import Any, Dict, List, Optional
import streamlit as st
import pandas as pd

# Ensure repository root is on sys.path and does not get shadowed by dashboard/app.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# If 'app' in sys.modules points to dashboard/app.py instead of the app/ package directory,
# remove it so imports like `from app.services...` correctly resolve to the app package.
if "app" in sys.modules and not hasattr(sys.modules["app"], "__path__"):
    del sys.modules["app"]

# Load .env file automatically so DATAPULSE_API_URL and other settings take effect on launch
try:
    from dotenv import load_dotenv
    load_dotenv(_PROJECT_ROOT / ".env")
except ImportError:
    pass

try:
    from dashboard.api_client import DataPulseApiClient, DashboardApiError
    from dashboard.auth_page import render_auth_landing_page
    from dashboard.guest_sandbox import (
        load_default_guest_dataset,
        profile_guest_dataset,
        simulate_guest_remediation,
        apply_guest_remediation,
    )
    from dashboard.components import (
        render_score_gauge,
        render_component_breakdown,
        render_issue_severity_distribution,
        render_column_quality_bar,
        display_ai_analysis_report,
    )
    from dashboard.theme import (
        apply_custom_theme,
        render_brand_sidebar,
        render_header,
        render_safety_guarantee_banner,
    )
    from dashboard.sample_demo import get_sample_ai_report
except ImportError:
    from api_client import DataPulseApiClient, DashboardApiError  # type: ignore
    from auth_page import render_auth_landing_page  # type: ignore
    from guest_sandbox import (  # type: ignore
        load_default_guest_dataset,
        profile_guest_dataset,
        simulate_guest_remediation,
        apply_guest_remediation,
    )
    from components import (  # type: ignore
        render_score_gauge,
        render_component_breakdown,
        render_issue_severity_distribution,
        render_column_quality_bar,
        display_ai_analysis_report,
    )
    from theme import (  # type: ignore
        apply_custom_theme,
        render_brand_sidebar,
        render_header,
        render_safety_guarantee_banner,
    )
    from sample_demo import get_sample_ai_report  # type: ignore


# -----------------------------------------------------------------------------
# 1. Page Configuration & Visual Theme
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="DataPulse AI — Data Quality Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Apply global dark SaaS styling
apply_custom_theme()


# -----------------------------------------------------------------------------
# 2. Session State Initialization
# -----------------------------------------------------------------------------
if "backend_url" not in st.session_state:
    st.session_state.backend_url = (
        os.environ.get("DATAPULSE_API_URL")
        or os.environ.get("BACKEND_URL")
        or "http://127.0.0.1:8000"
    )

if "auth_token" not in st.session_state:
    st.session_state.auth_token = None
if "user_profile" not in st.session_state:
    st.session_state.user_profile = None
if "is_guest" not in st.session_state:
    st.session_state.is_guest = False
if "guest_data" not in st.session_state:
    st.session_state.guest_data = None

if "selected_dataset_id" not in st.session_state:
    st.session_state.selected_dataset_id = None
if "selected_run_id" not in st.session_state:
    st.session_state.selected_run_id = None
if "ai_analysis_result" not in st.session_state:
    st.session_state.ai_analysis_result = None
if "remediation_preview" not in st.session_state:
    st.session_state.remediation_preview = None
if "remediation_result" not in st.session_state:
    st.session_state.remediation_result = None

# Initialize client with current token (or None)
client = DataPulseApiClient(
    base_url=st.session_state.backend_url,
    token=st.session_state.auth_token,
)


# -----------------------------------------------------------------------------
# 3. Authentication Landing Page Gate
# -----------------------------------------------------------------------------
# If user is neither signed in with a JWT nor in Guest Mode, show Auth Landing Page
if not st.session_state.auth_token and not st.session_state.is_guest:
    render_auth_landing_page(client)
    st.stop()


# -----------------------------------------------------------------------------
# 4. Persistent Left Sidebar Navigation
# -----------------------------------------------------------------------------
with st.sidebar:
    st.title("⚡ DataPulse AI")
    st.caption("DATA QUALITY INTELLIGENCE")

    # Mode Indicator & Sign-Out / Exit Button
    if st.session_state.is_guest:
        st.markdown(
            """
            <div style="background-color: rgba(6, 182, 212, 0.12); border: 1px solid rgba(6, 182, 212, 0.3); border-radius: 8px; padding: 0.65rem 0.85rem; margin-bottom: 0.75rem;">
                <div style="color: #38bdf8; font-weight: 600; font-size: 0.9rem;">👀 Guest Sandbox Active</div>
                <div style="color: #94a3b8; font-size: 0.78rem;">Isolated In-Memory Sandbox • No Cloud Writes</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚪 Exit Guest Session", type="secondary", use_container_width=True):
            st.session_state.is_guest = False
            st.session_state.guest_data = None
            st.session_state.selected_dataset_id = None
            st.session_state.selected_run_id = None
            st.rerun()
    else:
        user = st.session_state.user_profile or {}
        user_name = user.get("full_name") or user.get("email", "User")
        user_email = user.get("email", "")
        st.markdown(
            f"""
            <div style="background-color: rgba(37, 99, 235, 0.12); border: 1px solid rgba(56, 189, 248, 0.25); border-radius: 8px; padding: 0.65rem 0.85rem; margin-bottom: 0.75rem;">
                <div style="color: #60a5fa; font-weight: 600; font-size: 0.9rem;">👤 {user_name}</div>
                <div style="color: #94a3b8; font-size: 0.78rem;">{user_email} • Tenant Owner</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        if st.button("🚪 Sign Out", type="secondary", use_container_width=True):
            st.session_state.auth_token = None
            st.session_state.user_profile = None
            st.session_state.selected_dataset_id = None
            st.session_state.selected_run_id = None
            client.set_token(None)
            st.rerun()

    # Clean native connectivity check
    try:
        health = client.check_health()
        app_name = health.get("app", "DataPulse AI")
        app_ver = health.get("version", "0.1.0")
        st.success(f"● {app_name} v{app_ver} Online")
    except DashboardApiError:
        st.error("● Backend Offline")

    st.divider()
    st.caption("PLATFORM NAVIGATION")

    nav_option = st.radio(
        "Navigation Menu",
        options=[
            "📊 Overview & Ingestion",
            "🔍 Quality Deep-Dive",
            "⚖️ Historical Run Comparison",
            "🤖 AI Root-Cause Diagnostics",
            "🛠️ Data Remediation & Revalidation",
        ],
        index=0,
        label_visibility="collapsed",
    )

    st.divider()

    with st.expander("⚙️ Connection Settings", expanded=False):
        new_url = st.text_input(
            "Backend API URL",
            value=st.session_state.backend_url,
            help="Base URL for DataPulse FastAPI backend",
        )
        if new_url != st.session_state.backend_url:
            st.session_state.backend_url = new_url
            st.rerun()

    st.caption("DataPulse AI Enterprise • v0.1.0\n\nNeon PostgreSQL & S3 Storage")


# Clean navigation string for routing
active_view = nav_option.split(" ", 1)[1] if " " in nav_option else nav_option


# -----------------------------------------------------------------------------
# Helper: Handle 401 Session Expiration
# -----------------------------------------------------------------------------
def handle_api_error(exc: DashboardApiError) -> None:
    """Handle API errors with specific guidance on token expiration."""
    if exc.status_code == 401:
        st.error("🔒 **Session Expired**: Your access token has expired or is invalid. Please sign in again.")
        st.session_state.auth_token = None
        st.session_state.user_profile = None
        if st.button("Return to Sign In", type="primary"):
            st.rerun()
    elif exc.status_code == 403:
        st.error("⛔ **Access Denied**: You do not have permission to access or modify this dataset.")
    elif exc.status_code == 404:
        st.warning("🔍 **Resource Not Found**: The requested dataset or profiling run does not exist or belongs to another user.")
    else:
        st.error(f"API Error ({exc.status_code}): {exc.message}")


# -----------------------------------------------------------------------------
# View 1: Overview & CSV Ingestion
# -----------------------------------------------------------------------------
if active_view == "Overview & Ingestion":
    render_header(
        title="Overview & Dataset Ingestion",
        subtitle="Upload raw datasets for automated statistical profiling, explainable quality scoring, and anomaly detection.",
        icon="📊",
    )

    # -------------------------------------------------------------------------
    # A. Guest Mode Experience (Isolated In-Memory Sandbox)
    # -------------------------------------------------------------------------
    if st.session_state.is_guest:
        st.info(
            "**Welcome to DataPulse AI Guest Sandbox** — Explore automated data profiling without cloud storage writes. "
            "Ingest our curated synthetic dataset or upload a small CSV to calculate explainable quality scores (0–100), "
            "detect IQR outliers, and preview data remediation."
        )

        col_g_load, col_g_up = st.columns([1.2, 1.4], gap="large")

        with col_g_load:
            st.markdown("#### ⚡ Synthetic Sample Dataset")
            st.caption("Curated e-commerce transactions featuring missing emails, duplicates, whitespace anomalies, and extreme order amounts ($1.25M).")
            if st.button("📊 Profile Synthetic E-Commerce Dataset", type="primary", use_container_width=True):
                with st.spinner("Executing in-memory statistical profiling..."):
                    df = load_default_guest_dataset()
                    profile_res = profile_guest_dataset(df)
                    st.session_state.guest_data = profile_res
                    st.success(f"✓ Profiled {len(df)} rows! Quality Score: {profile_res['quality_score']}/100")

        with col_g_up:
            st.markdown("#### 📁 Upload Custom CSV (Sandbox Mode)")
            st.caption("Upload a small CSV dataset (< 2MB) to test automated profiling in this temporary sandbox.")
            guest_uploaded_file = st.file_uploader(
                "Upload small CSV file for sandbox",
                type=["csv"],
                help="Sandbox upload limit: 2MB. Evaluated strictly in-memory without database persistence.",
                label_visibility="collapsed",
                key="guest_csv_uploader",
            )
            if guest_uploaded_file is not None:
                if st.button("🚀 Ingest & Profile Uploaded CSV", type="secondary", use_container_width=True):
                    try:
                        df_custom = pd.read_csv(guest_uploaded_file)
                        if len(df_custom) > 10000:
                            st.warning("⚠️ Sandbox row limit is 10,000 rows. Truncating for quick in-memory evaluation.")
                            df_custom = df_custom.head(10000)
                        profile_res = profile_guest_dataset(df_custom)
                        st.session_state.guest_data = profile_res
                        st.success(f"✓ Profiled {len(df_custom)} rows! Quality Score: {profile_res['quality_score']}/100")
                    except Exception as e:
                        st.error(f"Cannot parse CSV: {e}")

        # Initialize default synthetic dataset if guest hasn't loaded anything yet
        if st.session_state.guest_data is None:
            df_default = load_default_guest_dataset()
            st.session_state.guest_data = profile_guest_dataset(df_default)

        # Display Quick Results KPI Grid for Guest
        g_data = st.session_state.guest_data
        st.divider()
        st.subheader("📋 Sandbox Quality Overview")

        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
        kpi1.metric("Overall Quality Score", f"{g_data['quality_score']}/100")
        kpi2.metric("Profiled Rows", g_data["total_rows_profiled"])
        kpi3.metric("Profiled Columns", g_data["total_columns_profiled"])
        kpi4.metric("Quality Issues", g_data["issues_count"])

        g_col1, g_col2 = st.columns([1, 1], gap="medium")
        with g_col1:
            st.plotly_chart(render_score_gauge(g_data["quality_score"]), use_container_width=True)
        with g_col2:
            comp_fig = render_component_breakdown(g_data.get("component_scores", {}))
            if comp_fig:
                st.plotly_chart(comp_fig, use_container_width=True)

        st.caption("👉 Switch to **Quality Deep-Dive** in the sidebar to inspect column distributions and detected issues!")

    # -------------------------------------------------------------------------
    # B. Authenticated User Experience (Tenant-Scoped AWS Ingestion)
    # -------------------------------------------------------------------------
    else:
        st.info(
            "**Welcome to DataPulse AI Enterprise** — Ingest CSV datasets to automatically calculate "
            "deterministic 0–100 quality scores, detect numeric IQR outliers, and safely store immutable snapshots in private S3."
        )

        st.divider()

        col_upload, col_meta = st.columns([1.6, 1.2], gap="large")

        with col_upload:
            st.subheader("📁 Upload CSV Dataset")
            st.caption("Drag and drop or browse for a comma-separated CSV file (up to 10MB on AWS API Gateway).")
            uploaded_file = st.file_uploader(
                "Choose a CSV file",
                type=["csv"],
                help="Upload a standard CSV file (limit 10MB to match cloud API Gateway limits)",
                label_visibility="collapsed",
            )

        with col_meta:
            st.subheader("🏷️ Ingestion Metadata (Optional)")
            st.caption("Customize dataset naming, semantic versioning, or schema validation rules.")
            custom_dataset_name = st.text_input(
                "Dataset Name",
                placeholder="e.g., customer_transactions",
                help="Leave blank to use original uploaded file name",
            )
            custom_description = st.text_input(
                "Description (Optional)",
                placeholder="e.g., Customer transaction records",
                help="Optional description of dataset",
            )
            custom_version_tag = st.text_input(
                "Version Tag",
                placeholder="e.g., v1.0.0",
                help="Leave blank for an automatic timestamped version tag",
            )
            custom_schema_str = st.text_area(
                "Expected Schema (JSON, Optional)",
                placeholder='{"columns": {"id": "int64", "email": "str", "salary": "float64"}}',
                help="Optional Pandera schema definition for strict column type validation",
                height=85,
            )

        if uploaded_file is not None:
            if st.button("🚀 Upload & Execute Profiling", type="primary", use_container_width=True):
                with st.spinner("Streaming dataset to secure S3 storage and executing statistical profiling..."):
                    try:
                        file_bytes = uploaded_file.getvalue()
                        filename = uploaded_file.name

                        summary_res = client.upload_csv(
                            file_bytes=file_bytes,
                            filename=filename,
                            name=custom_dataset_name.strip() if custom_dataset_name else None,
                            description=custom_description.strip() if custom_description else None,
                            version_tag=custom_version_tag.strip() if custom_version_tag else None,
                        )

                        # If endpoint returns DatasetDetailRead, fetch latest run summary for display
                        dataset_id = summary_res.get("id")
                        if dataset_id:
                            st.session_state.selected_dataset_id = dataset_id
                            try:
                                runs = client.list_runs_for_dataset(dataset_id)
                                if runs:
                                    latest_run = runs[0]
                                    run_id = latest_run["id"]
                                    st.session_state.selected_run_id = run_id
                                    summary_res = client.get_run_summary(run_id)
                            except Exception:
                                pass
                        elif summary_res.get("run_id"):
                            st.session_state.selected_run_id = summary_res.get("run_id")

                        st.success(
                            f"✓ Profiling completed successfully! Run ID: #{summary_res.get('run_id')} "
                            f"| Quality Score: {summary_res.get('quality_score')}/100"
                        )

                        # Display Quick Results KPI Grid
                        kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                        kpi1.metric("Overall Quality Score", f"{summary_res.get('quality_score')}/100")
                        kpi2.metric("Profiled Rows", summary_res.get("total_rows_profiled") or "N/A")
                        kpi3.metric("Profiled Columns", summary_res.get("total_columns_profiled") or "N/A")
                        kpi4.metric("Quality Issues", summary_res.get("issues_count", 0))

                        g_col1, g_col2 = st.columns([1, 1], gap="medium")
                        with g_col1:
                            st.plotly_chart(render_score_gauge(summary_res.get("quality_score")), use_container_width=True)
                        with g_col2:
                            comp_fig = render_component_breakdown(summary_res.get("component_scores", {}))
                            if comp_fig:
                                st.plotly_chart(comp_fig, use_container_width=True)

                    except DashboardApiError as exc:
                        handle_api_error(exc)

        st.divider()

        # Registered Datasets Catalog Section
        st.subheader("📚 Your Registered Datasets Catalog")
        st.caption("Catalog of datasets owned by your account tracked in Neon PostgreSQL.")
        try:
            datasets = client.list_datasets()
            if datasets:
                df_datasets = pd.DataFrame(datasets)
                display_cols = [c for c in ["id", "name", "source_type", "created_at", "updated_at"] if c in df_datasets.columns]
                df_display = df_datasets[display_cols].copy()
                df_display.rename(columns={
                    "id": "Dataset ID",
                    "name": "Dataset Name",
                    "source_type": "Source Type",
                    "created_at": "Created At",
                    "updated_at": "Last Updated",
                }, inplace=True)
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.info("No datasets registered yet. Upload a CSV above to start monitoring data quality.")
        except DashboardApiError as e:
            handle_api_error(e)


# -----------------------------------------------------------------------------
# View 2: Quality Deep-Dive
# -----------------------------------------------------------------------------
elif active_view == "Quality Deep-Dive":
    render_header(
        title="Quality Profiling Deep-Dive",
        subtitle="Inspect granular column metrics, statistical quartiles, and detected quality issues.",
        icon="🔍",
    )

    if st.session_state.is_guest:
        # ---------------------------------------------------------------------
        # Guest Mode Deep-Dive
        # ---------------------------------------------------------------------
        if st.session_state.guest_data is None:
            st.session_state.guest_data = profile_guest_dataset(load_default_guest_dataset())

        g_data = st.session_state.guest_data

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Overall Quality Score", f"{g_data['quality_score']}/100")
        k1_rows = g_data['total_rows_profiled']
        k2.metric("Profiled Rows", k1_rows)
        k3.metric("Anomalous Metrics", g_data.get("anomalous_metrics_count", 0))
        k4.metric("Detected Issues", g_data.get("issues_count", 0))

        st.divider()
        tab_summary, tab_columns, tab_issues = st.tabs([
            "📊 Score & Dimensions Breakdown",
            "📈 Column Metrics & IQR Outliers",
            "⚠️ Detected Quality Issues",
        ])

        with tab_summary:
            c1, c2 = st.columns([1, 1], gap="medium")
            with c1:
                st.plotly_chart(render_score_gauge(g_data["quality_score"]), use_container_width=True)
            with c2:
                comp_fig = render_component_breakdown(g_data.get("component_scores", {}))
                if comp_fig:
                    st.plotly_chart(comp_fig, use_container_width=True)
                if g_data.get("score_explanation"):
                    st.info(f"**Score Deductions & Reasons**: {g_data['score_explanation']}")

        with tab_columns:
            metrics = g_data.get("metrics", [])
            if metrics:
                chart_fig = render_column_quality_bar(metrics)
                if chart_fig:
                    st.plotly_chart(chart_fig, use_container_width=True)

                df_metrics = pd.DataFrame(metrics)
                st.dataframe(df_metrics, use_container_width=True, hide_index=True)

        with tab_issues:
            issues = g_data.get("issues", [])
            if issues:
                iss_fig = render_issue_severity_distribution(issues)
                if iss_fig:
                    st.plotly_chart(iss_fig, use_container_width=True)
                df_issues = pd.DataFrame(issues)
                st.dataframe(df_issues, use_container_width=True, hide_index=True)
            else:
                st.success("✓ Zero quality defects detected!")

    else:
        # ---------------------------------------------------------------------
        # Authenticated Mode Deep-Dive
        # ---------------------------------------------------------------------
        try:
            datasets = client.list_datasets()
        except DashboardApiError as e:
            handle_api_error(e)
            datasets = []

        if not datasets:
            st.info("No datasets found in your catalog. Please upload a dataset first in Overview & Ingestion.")
        else:
            dataset_options = {d["id"]: f"{d['name']} (ID: #{d['id']})" for d in datasets}
            col_ds, col_rn = st.columns(2, gap="medium")

            with col_ds:
                selected_d_id = st.selectbox(
                    "Select Monitored Dataset",
                    options=list(dataset_options.keys()),
                    format_func=lambda x: dataset_options[x],
                )

            runs = client.list_runs_for_dataset(selected_d_id)
            if not runs:
                st.info("No profiling runs found for this dataset. Upload a version snapshot to run profiling.")
            else:
                run_options = {
                    r["id"]: f"Run #{r['id']} — Status: {r['status']} | Score: {r.get('quality_score', 'N/A')}/100 | {r['created_at'][:19]}"
                    for r in runs
                }
                with col_rn:
                    selected_run_id = st.selectbox(
                        "Select Profiling Run Snapshot",
                        options=list(run_options.keys()),
                        format_func=lambda x: run_options[x],
                    )

                run_details = client.get_run(selected_run_id)
                summary_info = client.get_run_summary(selected_run_id)

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Overall Quality Score", f"{run_details.get('quality_score') or 0.0}/100")
                k2.metric("Profiled Rows", run_details.get("total_rows_profiled") or 0)
                k3.metric("Anomalous Metrics", summary_info.get("anomalous_metrics_count", 0))
                k4.metric("Detected Issues", summary_info.get("issues_count", 0))

                st.divider()
                tab_summary, tab_columns, tab_issues = st.tabs([
                    "📊 Score & Dimensions Breakdown",
                    "📈 Column Metrics & IQR Outliers",
                    "⚠️ Detected Quality Issues",
                ])

                with tab_summary:
                    c1, c2 = st.columns([1, 1], gap="medium")
                    with c1:
                        st.plotly_chart(render_score_gauge(run_details.get("quality_score")), use_container_width=True)
                    with c2:
                        comp_fig = render_component_breakdown(summary_info.get("component_scores", {}))
                        if comp_fig:
                            st.plotly_chart(comp_fig, use_container_width=True)
                        if summary_info.get("score_explanation"):
                            st.info(f"**Score Deductions & Reasons**: {summary_info.get('score_explanation')}")

                with tab_columns:
                    metrics = client.get_run_metrics(selected_run_id)
                    if metrics:
                        chart_fig = render_column_quality_bar(metrics)
                        if chart_fig:
                            st.plotly_chart(chart_fig, use_container_width=True)

                        df_metrics = pd.DataFrame(metrics)
                        st.dataframe(df_metrics, use_container_width=True, hide_index=True)

                with tab_issues:
                    issues = client.get_run_issues(selected_run_id)
                    if issues:
                        iss_fig = render_issue_severity_distribution(issues)
                        if iss_fig:
                            st.plotly_chart(iss_fig, use_container_width=True)

                        df_issues = pd.DataFrame(issues)
                        st.dataframe(df_issues, use_container_width=True, hide_index=True)
                    else:
                        st.success("✓ Zero quality defects detected! All schema checks, null bounds, and statistical rules passed.")


# -----------------------------------------------------------------------------
# View 3: Historical Run Comparison
# -----------------------------------------------------------------------------
elif active_view == "Historical Run Comparison":
    render_header(
        title="Historical Profiling Run Comparison",
        subtitle="Evaluate data drift, score progression, schema changes, and resolved issues between two profiling runs.",
        icon="⚖️",
    )

    if st.session_state.is_guest:
        st.info(
            "ℹ️ **Account Feature: Historical Run Tracking**\n\n"
            "Guest sessions operate in a temporary in-memory sandbox. Historical run comparison compares "
            "version snapshots and quality deltas stored persistently in Neon PostgreSQL.\n\n"
            "👉 To monitor production datasets and track quality deltas across version releases, sign out and create an account."
        )
    else:
        try:
            datasets = client.list_datasets()
        except DashboardApiError as e:
            handle_api_error(e)
            datasets = []

        if not datasets:
            st.info("No datasets available for comparison.")
        else:
            dataset_options = {d["id"]: f"{d['name']} (ID: #{d['id']})" for d in datasets}
            selected_d_id = st.selectbox(
                "Select Dataset for Comparison",
                options=list(dataset_options.keys()),
                format_func=lambda x: dataset_options[x],
                key="comp_dataset_select",
            )

            runs = client.list_runs_for_dataset(selected_d_id)
            if len(runs) < 2:
                st.warning("⚠️ Comparison requires at least 2 completed profiling runs for this dataset to evaluate delta metrics.")
            else:
                col_b, col_t = st.columns(2, gap="medium")
                run_opts = {r["id"]: f"Run #{r['id']} (Score: {r.get('quality_score', 'N/A')}/100 | {r['created_at'][:19]})" for r in runs}

                with col_b:
                    baseline_id = st.selectbox(
                        "Baseline Run (Older / Benchmark)",
                        options=list(run_opts.keys()),
                        format_func=lambda x: run_opts[x],
                        index=min(1, len(runs) - 1),
                    )
                with col_t:
                    target_id = st.selectbox(
                        "Target Run (Newer / Current)",
                        options=list(run_opts.keys()),
                        format_func=lambda x: run_opts[x],
                        index=0,
                    )

                if baseline_id == target_id:
                    st.info("Select two distinct runs above to generate comparative quality deltas.")
                else:
                    if st.button("⚖️ Compare Runs", type="primary"):
                        with st.spinner("Comparing profiling runs and evaluating schema shifts..."):
                            try:
                                comp = client.compare_runs(
                                    dataset_id=selected_d_id,
                                    baseline_run_id=baseline_id,
                                    target_run_id=target_id,
                                )

                                c1, c2, c3 = st.columns(3)
                                prev_score = comp.get("previous_score") or 0.0
                                curr_score = comp.get("current_score") or 0.0
                                score_delta = comp.get("score_change") or 0.0

                                c1.metric(
                                    label="Quality Score Progression",
                                    value=f"{curr_score}/100",
                                    delta=f"{score_delta:+0.2f} pts" if score_delta != 0 else "0.0 pts (Unchanged)",
                                )

                                metric_changes = comp.get("metric_changes", {})
                                row_diff = metric_changes.get("row_count_diff")
                                c2.metric(
                                    label="Row Count Shift",
                                    value=metric_changes.get("total_rows_current", "N/A"),
                                    delta=f"{row_diff:+d} rows" if row_diff is not None else None,
                                )

                                c3.metric(
                                    label="Schema Compatibility",
                                    value="Compatible" if comp.get("schema_compatible") else "Schema Shift",
                                )

                                col_new, col_res = st.columns(2, gap="medium")
                                with col_new:
                                    st.subheader("🚨 Newly Emerged Issues")
                                    new_issues = comp.get("new_issues", [])
                                    if new_issues:
                                        for ni in new_issues:
                                            st.error(f"- {ni}")
                                    else:
                                        st.success("✓ Zero new issues introduced between runs.")

                                with col_res:
                                    st.subheader("✨ Resolved Issues")
                                    res_issues = comp.get("resolved_issues", [])
                                    if res_issues:
                                        for ri in res_issues:
                                            st.success(f"✓ {ri}")
                                    else:
                                        st.info("No previously flagged defects were resolved in this run.")

                            except DashboardApiError as e:
                                handle_api_error(e)


# -----------------------------------------------------------------------------
# View 4: AI Root-Cause Diagnostics
# -----------------------------------------------------------------------------
elif active_view == "AI Root-Cause Diagnostics":
    render_header(
        title="AI-Powered Root-Cause Analysis",
        subtitle="Diagnose data quality degradation, missing values, outliers, and schema shifts using grounded LLM reasoning and prioritized corrective recommendations.",
        icon="🤖",
    )

    if st.session_state.is_guest:
        st.caption("Demonstration Report for Sandbox Exploration:")
        demo_report = get_sample_ai_report(dataset_name="synthetic_customer_orders_sandbox", run_id=1)
        display_ai_analysis_report(demo_report)
    else:
        try:
            datasets = client.list_datasets()
        except DashboardApiError as e:
            handle_api_error(e)
            datasets = []

        if not datasets:
            st.info("No datasets available.")
        else:
            dataset_options = {d["id"]: f"{d['name']} (ID: #{d['id']})" for d in datasets}
            col_ads, col_arn = st.columns(2, gap="medium")

            with col_ads:
                selected_d_id = st.selectbox(
                    "Select Monitored Dataset",
                    options=list(dataset_options.keys()),
                    format_func=lambda x: dataset_options[x],
                    key="ai_dataset_select",
                )

            runs = client.list_runs_for_dataset(selected_d_id)
            completed_runs = [r for r in runs if r.get("status") == "completed"]

            if not completed_runs:
                st.warning("⚠️ No completed profiling runs found for this dataset. Only completed runs can be diagnosed.")
            else:
                run_opts = {
                    r["id"]: f"Run #{r['id']} (Score: {r.get('quality_score', 'N/A')}/100 | {r['created_at'][:19]})"
                    for r in completed_runs
                }
                with col_arn:
                    selected_run_id = st.selectbox(
                        "Select Completed Run to Diagnose",
                        options=list(run_opts.keys()),
                        format_func=lambda x: run_opts[x],
                        key="ai_run_select",
                    )

                col_live_ai, col_demo_ai = st.columns([1.2, 1], gap="medium")

                with col_live_ai:
                    trigger_live_ai = st.button("🤖 Generate Live AI Diagnostics", type="primary", use_container_width=True)

                with col_demo_ai:
                    trigger_demo_ai = st.button(
                        "📖 View Sample AI Diagnostic Report",
                        type="secondary",
                        use_container_width=True,
                        help="Explore grounded AI diagnosis without requiring an external LLM API key",
                    )

                if trigger_demo_ai:
                    ds_name = dataset_options.get(selected_d_id, "customer_orders")
                    st.session_state.ai_analysis_result = get_sample_ai_report(dataset_name=str(ds_name), run_id=selected_run_id)
                    st.success("✓ Loaded demonstration sample AI diagnostic report.")

                if trigger_live_ai:
                    with st.spinner("Synthesizing empirical profiling evidence and formulating grounded hypotheses..."):
                        try:
                            analysis = client.analyze_run(run_id=selected_run_id)
                            st.session_state.ai_analysis_result = analysis
                            st.success("✓ AI Root-Cause Diagnostics formulated successfully!")
                        except DashboardApiError as exc:
                            if exc.status_code == 503 and (
                                exc.error_code == "LLM_NOT_CONFIGURED"
                                or "LLM" in (exc.message or "").upper()
                                or "API_KEY" in (exc.message or "").upper()
                            ):
                                st.warning(
                                    "⚠️ **AI Root-Cause Diagnostics Unavailable**: The backend reports that no LLM API key "
                                    "is configured (`LLM_NOT_CONFIGURED`). Live LLM diagnostics require `LLM_API_KEY` to be set "
                                    "on the backend.\n\n"
                                    "👉 Click **📖 View Sample AI Diagnostic Report** above to inspect a full demonstration report "
                                    "illustrating DataPulse AI's grounded root-cause analysis without requiring an external LLM key."
                                )
                            elif exc.status_code == 401:
                                handle_api_error(exc)
                            else:
                                st.error(f"Diagnostics request failed: {exc.message}")

                if st.session_state.ai_analysis_result:
                    st.divider()
                    display_ai_analysis_report(st.session_state.ai_analysis_result)


# -----------------------------------------------------------------------------
# View 5: Data Remediation & Revalidation
# -----------------------------------------------------------------------------
elif active_view == "Data Remediation & Revalidation":
    render_header(
        title="Safe Data Remediation & Revalidation",
        subtitle="Safely configure deterministic data corrections, preview before-and-after diffs, and apply changes to a separate immutable copy without touching the original dataset.",
        icon="🛠️",
    )

    render_safety_guarantee_banner()

    # -------------------------------------------------------------------------
    # Guest Mode Remediation (In-Memory)
    # -------------------------------------------------------------------------
    if st.session_state.is_guest:
        if st.session_state.guest_data is None:
            st.session_state.guest_data = profile_guest_dataset(load_default_guest_dataset())

        guest_df = st.session_state.guest_data.get("df")
        available_cols = sorted(list(guest_df.columns))

        st.subheader("⚙️ Configure Deterministic Corrections (Sandbox Mode)")
        guest_ops: List[Dict[str, Any]] = []

        # 1. Missing Values Imputation
        with st.expander("1. Missing Value Imputation", expanded=True):
            enable_impute = st.checkbox("Impute missing values in a column", key="g_impute")
            if enable_impute:
                col1, col2, col3 = st.columns(3)
                with col1:
                    target_col = st.selectbox("Target Column", options=available_cols, key="g_impute_col")
                with col2:
                    strategy = st.selectbox("Strategy", options=["constant", "mean", "median", "mode"], key="g_impute_strategy")
                with col3:
                    fill_val = st.text_input("Fill Value", value="unverified@example.com" if strategy == "constant" else "", key="g_fill_val")

                guest_ops.append({
                    "operation_type": "fill_missing",
                    "column": target_col,
                    "strategy": strategy,
                    "fill_value": fill_val if strategy == "constant" else None,
                })

        # 2. Duplicate Rows Removal
        with st.expander("2. Duplicate Rows Removal", expanded=False):
            enable_dedup = st.checkbox("Remove duplicate rows (preserve first occurrence)", key="g_dedup")
            if enable_dedup:
                guest_ops.append({"operation_type": "drop_duplicates"})

        # 3. Whitespace Normalization
        with st.expander("3. Whitespace & Text Normalization", expanded=False):
            enable_trim = st.checkbox("Trim leading and trailing whitespace", key="g_trim")
            if enable_trim:
                empty_to_null = st.checkbox("Normalize empty strings to NULL", key="g_empty_null")
                guest_ops.append({
                    "operation_type": "trim_whitespace",
                    "columns": None,
                    "empty_string_to_null": empty_to_null,
                })

        # 4. Outlier Capping
        with st.expander("4. Numeric Outlier Capping", expanded=False):
            enable_cap = st.checkbox("Cap extreme numerical outliers to fixed bounds", key="g_cap")
            if enable_cap:
                num_cols = [c for c in available_cols if pd.api.types.is_numeric_dtype(guest_df[c])]
                if num_cols:
                    cc1, cc2, cc3 = st.columns(3)
                    with cc1:
                        cap_col = st.selectbox("Numeric Column", options=num_cols, key="g_cap_col")
                    with cc2:
                        lower_b = st.number_input("Lower Bound (Optional)", value=0.0, key="g_cap_low")
                    with cc3:
                        upper_b = st.number_input("Upper Bound (Optional)", value=2000.0, key="g_cap_up")
                    guest_ops.append({
                        "operation_type": "cap_outliers",
                        "column": cap_col,
                        "lower_bound": lower_b,
                        "upper_bound": upper_b,
                    })

        # Preview Button
        if st.button("🔍 Simulate & Preview Changes", type="primary"):
            if not guest_ops:
                st.warning("Please configure at least one remediation operation above.")
            else:
                with st.spinner("Simulating operations on in-memory DataFrame copy..."):
                    preview = simulate_guest_remediation(guest_df, guest_ops)
                    st.session_state.guest_preview = preview
                    st.session_state.guest_remediation_ops = guest_ops
                    st.session_state.guest_applied_result = None
                    st.success("✓ Remediation preview generated! Review proposed modifications below.")

        if st.session_state.get("guest_preview"):
            prev = st.session_state.guest_preview
            st.divider()
            st.subheader("📋 In-Memory Remediation Impact Preview")

            p1, p2, p3 = st.columns(3)
            p1.metric("Rows Before", prev.get("total_rows_before", 0))
            p2.metric("Projected Rows After", prev.get("total_rows_after", 0))
            p3.metric("Operations Configured", len(prev.get("operations", [])))

            # Sample Diffs
            sample_diffs = prev.get("sample_diffs", [])
            if sample_diffs:
                st.subheader("Sample Row Modifications (Before vs. After)")
                df_diffs = pd.DataFrame(sample_diffs)
                st.dataframe(df_diffs, use_container_width=True, hide_index=True)

            st.divider()
            st.subheader("🛡️ User Approval & Sandbox Application")
            approval = st.checkbox("✅ I approve applying these corrections in-memory to revalidate data quality.")

            if st.button("🚀 Confirm & Apply Remediation (Sandbox)", type="primary", disabled=not approval):
                with st.spinner("Applying operations and revalidating quality score..."):
                    apply_res = apply_guest_remediation(guest_df, st.session_state.guest_remediation_ops)
                    st.session_state.guest_applied_result = apply_res
                    st.session_state.guest_data["df"] = apply_res["remediated_df"]
                    st.session_state.guest_preview = None
                    st.success("✓ Remediation applied and revalidation completed successfully!")

        if st.session_state.get("guest_applied_result"):
            res = st.session_state.guest_applied_result
            st.divider()
            st.subheader("🎉 Revalidation & Quality Improvement Results")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Original Quality Score", f"{res.get('original_score')}/100")
            m2.metric("Remediated Score", f"{res.get('remediated_score')}/100", delta=f"{res.get('score_improvement'):+0.2f} pts")
            m3.metric("New Run ID", res.get("new_run_id"))
            m4.metric("Version Tag", res.get("new_version_tag"))

            st.info(
                "ℹ️ **Sandbox Mode**: Corrected dataset evaluated in memory. "
                "To automatically store immutable version artifacts in private Amazon S3 and track audit logs in Neon PostgreSQL, "
                "sign out and register for an account."
            )

    # -------------------------------------------------------------------------
    # Authenticated User Remediation (Cloud API)
    # -------------------------------------------------------------------------
    else:
        try:
            datasets = client.list_datasets()
        except DashboardApiError as e:
            handle_api_error(e)
            datasets = []

        if not datasets:
            st.info("No datasets available for remediation. Upload a dataset in Overview & Ingestion first.")
        else:
            d_options = {d["id"]: f"{d['name']} (ID: #{d['id']})" for d in datasets}
            col_rds, col_rrn = st.columns(2, gap="medium")

            with col_rds:
                selected_d_id = st.selectbox(
                    "Select Monitored Dataset",
                    options=list(d_options.keys()),
                    format_func=lambda x: d_options[x],
                    key="rem_dataset_select",
                )

            runs = client.list_runs_for_dataset(selected_d_id)
            completed_runs = [r for r in runs if r.get("status") == "completed"]

            if not completed_runs:
                st.warning("⚠️ No completed profiling runs available. Remediation requires an existing completed run.")
            else:
                run_options = {
                    r["id"]: f"Run #{r['id']} (Score: {r.get('quality_score', 'N/A')}/100 | {r['created_at'][:19]})"
                    for r in completed_runs
                }
                with col_rrn:
                    selected_run_id = st.selectbox(
                        "Select Completed Source Run to Remediate",
                        options=list(run_options.keys()),
                        format_func=lambda x: run_options[x],
                        key="rem_run_select",
                    )

                metrics = client.get_run_metrics(selected_run_id)
                available_cols = sorted(list(set([m["column_name"] for m in metrics if m.get("column_name")])))

                st.divider()
                st.subheader("⚙️ Configure Deterministic Corrections")
                configured_operations: List[Dict[str, Any]] = []

                # 1. Missing Values Imputation
                with st.expander("1. Missing Value Imputation", expanded=True):
                    enable_impute = st.checkbox("Impute missing values in a column", key="enable_impute")
                    if enable_impute and available_cols:
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            target_col = st.selectbox("Target Column", options=available_cols, key="impute_col")
                        with col2:
                            strategy = st.selectbox("Strategy", options=["constant", "mean", "median", "mode"], key="impute_strategy")
                        with col3:
                            fill_val = None
                            if strategy == "constant":
                                fill_val = st.text_input("Fill Value", placeholder="e.g., 0 or Unknown", key="impute_fill_val")

                        configured_operations.append({
                            "operation_type": "fill_missing",
                            "column": target_col,
                            "strategy": strategy,
                            "fill_value": fill_val if strategy == "constant" else None,
                        })

                # 2. Duplicate Rows Removal
                with st.expander("2. Duplicate Rows Removal", expanded=False):
                    enable_dedup = st.checkbox("Remove duplicate rows (preserve first occurrence)", key="enable_dedup")
                    if enable_dedup:
                        configured_operations.append({
                            "operation_type": "drop_duplicates",
                        })

                # 3. Whitespace & Text Normalization
                with st.expander("3. Whitespace & Text Normalization", expanded=False):
                    enable_trim = st.checkbox("Trim leading and trailing whitespace", key="enable_trim")
                    if enable_trim:
                        trim_cols = st.multiselect("Columns to trim (leave empty for all string columns)", options=available_cols, key="trim_cols")
                        empty_to_null = st.checkbox("Normalize empty strings to NULL", key="trim_empty_null")
                        configured_operations.append({
                            "operation_type": "trim_whitespace",
                            "columns": trim_cols if trim_cols else None,
                            "empty_string_to_null": empty_to_null,
                        })

                # 4. Data Type Corrections
                with st.expander("4. Data Type Conversion", expanded=False):
                    enable_type = st.checkbox("Convert column data type", key="enable_type")
                    if enable_type and available_cols:
                        tc1, tc2, tc3 = st.columns(3)
                        with tc1:
                            type_col = st.selectbox("Column", options=available_cols, key="type_col")
                        with tc2:
                            target_t = st.selectbox("Target Type", options=["integer", "float", "string", "date"], key="type_target")
                        with tc3:
                            policy = st.selectbox("Unconvertible Values Policy", options=["coerce", "reject"], key="type_policy", help="coerce sets invalid values to NULL; reject aborts the operation")
                        configured_operations.append({
                            "operation_type": "convert_type",
                            "column": type_col,
                            "target_type": target_t,
                            "failure_policy": policy,
                        })

                # 5. Outlier Capping
                with st.expander("5. Numeric Outlier Capping", expanded=False):
                    enable_cap = st.checkbox("Cap extreme numerical outliers to fixed bounds", key="enable_cap")
                    if enable_cap and available_cols:
                        cc1, cc2, cc3 = st.columns(3)
                        with cc1:
                            cap_col = st.selectbox("Numeric Column", options=available_cols, key="cap_col")
                        with cc2:
                            lower_b = st.number_input("Lower Bound (Optional)", value=0.0, key="cap_lower")
                        with cc3:
                            upper_b = st.number_input("Upper Bound (Optional)", value=1000000.0, key="cap_upper")
                        use_low = st.checkbox("Apply lower bound", value=True, key="use_low")
                        use_up = st.checkbox("Apply upper bound", value=True, key="use_up")

                        if use_low or use_up:
                            configured_operations.append({
                                "operation_type": "cap_outliers",
                                "column": cap_col,
                                "lower_bound": lower_b if use_low else None,
                                "upper_bound": upper_b if use_up else None,
                            })

                # Preview Button
                if st.button("🔍 Simulate & Preview Changes", type="primary"):
                    if not configured_operations:
                        st.warning("Please configure at least one remediation operation above.")
                    else:
                        with st.spinner("Simulating operations on dataset copy..."):
                            try:
                                preview = client.preview_remediation(
                                    run_id=selected_run_id,
                                    operations=configured_operations,
                                )
                                st.session_state.remediation_preview = preview
                                st.session_state.remediation_preview_ops = configured_operations
                                st.session_state.remediation_result = None
                                st.success("✓ Remediation preview generated successfully! Review proposed modifications below.")
                            except DashboardApiError as e:
                                handle_api_error(e)

                # Display Preview Results
                if st.session_state.remediation_preview:
                    preview = st.session_state.remediation_preview
                    st.divider()
                    st.subheader("📋 Remediation Impact Preview")

                    p1, p2, p3 = st.columns(3)
                    p1.metric("Rows Before", preview.get("total_rows_before", 0))
                    p2.metric("Projected Rows After", preview.get("total_rows_after", 0))
                    p3.metric("Operations Configured", len(preview.get("operations", [])))

                    warnings = preview.get("warnings", [])
                    if warnings:
                        for w in warnings:
                            st.warning(f"⚠️ {w}")

                    st.subheader("Proposed Operations Impact")
                    for op_p in preview.get("operations", []):
                        st.markdown(f"- **{op_p.get('operation_type')}** ({op_p.get('column') or 'table'}): {op_p.get('description')} *(Affected: {op_p.get('affected_rows', 0)} rows)*")

                    sample_diffs = preview.get("sample_diffs", [])
                    if sample_diffs:
                        st.subheader("Sample Row Modifications (Before vs. After)")
                        df_diffs = pd.DataFrame(sample_diffs)
                        st.dataframe(df_diffs, use_container_width=True, hide_index=True)

                    st.divider()
                    st.subheader("🛡️ User Approval & Safe Application")
                    st.write("Applying corrections will upload a **separate corrected CSV artifact** to Amazon S3, create a new `DatasetVersion`, and trigger automated re-profiling.")

                    custom_tag_input = st.text_input(
                        "Remediated Version Tag (Optional)",
                        placeholder=f"v{selected_run_id}_remediated",
                        key="rem_tag_input",
                    )

                    approval_checkbox = st.checkbox(
                        "✅ I have reviewed the simulated changes above and approve applying them to a new dataset version.",
                        key="rem_approve_checkbox",
                    )

                    if st.button("🚀 Confirm & Apply Remediation", type="primary", disabled=not approval_checkbox):
                        with st.spinner("Applying approved operations, uploading corrected CSV, and re-profiling..."):
                            try:
                                apply_res = client.apply_remediation(
                                    run_id=selected_run_id,
                                    preview_id=preview.get("preview_id"),
                                    operations=st.session_state.remediation_preview_ops,
                                    new_version_tag=custom_tag_input or None,
                                )
                                st.session_state.remediation_result = apply_res
                                st.session_state.remediation_preview = None
                                st.success("✓ Remediation applied and revalidation completed successfully!")
                            except DashboardApiError as exc:
                                handle_api_error(exc)

                if st.session_state.remediation_result:
                    res = st.session_state.remediation_result
                    st.divider()
                    st.subheader("🎉 Revalidation & Quality Improvement Results")

                    orig_s = res.get("original_score", 0.0)
                    new_s = res.get("remediated_score", 0.0)
                    diff_s = res.get("score_improvement", 0.0)

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Original Quality Score", f"{orig_s}/100")
                    m2.metric("Remediated Score", f"{new_s}/100", delta=f"{diff_s:+0.2f} pts")
                    m3.metric("New Run ID", f"#{res.get('new_run_id')}")
                    m4.metric("Version Tag", res.get("new_version_tag"))

                    st.caption(f"Artifact S3 Location: `{res.get('storage_uri')}`")

                # Remediation History Expander
                st.divider()
                with st.expander("📜 Dataset Remediation Audit History"):
                    try:
                        history = client.get_dataset_remediation_history(selected_d_id)
                        if history:
                            df_hist = pd.DataFrame(history)
                            st.dataframe(df_hist, use_container_width=True, hide_index=True)
                        else:
                            st.write("No historical remediations recorded for this dataset.")
                    except DashboardApiError as e:
                        st.caption(f"Could not load history: {e.message}")
