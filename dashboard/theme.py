"""DataPulse AI — Dashboard Theme, Design System & Reusable Visual Components."""

from typing import Optional
import streamlit as st


DARK_SAAS_CSS = """
<style>
/* =============================================================================
   DataPulse AI — Modern Analytics SaaS Dark Design System
   ============================================================================= */

/* Google Fonts Import (Inter) */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

/* Root color variables */
:root {
    --dp-bg-root: #0b0f19;
    --dp-bg-app: #0f172a;
    --dp-bg-surface: #131d2e;
    --dp-bg-surface-elevated: #1e293b;
    --dp-bg-surface-hover: #273549;
    --dp-border: rgba(255, 255, 255, 0.09);
    --dp-border-active: rgba(56, 189, 248, 0.45);
    --dp-text-primary: #f8fafc;
    --dp-text-secondary: #94a3b8;
    --dp-text-muted: #64748b;
    --dp-accent-blue: #38bdf8;
    --dp-accent-primary: #2563eb;
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
}

/* Remove default white Streamlit top header */
header[data-testid="stHeader"] {
    background-color: var(--dp-bg-root) !important;
    background: var(--dp-bg-root) !important;
    border-bottom: 1px solid var(--dp-border) !important;
    color: var(--dp-text-primary) !important;
}

header[data-testid="stHeader"] button,
header[data-testid="stHeader"] [data-testid="stToolbar"] {
    color: var(--dp-text-secondary) !important;
}

/* Main block container padding */
.main .block-container {
    padding-top: 2rem !important;
    padding-bottom: 3.5rem !important;
    max-width: 1360px !important;
}

/* =============================================================================
   1. Persistent Left Sidebar
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

/* Radio Navigation in Sidebar */
section[data-testid="stSidebar"] [data-testid="stRadio"] > div {
    gap: 6px !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label {
    background-color: transparent !important;
    padding: 10px 14px !important;
    border-radius: 8px !important;
    border: 1px solid transparent !important;
    color: var(--dp-text-secondary) !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    cursor: pointer !important;
    transition: all 0.15s ease-in-out !important;
    display: flex !important;
    align-items: center !important;
    margin-bottom: 4px !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label:hover {
    background-color: rgba(255, 255, 255, 0.04) !important;
    color: var(--dp-text-primary) !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"],
section[data-testid="stSidebar"] [data-testid="stRadio"] label:has(input:checked) {
    background-color: rgba(37, 99, 235, 0.16) !important;
    color: #60a5fa !important;
    border-left: 3px solid #38bdf8 !important;
    border-color: rgba(56, 189, 248, 0.35) !important;
    font-weight: 600 !important;
}

section[data-testid="stSidebar"] [data-testid="stRadio"] input[type="radio"] {
    display: none !important;
}
section[data-testid="stSidebar"] [data-testid="stRadio"] div[data-testid="stMarkdownContainer"] {
    margin-left: 0 !important;
}

/* =============================================================================
   2. Typography & Headings
   ============================================================================= */
h1, h2, h3, h4, h5, h6 {
    color: var(--dp-text-primary) !important;
    font-weight: 600 !important;
    letter-spacing: -0.02em !important;
}

h1 { font-size: 1.85rem !important; }
h2 { font-size: 1.45rem !important; }
h3 { font-size: 1.15rem !important; }

p, span, label {
    color: var(--dp-text-secondary);
}

/* =============================================================================
   3. Metrics & KPI Cards
   ============================================================================= */
[data-testid="stMetric"] {
    background-color: var(--dp-bg-surface) !important;
    border: 1px solid var(--dp-border) !important;
    border-radius: 10px !important;
    padding: 1rem 1.15rem !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.15) !important;
}

[data-testid="stMetricLabel"] {
    color: var(--dp-text-secondary) !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.04em !important;
}

[data-testid="stMetricValue"] {
    color: var(--dp-text-primary) !important;
    font-size: 1.65rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.02em !important;
}

[data-testid="stMetricDelta"] {
    font-size: 0.82rem !important;
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
    background-color: #0b1120 !important;
    background: #0b1120 !important;
    border: 1px solid var(--dp-border) !important;
    color: var(--dp-text-primary) !important;
    border-radius: 8px !important;
    -webkit-text-fill-color: var(--dp-text-primary) !important;
}

.stTextInput input:focus,
.stTextArea textarea:focus,
div[data-baseweb="input"]:focus-within,
div[data-baseweb="textarea"]:focus-within {
    border-color: var(--dp-accent-blue) !important;
    box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2) !important;
}

/* Selectbox & Popover dropdown menus */
div[data-baseweb="select"] > div {
    background-color: #0b1120 !important;
    background: #0b1120 !important;
    border: 1px solid var(--dp-border) !important;
    color: var(--dp-text-primary) !important;
    border-radius: 8px !important;
}

div[data-baseweb="select"] span,
div[data-baseweb="select"] svg {
    color: var(--dp-text-primary) !important;
    fill: var(--dp-text-primary) !important;
}

div[data-baseweb="popover"],
div[data-baseweb="menu"],
ul[role="listbox"] {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    border: 1px solid var(--dp-border) !important;
    border-radius: 8px !important;
    color: var(--dp-text-primary) !important;
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4) !important;
}

li[role="option"] {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    color: var(--dp-text-primary) !important;
}

li[role="option"]:hover,
li[aria-selected="true"] {
    background-color: var(--dp-accent-primary) !important;
    background: var(--dp-accent-primary) !important;
    color: #ffffff !important;
}

/* Checkboxes */
[data-testid="stCheckbox"] label span:first-child {
    background-color: #0b1120 !important;
    border-color: rgba(255, 255, 255, 0.2) !important;
}

[data-testid="stCheckbox"] label span {
    color: var(--dp-text-primary) !important;
}

/* Primary Buttons */
div.stButton > button[kind="primary"],
div.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.15) !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.25rem !important;
    box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3) !important;
    transition: all 0.15s ease-in-out !important;
}

div.stButton > button[kind="primary"]:hover,
div.stButton > button[data-testid="baseButton-primary"]:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    box-shadow: 0 6px 16px rgba(37, 99, 235, 0.45) !important;
    transform: translateY(-1px) !important;
}

/* Secondary & General Buttons (Eliminating Stark White Rectangles) */
div.stButton > button,
div.stButton > button[kind="secondary"],
div.stButton > button[data-testid="baseButton-secondary"],
div.stDownloadButton > button,
div.stDownloadButton > button[kind="secondary"] {
    background-color: var(--dp-bg-surface-elevated) !important;
    background: var(--dp-bg-surface-elevated) !important;
    color: var(--dp-text-primary) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    padding: 0.55rem 1.25rem !important;
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.2) !important;
    transition: all 0.15s ease-in-out !important;
}

div.stButton > button:hover,
div.stButton > button[kind="secondary"]:hover,
div.stButton > button[data-testid="baseButton-secondary"]:hover,
div.stDownloadButton > button:hover,
div.stDownloadButton > button[kind="secondary"]:hover {
    background-color: var(--dp-bg-surface-hover) !important;
    background: var(--dp-bg-surface-hover) !important;
    color: var(--dp-accent-blue) !important;
    border-color: var(--dp-border-active) !important;
    box-shadow: 0 4px 10px rgba(0, 0, 0, 0.3) !important;
    transform: translateY(-1px) !important;
}

/* =============================================================================
   5. Expanders & Accordions (Fixing White Background Glitch)
   ============================================================================= */
[data-testid="stExpander"],
[data-testid="stExpander"] details,
[data-testid="stExpander"] summary,
[data-testid="stExpander"] div[data-testid="stExpanderDetails"],
[data-testid="stExpander"] .streamlit-expanderHeader {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    color: var(--dp-text-primary) !important;
    border-color: var(--dp-border) !important;
}

[data-testid="stExpander"] details {
    border: 1px solid var(--dp-border) !important;
    border-radius: 8px !important;
    overflow: hidden !important;
    margin-bottom: 0.75rem !important;
}

[data-testid="stExpander"] summary {
    padding: 0.65rem 1rem !important;
    cursor: pointer !important;
    transition: background-color 0.15s ease !important;
}

[data-testid="stExpander"] summary:hover {
    background-color: var(--dp-bg-surface-hover) !important;
    background: var(--dp-bg-surface-hover) !important;
    color: var(--dp-accent-blue) !important;
}

[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary span,
[data-testid="stExpander"] summary svg {
    color: var(--dp-text-primary) !important;
    fill: var(--dp-text-primary) !important;
    font-weight: 500 !important;
}

[data-testid="stExpander"] div[data-testid="stExpanderDetails"] {
    padding: 1rem !important;
    border-top: 1px solid var(--dp-border) !important;
}

/* =============================================================================
   6. File Uploader Dropzone (Fixing White Box)
   ============================================================================= */
[data-testid="stFileUploader"] {
    background-color: transparent !important;
    padding: 0 !important;
}

section[data-testid="stFileUploaderDropzone"],
section[data-testid="stFileUploaderDropzone"] > div {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    border: 1.5px dashed rgba(56, 189, 248, 0.3) !important;
    border-radius: 10px !important;
    color: var(--dp-text-primary) !important;
    transition: all 0.2s ease !important;
}

section[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--dp-accent-blue) !important;
    background-color: #172338 !important;
    background: #172338 !important;
}

section[data-testid="stFileUploaderDropzone"] button {
    background-color: var(--dp-bg-surface-elevated) !important;
    background: var(--dp-bg-surface-elevated) !important;
    color: var(--dp-text-primary) !important;
    border: 1px solid var(--dp-border) !important;
    border-radius: 6px !important;
}

section[data-testid="stFileUploaderDropzone"] button:hover {
    background-color: var(--dp-accent-primary) !important;
    background: var(--dp-accent-primary) !important;
    color: #ffffff !important;
    border-color: var(--dp-accent-primary) !important;
}

section[data-testid="stFileUploaderDropzone"] span,
section[data-testid="stFileUploaderDropzone"] small,
section[data-testid="stFileUploaderDropzone"] svg {
    color: var(--dp-text-secondary) !important;
    fill: var(--dp-text-secondary) !important;
}

section[data-testid="stFileUploaderDropzone"] [data-testid="stMarkdownContainer"] p {
    color: var(--dp-text-primary) !important;
}

/* =============================================================================
   7. Tabs & DataFrames
   ============================================================================= */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 8px !important;
    border-bottom: 1px solid var(--dp-border) !important;
}

[data-testid="stTabs"] [data-baseweb="tab"] {
    padding: 8px 16px !important;
    color: var(--dp-text-secondary) !important;
    font-weight: 500 !important;
    border-radius: 6px 6px 0 0 !important;
    background-color: transparent !important;
}

[data-testid="stTabs"] [aria-selected="true"] {
    color: var(--dp-accent-blue) !important;
    font-weight: 600 !important;
    border-bottom: 2px solid var(--dp-accent-blue) !important;
    background-color: rgba(56, 189, 248, 0.06) !important;
}

[data-testid="stDataFrame"],
[data-testid="stTable"] {
    border: 1px solid var(--dp-border) !important;
    border-radius: 8px !important;
    background-color: var(--dp-bg-surface) !important;
}

/* =============================================================================
   8. Alerts & Banners (Sleek Dark Accent Styling)
   ============================================================================= */
[data-testid="stAlert"] {
    background-color: var(--dp-bg-surface) !important;
    background: var(--dp-bg-surface) !important;
    border: 1px solid var(--dp-border) !important;
    border-radius: 10px !important;
    color: var(--dp-text-primary) !important;
}

[data-testid="stAlert"] * {
    color: var(--dp-text-primary) !important;
}

div[data-testid="stAlert"]:has([data-testid="stAlertContentInfo"]) {
    border-left: 4px solid var(--dp-accent-blue) !important;
}

div[data-testid="stAlert"]:has([data-testid="stAlertContentSuccess"]) {
    border-left: 4px solid var(--dp-success) !important;
}

div[data-testid="stAlert"]:has([data-testid="stAlertContentWarning"]) {
    border-left: 4px solid var(--dp-warning) !important;
}

div[data-testid="stAlert"]:has([data-testid="stAlertContentError"]) {
    border-left: 4px solid var(--dp-danger) !important;
}

/* Dividers & Scrollbars */
hr {
    border-color: var(--dp-border) !important;
}

::-webkit-scrollbar {
    width: 7px;
    height: 7px;
}
::-webkit-scrollbar-track {
    background: var(--dp-bg-root);
}
::-webkit-scrollbar-thumb {
    background: var(--dp-bg-surface-elevated);
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #334155;
}
</style>
"""


def apply_custom_theme() -> None:
    """Inject modern analytics SaaS stylesheet into Streamlit page."""
    st.markdown(DARK_SAAS_CSS, unsafe_allow_html=True)


def render_brand_sidebar(app_name: str = "DataPulse AI", subtitle: str = "DATA QUALITY INTELLIGENCE") -> None:
    """Render clean brand header at the top of the sidebar."""
    st.title(f"⚡ {app_name}")
    st.caption(subtitle)


def render_header(
    title: str,
    subtitle: str,
    icon: str = "",
    backend_status: Optional[str] = None,
    backend_online: bool = True,
) -> None:
    """Render consistent, professional page header."""
    header_text = f"{icon} {title}".strip() if icon else title
    st.header(header_text)
    st.caption(subtitle)
    st.divider()


def render_safety_guarantee_banner() -> None:
    """Render visual safety guarantee banner in the Data Remediation view."""
    st.info(
        "🛡️ **Source Dataset Immutability Guarantee**: "
        "Proposed corrections are previewed strictly on a non-destructive copy. "
        "Approved corrections will be stored as an independent, new CSV artifact in S3. "
        "Your original CSV and historical profiling runs will **never be overwritten**."
    )
