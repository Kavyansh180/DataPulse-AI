"""DataPulse AI — Dashboard Theme, Design System & TicketVault-Inspired Aesthetics."""

from typing import Any, Optional
import streamlit as st


DARK_SAAS_CSS = """
<style>
/* =============================================================================
   DataPulse AI — TicketVault-Inspired Ultra-Dark Cinema SaaS Design System
   ============================================================================= */

/* Google Fonts Import (Inter & JetBrains Mono) */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

/* TicketVault Color Palette Tokens */
/* TicketVault Color Palette Tokens */
:root {
    --dp-bg-root: #06090e;
    --dp-bg-app: #080c14;
    --dp-bg-surface: #0d131f;
    --dp-bg-surface-elevated: #131c2e;
    --dp-bg-surface-hover: #19253d;
    --dp-border: rgba(255, 255, 255, 0.12);
    --dp-border-hover: rgba(225, 29, 72, 0.5);
    --dp-border-active: rgba(225, 29, 72, 0.7);
    --dp-text-primary: #ffffff;
    --dp-text-secondary: #f1f5f9;
    --dp-text-muted: #94a3b8;
    --dp-accent-crimson: #e11d48;
    --dp-accent-crimson-hover: #f43f5e;
    --dp-accent-gradient: linear-gradient(135deg, #e11d48 0%, #be123c 100%);
    --dp-accent-blue: #38bdf8;
    --dp-accent-cyan: #06b6d4;
    --dp-success: #10b981;
    --dp-warning: #f59e0b;
    --dp-danger: #ef4444;
}

/* Base application styling */
html, body, [data-testid="stAppViewContainer"], .main {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    background-color: var(--dp-bg-app) !important;
    background: var(--dp-bg-app) !important;
    color: var(--dp-text-primary) !important;
    letter-spacing: -0.01em;
}

/* Streamlit Header Bar */
header[data-testid="stHeader"] {
    background-color: rgba(6, 9, 14, 0.85) !important;
    background: rgba(6, 9, 14, 0.85) !important;
    backdrop-filter: blur(12px) !important;
    border-bottom: 1px solid var(--dp-border) !important;
    color: var(--dp-text-primary) !important;
}

header[data-testid="stHeader"] button,
header[data-testid="stHeader"] [data-testid="stToolbar"] {
    color: var(--dp-text-primary) !important;
}

/* Main block container padding */
.main .block-container {
    padding-top: 1.75rem !important;
    padding-bottom: 3.5rem !important;
    max-width: 1400px !important;
}

/* =============================================================================
   1. Left Sidebar Navigation (High-Contrast, Readable Menu)
   ============================================================================= */
section[data-testid="stSidebar"] {
    background-color: var(--dp-bg-root) !important;
    background: var(--dp-bg-root) !important;
    border-right: 1px solid var(--dp-border) !important;
    min-width: 295px !important;
    max-width: 320px !important;
    width: 300px !important;
    transform: none !important;
    visibility: visible !important;
}

@media (min-width: 768px) {
    section[data-testid="stSidebar"] {
        display: block !important;
        margin-left: 0 !important;
    }
    button[data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }
}

section[data-testid="stSidebar"] .block-container {
    padding-top: 1.5rem !important;
    padding-left: 1.2rem !important;
    padding-right: 1.2rem !important;
}

/* Radio Navigation in Sidebar (High-Contrast TicketVault Style) */
section[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 8px !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background: #0f1626 !important;
    padding: 12px 16px !important;
    border-radius: 12px !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    color: #ffffff !important;
    font-size: 14.5px !important;
    font-weight: 600 !important;
    cursor: pointer !important;
    transition: all 0.18s ease-in-out !important;
    display: flex !important;
    align-items: center !important;
    margin-bottom: 4px !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25) !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label span,
section[data-testid="stSidebar"] [data-testid="stRadio"] label div {
    color: #f8fafc !important;
    font-size: 14px !important;
    font-weight: 600 !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background: #17243c !important;
    border-color: rgba(225, 29, 72, 0.5) !important;
    color: #ffffff !important;
    transform: translateX(3px);
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background: linear-gradient(135deg, rgba(225, 29, 72, 0.25) 0%, rgba(13, 19, 31, 0.98) 100%) !important;
    color: #ffffff !important;
    border: 1.5px solid var(--dp-accent-crimson) !important;
    box-shadow: 0 4px 15px rgba(225, 29, 72, 0.3) !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"] p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"] span,
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) p,
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) span {
    color: #ffffff !important;
    font-weight: 700 !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    display: none !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[data-testid="stMarkdownContainer"] {
    margin-left: 0 !important;
}

/* =============================================================================
   2. Typography & High-Contrast Readability
   ============================================================================= */
h1, h2, h3, h4, h5, h6 {
    color: #ffffff !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
}

h1 { font-size: 1.95rem !important; }
h2 { font-size: 1.5rem !important; }
h3 { font-size: 1.2rem !important; }

p, div[data-testid="stMarkdownContainer"] p {
    color: #f1f5f9 !important;
    line-height: 1.55 !important;
}

label, [data-testid="stWidgetLabel"] label, [data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] span {
    color: #ffffff !important;
    font-weight: 600 !important;
    font-size: 0.95rem !important;
}

[data-testid="stCaptionContainer"] p, caption, small {
    color: #94a3b8 !important;
    font-size: 0.85rem !important;
}

/* =============================================================================
   3. TicketVault Metrics & KPI Cards
   ============================================================================= */
[data-testid="stMetric"] {
    background: linear-gradient(135deg, rgba(13, 19, 31, 0.9) 0%, rgba(19, 28, 46, 0.75) 100%) !important;
    border: 1px solid var(--dp-border) !important;
    border-radius: 14px !important;
    padding: 1.1rem 1.25rem !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.3) !important;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease-in-out;
}

[data-testid="stMetric"]:hover {
    border-color: rgba(225, 29, 72, 0.4) !important;
    transform: translateY(-2px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.4), 0 0 15px rgba(225, 29, 72, 0.15) !important;
}

[data-testid="stMetricLabel"] {
    color: #94a3b8 !important;
    font-size: 0.8rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

[data-testid="stMetricValue"] {
    color: #ffffff !important;
    font-size: 1.95rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.03em !important;
}

[data-testid="stMetricDelta"] {
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}

/* =============================================================================
   4. Form Inputs & Interactive Controls
   ============================================================================= */
.stTextInput input,
.stTextArea textarea,
div[data-baseweb="input"],
div[data-baseweb="base-input"],
div[data-baseweb="textarea"] {
    background-color: #0b111e !important;
    background: #0b111e !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    color: #ffffff !important;
    border-radius: 10px !important;
    -webkit-text-fill-color: #ffffff !important;
    transition: all 0.2s ease;
}

.stTextInput input:focus,
.stTextArea textarea:focus,
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within {
    border-color: var(--dp-accent-crimson) !important;
    box-shadow: 0 0 0 2px rgba(225, 29, 72, 0.3) !important;
}

div[data-baseweb="select"] > div {
    background-color: #0b111e !important;
    background: #0b111e !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    color: #ffffff !important;
    border-radius: 10px !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] div,
div[data-baseweb="select"] svg {
    color: #ffffff !important;
    fill: #ffffff !important;
    font-weight: 500 !important;
}

div[data-baseweb="popover"],
div[data-baseweb="menu"],
ul[role="listbox"] {
    background-color: var(--dp-bg-surface-elevated) !important;
    background: var(--dp-bg-surface-elevated) !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 10px !important;
    color: #ffffff !important;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.6) !important;
}

li[role="option"] {
    background-color: var(--dp-bg-surface-elevated) !important;
    color: #f1f5f9 !important;
    font-size: 0.92rem !important;
    font-weight: 500 !important;
    padding: 10px 14px !important;
}

li[role="option"]:hover,
li[aria-selected="true"] {
    background: linear-gradient(135deg, #e11d48 0%, #be123c 100%) !important;
    color: #ffffff !important;
    font-weight: 700 !important;
}

[data-testid="stCheckbox"] label p,
[data-testid="stCheckbox"] label span {
    color: #ffffff !important;
    font-size: 0.95rem !important;
    font-weight: 500 !important;
}

/* =============================================================================
   5. Buttons (TicketVault Crimson Glow & Sleek Glass)
   ============================================================================= */
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #e11d48 0%, #be123c 100%) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: -0.01em !important;
    padding: 0.6rem 1.35rem !important;
    box-shadow: 0 4px 16px rgba(225, 29, 72, 0.35) !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

div.stButton > button[kind="primary"]:hover,
div.stButton > button[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #f43f5e 0%, #e11d48 100%) !important;
    box-shadow: 0 6px 22px rgba(225, 29, 72, 0.5) !important;
    transform: translateY(-2px) !important;
}

div.stButton > button,
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"],
div.stDownloadButton > button,
div.stDownloadButton > button[kind="secondary"] {
    background-color: #121927 !important;
    background: #121927 !important;
    color: #f8fafc !important;
    border: 1px solid rgba(255, 255, 255, 0.1) !important;
    border-radius: 10px !important;
    font-weight: 500 !important;
    padding: 0.6rem 1.25rem !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3) !important;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
}

div.stButton > button:hover,
div.stButton > button[kind="secondary"]:hover,
div.stButton > button[data-testid="baseButton-secondary"]:hover,
div.stDownloadButton > button:hover,
div.stDownloadButton > button[kind="secondary"]:hover {
    background-color: #182338 !important;
    background: #182338 !important;
    color: #38bdf8 !important;
    border-color: rgba(56, 189, 248, 0.4) !important;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4), 0 0 10px rgba(56, 189, 248, 0.15) !important;
    transform: translateY(-2px) !important;
}

/* =============================================================================
   6. Expanders & Dropzones
   ============================================================================= */
[data-testid="stExpander"],
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    color: var(--dp-text-primary) !important;
    border-color: var(--dp-border) !important;
}

[data-testid="stExpander"] details {
    border: 1px solid var(--dp-border) !important;
    border-radius: 12px !important;
    overflow: hidden !important;
    margin-bottom: 0.75rem !important;
}

[data-testid="stExpander"] summary {
    padding: 0.75rem 1.15rem !important;
    cursor: pointer !important;
    transition: background-color 0.15s ease !important;
}

[data-testid="stExpander"] summary:hover {
    background-color: var(--dp-bg-surface-hover) !important;
    color: var(--dp-accent-crimson) !important;
}

/* File Uploader Dropzone */
section[data-testid="stFileUploaderDropzone"] {
    background-color: #0a0f19 !important;
    background: #0a0f19 !important;
    border: 1.5px dashed rgba(225, 29, 72, 0.3) !important;
    border-radius: 12px !important;
    transition: all 0.2s ease !important;
}

section[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--dp-accent-crimson) !important;
    background-color: rgba(225, 29, 72, 0.04) !important;
}

/* =============================================================================
   7. Tabs & DataFrames
   ============================================================================= */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 8px !important;
    border-bottom: 1px solid var(--dp-border) !important;
}

[data-testid="stTabs"] [data-baseweb="tab"] {
    padding: 10px 18px !important;
    color: var(--dp-text-secondary) !important;
    font-weight: 500 !important;
    border-radius: 8px 8px 0 0 !important;
    background-color: transparent !important;
    transition: all 0.15s ease;
}

[data-testid="stTabs"] [aria-selected="true"] {
    color: #ffffff !important;
    font-weight: 600 !important;
    border-bottom: 2px solid var(--dp-accent-crimson) !important;
    background-color: rgba(225, 29, 72, 0.08) !important;
}

[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid var(--dp-border) !important;
    border-radius: 12px !important;
    background-color: var(--dp-bg-surface) !important;
    overflow: hidden;
}

/* =============================================================================
   8. TicketVault Card & Pill Utility Classes
   ============================================================================= */
.tv-hero-banner {
    background: radial-gradient(circle at 80% 20%, rgba(225, 29, 72, 0.12) 0%, rgba(13, 19, 31, 0.85) 60%), #090e18;
    border: 1px solid rgba(225, 29, 72, 0.25);
    border-radius: 18px;
    padding: 2rem 2.25rem;
    margin-bottom: 1.75rem;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.4), 0 0 20px rgba(225, 29, 72, 0.1);
    position: relative;
    overflow: hidden;
}

.tv-card {
    background: linear-gradient(135deg, rgba(13, 19, 31, 0.95) 0%, rgba(16, 24, 38, 0.85) 100%);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
    padding: 1.35rem;
    margin-bottom: 1rem;
    transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25);
}

.tv-card:hover {
    border-color: rgba(225, 29, 72, 0.35);
    transform: translateY(-2px);
    box-shadow: 0 10px 25px rgba(0, 0, 0, 0.4), 0 0 15px rgba(225, 29, 72, 0.12);
}

.tv-badge-crimson {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(225, 29, 72, 0.15);
    color: #f43f5e;
    border: 1px solid rgba(225, 29, 72, 0.35);
    border-radius: 9999px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.tv-badge-cyan {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(56, 189, 248, 0.14);
    color: #38bdf8;
    border: 1px solid rgba(56, 189, 248, 0.35);
    border-radius: 9999px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.tv-badge-emerald {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(16, 185, 129, 0.14);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 9999px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.tv-badge-amber {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(245, 158, 11, 0.14);
    color: #fbbf24;
    border: 1px solid rgba(245, 158, 11, 0.35);
    border-radius: 9999px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.tv-badge-purple {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(139, 92, 246, 0.14);
    color: #a78bfa;
    border: 1px solid rgba(139, 92, 246, 0.35);
    border-radius: 9999px;
    padding: 4px 11px;
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

.tv-filter-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: #0f1624;
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 9999px;
    padding: 6px 14px;
    font-size: 0.82rem;
    font-weight: 500;
    color: #cbd5e1;
    margin-right: 8px;
    margin-bottom: 8px;
}

/* Custom Scrollbars */
hr { border-color: var(--dp-border) !important; }
::-webkit-scrollbar { width: 7px; height: 7px; }
::-webkit-scrollbar-track { background: var(--dp-bg-root); }
::-webkit-scrollbar-thumb { background: var(--dp-bg-surface-elevated); border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #334155; }
</style>
"""


def apply_custom_theme() -> None:
    """Inject modern TicketVault-inspired stylesheet into Streamlit page."""
    st.markdown(DARK_SAAS_CSS, unsafe_allow_html=True)


def render_brand_sidebar(app_name: str = "DataPulse AI", subtitle: str = "DATA QUALITY INTELLIGENCE") -> None:
    """Render clean brand header at the top of the sidebar."""
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 4px;">
            <div style="background: linear-gradient(135deg, #e11d48 0%, #be123c 100%); width: 28px; height: 28px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 16px; box-shadow: 0 2px 10px rgba(225, 29, 72, 0.4);">⚡</div>
            <h2 style="margin: 0; font-size: 1.3rem; font-weight: 800; color: #ffffff;">{app_name}</h2>
        </div>
        <p style="color: #94a3b8; font-size: 0.72rem; font-weight: 700; letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 12px;">{subtitle}</p>
        """,
        unsafe_allow_html=True,
    )


def render_header(
    title: str,
    subtitle: str,
    icon: str = "",
    badge_text: Optional[str] = None,
    backend_status: Optional[str] = None,
    backend_online: bool = True,
    **kwargs: Any,
) -> None:
    """Render consistent, professional TicketVault-style page header.

    Supports TicketVault badge pills (`badge_text`), legacy backend status indicators,
    and arbitrary keyword arguments to ensure robust compatibility across deployments.
    """
    badge_html = f'<span class="tv-badge-crimson" style="margin-left: 10px;">{badge_text}</span>' if badge_text else ""
    st.markdown(
        f"""
        <div style="margin-bottom: 1.25rem;">
            <div style="display: flex; align-items: center;">
                <h1 style="margin: 0; font-size: 1.85rem; font-weight: 800; letter-spacing: -0.025em; color: #ffffff;">{icon} {title}</h1>
                {badge_html}
            </div>
            <p style="color: #f1f5f9; font-size: 0.95rem; margin-top: 5px; margin-bottom: 0; line-height: 1.5;">{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.divider()


def render_safety_guarantee_banner() -> None:
    """Render clear, reassuring safety guarantee banner in the Data Remediation view."""
    st.markdown(
        """
        <div style="background: rgba(16, 185, 129, 0.12); border: 1.5px solid rgba(16, 185, 129, 0.4); border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; display: flex; align-items: flex-start; gap: 12px;">
            <div style="font-size: 1.4rem; line-height: 1;">🛡️</div>
            <div>
                <h4 style="color: #34d399; margin: 0 0 4px 0; font-size: 1rem; font-weight: 700;">100% Safe: Your Original File is Never Touched</h4>
                <p style="color: #f1f5f9; font-size: 0.9rem; margin: 0; line-height: 1.5;">
                    DataPulse creates a separate clean copy of your data. You can preview every single changed row before confirming, and your original uploaded file will always remain untouched.
                </p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
