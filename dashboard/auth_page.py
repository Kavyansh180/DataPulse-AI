"""DataPulse AI — Authentication Landing Page & Guest Mode Onboarding.
TicketVault-inspired dark cinema aesthetics, clean typography, and zero-clutter layout.
"""

import re
from typing import Optional
import streamlit as st

from dashboard.api_client import DataPulseApiClient, DashboardApiError


def is_valid_email(email: str) -> bool:
    """Validate email format with standard regex."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def render_auth_landing_page(client: DataPulseApiClient) -> None:
    """Render the TicketVault-inspired Authentication Landing Page."""

    # -------------------------------------------------------------------------
    # 1. Connectivity Check for Header Status Pill
    # -------------------------------------------------------------------------
    backend_online = False
    try:
        health = client.check_health()
        backend_online = bool(health.get("status") == "healthy")
    except Exception:
        backend_online = False

    status_pill = (
        '<span class="tv-badge-emerald">● AWS BACKEND ONLINE</span>'
        if backend_online
        else '<span class="tv-badge-cyan">● GUEST SANDBOX READY</span>'
    )

    # -------------------------------------------------------------------------
    # 2. TicketVault-Inspired Featured Hero Spotlight Banner
    # -------------------------------------------------------------------------
    st.markdown(
        f"""
        <div class="tv-hero-banner">
            <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; flex-wrap: wrap; gap: 10px;">
                <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                    <span class="tv-badge-crimson">★ ENTERPRISE GRADE</span>
                    <span class="tv-badge-cyan">0–100 QUALITY SCORING</span>
                    <span class="tv-badge-emerald">SAFE REMEDIATION</span>
                </div>
                <div>{status_pill}</div>
            </div>
            <h1 style="font-size: 2.35rem; font-weight: 800; letter-spacing: -0.035em; margin: 0 0 10px 0; color: #ffffff;">
                Next-Gen Data Quality Intelligence
            </h1>
            <p style="color: #94a3b8; font-size: 1.05rem; margin: 0 0 18px 0; max-width: 820px; line-height: 1.5;">
                Automated statistical profiling, explainable quality scoring, and safe non-destructive CSV remediation 
                backed by Neon PostgreSQL and Amazon S3.
            </p>
            <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                <span class="tv-filter-chip">⚡ 1M+ Rows Handled</span>
                <span class="tv-filter-chip">🔍 IQR Outlier Bounds</span>
                <span class="tv-filter-chip">🛡️ Cell-Level Diffs</span>
                <span class="tv-filter-chip">🔒 Zero Disk Leakage</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # -------------------------------------------------------------------------
    # 3. Main Split Content: Highlights (Left) vs. Onboarding & Auth (Right)
    # -------------------------------------------------------------------------
    col_pitch, col_card = st.columns([1.25, 1.15], gap="large")

    with col_pitch:
        st.markdown(
            """
            <div style="margin-bottom: 1rem;">
                <h3 style="margin: 0; font-size: 1.25rem; font-weight: 700; color: #ffffff;">⚡ Core Capabilities</h3>
                <p style="color: #64748b; font-size: 0.88rem; margin: 4px 0 0 0;">Engineered for production data engineering and analytics teams</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Feature Card 1
        st.markdown(
            """
            <div class="tv-card">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span class="tv-badge-crimson">ALGORITHMIC</span>
                    <span style="color: #10b981; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;">100% EXPLAINABLE</span>
                </div>
                <h4 style="color: #ffffff; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Deterministic Quality Scoring (0–100)</h4>
                <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.45; margin: 0;">
                    Calculates explainable scores across completeness, uniqueness, validity, and consistency dimensions without black-box drift guesswork.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Feature Card 2
        st.markdown(
            """
            <div class="tv-card">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span class="tv-badge-cyan">STATISTICAL</span>
                    <span style="color: #38bdf8; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;">AUTOMATED</span>
                </div>
                <h4 style="color: #ffffff; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">IQR Anomaly & Defect Detection</h4>
                <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.45; margin: 0;">
                    Automated quartile bounds flag corrupt transaction spikes, numerical skew, and duplicate rows before they degrade downstream pipelines.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # Feature Card 3
        st.markdown(
            """
            <div class="tv-card">
                <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
                    <span class="tv-badge-emerald">GOVERNANCE</span>
                    <span style="color: #34d399; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.05em;">IMMUTABLE</span>
                </div>
                <h4 style="color: #ffffff; margin: 0 0 6px 0; font-size: 1.05rem; font-weight: 700;">Safe Non-Destructive Remediation</h4>
                <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.45; margin: 0;">
                    Preview proposed transformations (imputation, deduplication, whitespace trimming) with cell-level diffs before generating versioned S3 snapshots.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_card:
        # ---------------------------------------------------------------------
        # Quick Instant Guest Sandbox Card (TicketVault Highlight Card)
        # ---------------------------------------------------------------------
        st.markdown(
            """
            <div class="tv-card" style="border-color: rgba(225, 29, 72, 0.35); background: linear-gradient(135deg, rgba(225, 29, 72, 0.08) 0%, rgba(13, 19, 31, 0.95) 100%);">
                <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <span style="font-size: 1.25rem;">🚀</span>
                    <h3 style="color: #ffffff; margin: 0; font-size: 1.15rem; font-weight: 800;">Instant Sandbox Evaluation</h3>
                </div>
                <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.45; margin-bottom: 12px;">
                    Evaluate DataPulse AI immediately in an isolated, in-memory sandbox. Includes preloaded e-commerce transactions, automated profiling, and remediation previews.
                </p>
                <div style="display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 14px;">
                    <span class="tv-badge-crimson">ZERO REGISTRATION</span>
                    <span class="tv-badge-cyan">PRELOADED DATASET</span>
                    <span class="tv-badge-emerald">100% IN-MEMORY</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        if st.button("⚡ Launch Free Guest Sandbox Session", type="primary", use_container_width=True, key="btn_hero_guest"):
            st.session_state.is_guest = True
            st.session_state.auth_token = None
            st.session_state.user_profile = {
                "id": 0,
                "email": "guest@datapulse.demo",
                "full_name": "Guest Explorer",
            }
            client.set_token(None)
            st.success("Launching isolated Guest Sandbox...")
            st.rerun()

        st.markdown(
            "<div style='text-align: center; color: #64748b; font-size: 0.78rem; margin: 1.25rem 0 1rem 0; font-weight: 700; letter-spacing: 0.1em;'>"
            "─── OR SIGN IN TO YOUR WORKSPACE ───"
            "</div>",
            unsafe_allow_html=True,
        )

        # ---------------------------------------------------------------------
        # Auth Container Box
        # ---------------------------------------------------------------------
        with st.container():
            auth_tab_login, auth_tab_register = st.tabs(["🔑 Sign In", "✨ Create Account"])

            # -----------------------------------------------------------------
            # 1. Sign In Form
            # -----------------------------------------------------------------
            with auth_tab_login:
                with st.form("login_form", clear_on_submit=False):
                    login_email = st.text_input(
                        "Email Address",
                        placeholder="you@company.com",
                        key="login_email_input",
                    )
                    login_password = st.text_input(
                        "Password",
                        type="password",
                        placeholder="••••••••",
                        key="login_password_input",
                    )
                    submit_login = st.form_submit_button(
                        "Sign In to Workspace",
                        type="secondary",
                        use_container_width=True,
                    )

                if submit_login:
                    if not login_email or not login_password:
                        st.error("Please enter both your email address and password.")
                    elif not is_valid_email(login_email):
                        st.error("Please enter a valid email address.")
                    else:
                        with st.spinner("Authenticating credentials..."):
                            try:
                                res = client.login(email=login_email, password=login_password)
                                token = res.get("access_token")
                                user = res.get("user")
                                if token and user:
                                    st.session_state.auth_token = token
                                    st.session_state.user_profile = user
                                    st.session_state.is_guest = False
                                    client.set_token(token)
                                    st.success(f"Welcome back, {user.get('full_name') or user.get('email')}!")
                                    st.rerun()
                                else:
                                    st.error("Authentication succeeded but token was not returned.")
                            except DashboardApiError as exc:
                                if exc.status_code == 401:
                                    st.error("❌ Invalid email or password. Please check your credentials.")
                                elif exc.status_code == 403:
                                    st.error("⚠️ This account has been deactivated. Please contact support.")
                                else:
                                    st.error(f"Authentication failed: {exc.message}")

            # -----------------------------------------------------------------
            # 2. Registration Form
            # -----------------------------------------------------------------
            with auth_tab_register:
                with st.form("register_form", clear_on_submit=False):
                    reg_name = st.text_input(
                        "Full Name",
                        placeholder="Arthur Dent",
                        key="reg_name_input",
                    )
                    reg_email = st.text_input(
                        "Email Address",
                        placeholder="arthur@galaxy.org",
                        key="reg_email_input",
                    )
                    reg_password = st.text_input(
                        "Password (min 8 characters)",
                        type="password",
                        placeholder="At least 8 chars + 1 number",
                        key="reg_password_input",
                    )
                    submit_register = st.form_submit_button(
                        "Create Account & Sign In",
                        type="secondary",
                        use_container_width=True,
                    )

                if submit_register:
                    if not reg_email or not reg_password:
                        st.error("Please provide both an email address and a password.")
                    elif not is_valid_email(reg_email):
                        st.error("Please provide a valid email address.")
                    elif len(reg_password) < 8:
                        st.error("Password must be at least 8 characters long.")
                    elif not any(c.isdigit() for c in reg_password) and not any(not c.isalnum() for c in reg_password):
                        st.error("Password must contain at least one number or special character.")
                    else:
                        with st.spinner("Creating account and hashing credentials with Argon2id..."):
                            try:
                                res = client.register(
                                    email=reg_email,
                                    password=reg_password,
                                    full_name=reg_name.strip() if reg_name else None,
                                )
                                token = res.get("access_token")
                                user = res.get("user")
                                if token and user:
                                    st.session_state.auth_token = token
                                    st.session_state.user_profile = user
                                    st.session_state.is_guest = False
                                    client.set_token(token)
                                    st.success("Account created successfully! Welcome to DataPulse AI.")
                                    st.rerun()
                                else:
                                    st.error("Registration completed but token was not returned.")
                            except DashboardApiError as exc:
                                if exc.status_code == 409:
                                    st.error(f"❌ An account with email '{reg_email}' already exists. Please sign in.")
                                elif exc.status_code == 422:
                                    st.error(f"Validation Error: {exc.message}")
                                else:
                                    st.error(f"Registration failed: {exc.message}")
