"""DataPulse AI — Authentication Landing Page & Guest Mode Onboarding."""

import re
from typing import Optional
import streamlit as st

from dashboard.api_client import DataPulseApiClient, DashboardApiError


def is_valid_email(email: str) -> bool:
    """Validate email format with standard regex."""
    pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
    return bool(re.match(pattern, email.strip()))


def render_auth_landing_page(client: DataPulseApiClient) -> None:
    """Render the dark-themed Authentication Landing Page with Sign-In, Registration, and Guest Mode."""

    # Top Hero Branding
    col_logo, col_badge = st.columns([3, 1])
    with col_logo:
        st.title("⚡ DataPulse AI")
        st.subheader("Enterprise Data Quality Monitoring & Safe Remediation")
    with col_badge:
        try:
            health = client.check_health()
            st.success(f"● {health.get('app', 'DataPulse AI')} Online")
        except Exception:
            st.warning("● Offline Mode Available")

    st.markdown(
        "<p style='color: #94a3b8; font-size: 1.1rem; margin-top: -0.5rem;'>"
        "Automated statistical profiling, explainable quality scoring, and safe non-destructive data remediation "
        "backed by Neon PostgreSQL and Amazon S3."
        "</p>",
        unsafe_allow_html=True,
    )

    st.divider()

    # Main Split Hero: Value Proposition (Left) vs. Auth & Guest Actions (Right)
    col_pitch, col_card = st.columns([1.2, 1.1], gap="large")

    with col_pitch:
        st.markdown("### 🎯 Platform Capabilities")

        st.markdown(
            """
            <div style="background-color: #131d2e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;">
                <h4 style="color: #38bdf8; margin-top: 0;">🛡️ Deterministic Quality Scoring (0–100)</h4>
                <p style="color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0;">
                    Calculates explainable quality metrics across completeness, uniqueness, validity, and consistency dimensions without black-box drift guesswork.
                </p>
            </div>

            <div style="background-color: #131d2e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;">
                <h4 style="color: #38bdf8; margin-top: 0;">📈 Statistical Anomaly & Outlier Detection</h4>
                <p style="color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0;">
                    Automated IQR quartile bounds identify numerical skew and corrupt transaction spikes before they degrade downstream machine learning or BI models.
                </p>
            </div>

            <div style="background-color: #131d2e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.25rem; margin-bottom: 1rem;">
                <h4 style="color: #38bdf8; margin-top: 0;">🛠️ Safe Non-Destructive Remediation</h4>
                <p style="color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0;">
                    Preview proposed transformations (imputation, deduplication, whitespace trimming, type coercion) on a separate copy with cell-level diffs before applying.
                </p>
            </div>

            <div style="background-color: #131d2e; border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px; padding: 1.25rem;">
                <h4 style="color: #38bdf8; margin-top: 0;">🔒 Secure JWT Multi-Tenant Ownership</h4>
                <p style="color: #cbd5e1; font-size: 0.92rem; margin-bottom: 0;">
                    Argon2id password hashing and short-lived JWT authorization guarantee strict dataset ownership and tenant isolation.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with col_card:
        # Auth Container Box
        with st.container():
            auth_tab_login, auth_tab_register = st.tabs(["🔑 Sign In", "✨ Create Account"])

            # -----------------------------------------------------------------
            # 1. Sign In Form
            # -----------------------------------------------------------------
            with auth_tab_login:
                st.markdown("#### Welcome Back")
                st.caption("Sign in to access your registered datasets and profiling history.")

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
                        "Sign In",
                        type="primary",
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
                st.markdown("#### Create Your Account")
                st.caption("Register for a dedicated multi-tenant dataset workspace.")

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
                        type="primary",
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

        # ---------------------------------------------------------------------
        # 3. Path B: Continue as Guest (Recruiter Demo Sandbox)
        # ---------------------------------------------------------------------
        st.markdown(
            "<div style='text-align: center; color: #64748b; font-size: 0.85rem; margin: 1.25rem 0; font-weight: 600; letter-spacing: 0.08em;'>"
            "─── OR EXPLORE WITHOUT AN ACCOUNT ───"
            "</div>",
            unsafe_allow_html=True,
        )

        with st.container():
            st.markdown(
                """
                <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.9) 100%);
                            border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 12px; padding: 1.25rem; margin-bottom: 0.75rem;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px;">
                        <span style="font-size: 1.2rem;">🚀</span>
                        <h4 style="color: #f8fafc; margin: 0; font-size: 1.05rem;">Continue as Guest</h4>
                    </div>
                    <p style="color: #94a3b8; font-size: 0.88rem; line-height: 1.4; margin-bottom: 0.75rem;">
                        Evaluate DataPulse AI immediately. Explore automated statistical profiling, quality score breakdowns,
                        outlier detection, and safe remediation previews in an isolated, in-memory sandbox.
                    </p>
                    <ul style="color: #64748b; font-size: 0.82rem; margin-bottom: 0; padding-left: 1.2rem;">
                        <li>Zero registration or credentials required</li>
                        <li>Built-in synthetic e-commerce dataset included</li>
                        <li>Zero cloud persistence — your data stays strictly in memory</li>
                    </ul>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("⚡ Launch Guest Sandbox Session", type="secondary", use_container_width=True):
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
