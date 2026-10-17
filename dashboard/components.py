"""Reusable visual components and Plotly charts for DataPulse AI Dashboard."""

from typing import Any, Dict, List, Optional
import plotly.graph_objects as go
import streamlit as st


def render_score_gauge(score: Optional[float]) -> go.Figure:
    """Create a sleek, high-visibility gauge chart for the 0-100 quality score."""
    val = round(score, 1) if score is not None else 0.0

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=val,
            number={
                "suffix": "/100",
                "font": {"size": 40, "color": "#f8fafc", "family": "Inter, sans-serif"},
            },
            title={
                "text": "Overall Data Quality Score",
                "font": {"size": 15, "color": "#94a3b8", "family": "Inter, sans-serif"},
            },
            gauge={
                "axis": {
                    "range": [0, 100],
                    "tickwidth": 1,
                    "tickcolor": "#64748b",
                    "tickfont": {"color": "#94a3b8", "size": 11},
                },
                "bar": {"color": "#38bdf8", "thickness": 0.26},
                "bgcolor": "rgba(30, 41, 59, 0.7)",
                "borderwidth": 1,
                "bordercolor": "rgba(255, 255, 255, 0.12)",
                "steps": [
                    {"range": [0, 50], "color": "rgba(239, 68, 68, 0.22)"},    # Red
                    {"range": [50, 70], "color": "rgba(245, 158, 11, 0.22)"},   # Amber
                    {"range": [70, 85], "color": "rgba(56, 189, 248, 0.20)"},   # Blue
                    {"range": [85, 100], "color": "rgba(16, 185, 129, 0.22)"},  # Emerald
                ],
                "threshold": {
                    "line": {"color": "#10b981", "width": 4},
                    "thickness": 0.75,
                    "value": 85,
                },
            },
        )
    )
    fig.update_layout(
        height=260,
        margin=dict(l=25, r=25, t=40, b=15),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif"),
    )
    return fig


def render_component_breakdown(component_scores: Dict[str, float]) -> Optional[go.Figure]:
    """Render horizontal bar chart for quality dimensions."""
    if not component_scores:
        return None

    dimensions = [k.capitalize() for k in component_scores.keys()]
    scores = [round(v, 1) for v in component_scores.values()]

    colors = []
    for s in scores:
        if s >= 85:
            colors.append("#10b981")  # Emerald
        elif s >= 70:
            colors.append("#38bdf8")  # Sky
        elif s >= 50:
            colors.append("#f59e0b")  # Amber
        else:
            colors.append("#ef4444")  # Red

    fig = go.Figure(
        go.Bar(
            x=scores,
            y=dimensions,
            orientation="h",
            marker=dict(
                color=colors,
                line=dict(color="rgba(255, 255, 255, 0.15)", width=1),
            ),
            text=[f"{s}%" for s in scores],
            textposition="auto",
            textfont=dict(color="#f8fafc", size=12, family="Inter, sans-serif"),
        )
    )
    fig.update_layout(
        title={
            "text": "Quality Dimensions Breakdown",
            "font": {"size": 15, "color": "#f8fafc", "family": "Inter, sans-serif"},
        },
        xaxis=dict(
            range=[0, 100],
            title=dict(text="Score (%)", font=dict(color="#94a3b8", size=12)),
            tickfont=dict(color="#94a3b8", size=11),
            gridcolor="rgba(255, 255, 255, 0.08)",
        ),
        yaxis=dict(
            autorange="reversed",
            tickfont=dict(color="#f8fafc", size=12),
        ),
        height=240,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def render_issue_severity_distribution(issues: List[Dict[str, Any]]) -> Optional[go.Figure]:
    """Render a donut chart displaying distribution of issue severities."""
    if not issues:
        return None

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for issue in issues:
        sev = str(issue.get("severity", "medium")).lower()
        if sev in counts:
            counts[sev] += 1
        else:
            counts[sev] = 1

    labels = [k.capitalize() for k, v in counts.items() if v > 0]
    values = [v for k, v in counts.items() if v > 0]

    color_map = {
        "Critical": "#ef4444",
        "High": "#f97316",
        "Medium": "#f59e0b",
        "Low": "#64748b",
    }
    colors = [color_map.get(lbl, "#94a3b8") for lbl in labels]

    if not values or sum(values) == 0:
        return None

    fig = go.Figure(
        data=[
            go.Pie(
                labels=labels,
                values=values,
                hole=0.52,
                marker=dict(colors=colors, line=dict(color="#1e293b", width=2)),
                textinfo="label+value",
                textfont=dict(color="#f8fafc", size=12, family="Inter, sans-serif"),
            )
        ]
    )
    fig.update_layout(
        title={
            "text": "Detected Issues by Severity",
            "font": {"size": 15, "color": "#f8fafc", "family": "Inter, sans-serif"},
        },
        height=260,
        margin=dict(l=20, r=20, t=40, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        legend=dict(font=dict(color="#94a3b8", size=11)),
    )
    return fig


def render_column_quality_bar(metrics: List[Dict[str, Any]]) -> Optional[go.Figure]:
    """Render column-level null rates and outlier counts."""
    col_missing: Dict[str, float] = {}
    col_outliers: Dict[str, float] = {}

    for m in metrics:
        col = m.get("column_name")
        if not col:
            continue
        m_name = m.get("metric_name")
        val = m.get("metric_value")
        if val is None:
            continue

        if m_name == "missing_percentage":
            col_missing[col] = float(val)
        elif m_name == "outlier_count":
            col_outliers[col] = float(val)

    if not col_missing and not col_outliers:
        return None

    cols = sorted(list(set(list(col_missing.keys()) + list(col_outliers.keys()))))
    missing_vals = [col_missing.get(c, 0.0) for c in cols]
    outlier_vals = [col_outliers.get(c, 0.0) for c in cols]

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Missing Rate (%)",
            x=cols,
            y=missing_vals,
            marker_color="#f59e0b",
        )
    )
    if any(v > 0 for v in outlier_vals):
        fig.add_trace(
            go.Bar(
                name="Outlier Count",
                x=cols,
                y=outlier_vals,
                marker_color="#ef4444",
            )
        )

    fig.update_layout(
        title={
            "text": "Column-Level Defects (Missing % & Outliers)",
            "font": {"size": 15, "color": "#f8fafc", "family": "Inter, sans-serif"},
        },
        barmode="group",
        height=320,
        margin=dict(l=20, r=20, t=45, b=40),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(
            tickangle=-30,
            tickfont=dict(color="#94a3b8", size=11),
            gridcolor="rgba(255, 255, 255, 0.06)",
        ),
        yaxis=dict(
            tickfont=dict(color="#94a3b8", size=11),
            gridcolor="rgba(255, 255, 255, 0.08)",
        ),
        legend=dict(font=dict(color="#94a3b8", size=11)),
    )
    return fig


def display_ai_analysis_report(analysis: Dict[str, Any]) -> None:
    """Format and display structured AI Root-Cause Analysis with TicketVault aesthetics."""
    if analysis.get("is_sample_demo"):
        st.markdown(
            """
            <div style="background: rgba(225, 29, 72, 0.08); border: 1px solid rgba(225, 29, 72, 0.3); border-radius: 12px; padding: 10px 16px; margin-bottom: 1rem; display: flex; align-items: center; gap: 10px;">
                <span class="tv-badge-crimson">DEMO REPORT</span>
                <span style="color: #cbd5e1; font-size: 0.88rem;">Curated diagnostic report illustrating grounded root-cause reasoning without requiring live LLM API credits.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    assessment = analysis.get("overall_assessment", "No assessment provided.")
    findings = analysis.get("key_findings", [])
    causes = analysis.get("likely_causes", [])
    recommendations = analysis.get("recommendations", [])
    limitations = analysis.get("limitations", [])

    st.markdown(
        f"""
        <div class="tv-card" style="border-left: 4px solid var(--dp-accent-crimson); margin-bottom: 1.25rem;">
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                <span class="tv-badge-crimson">AI EXECUTIVE SUMMARY</span>
            </div>
            <p style="color: #ffffff; font-size: 0.98rem; line-height: 1.55; margin: 0;">
                {assessment}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2, gap="medium")

    with col1:
        st.markdown("### 🔍 What the Data Shows")
        if findings:
            for f in findings:
                st.markdown(
                    f"""
                    <div style="background: #0d1422; border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 10px; padding: 11px 15px; margin-bottom: 8px; color: #ffffff; font-size: 0.92rem; line-height: 1.45;">
                        • {f}
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No specific findings highlighted.")

        st.markdown("### 💡 Why This Happened")
        if causes:
            for idx, c in enumerate(causes, 1):
                cause_text = c.get("cause", "")
                is_hyp = c.get("is_hypothesis", True)
                evidence = c.get("supporting_evidence", "")
                badge_html = '<span class="tv-badge-purple">LIKELY CAUSE</span>' if is_hyp else '<span class="tv-badge-emerald">CONFIRMED FACT</span>'

                with st.expander(f"#{idx} {cause_text[:50]}...", expanded=True):
                    st.markdown(f"{badge_html} <span style='color: #ffffff; font-weight: 600; margin-left: 6px;'>{cause_text}</span>", unsafe_allow_html=True)
                    if evidence:
                        st.markdown(f"<p style='color: #cbd5e1; font-size: 0.85rem; margin-top: 6px;'><strong>Evidence:</strong> {evidence}</p>", unsafe_allow_html=True)
        else:
            st.caption("No root causes identified.")

    with col2:
        st.markdown("### 🛠️ Suggested Actions")
        if recommendations:
            for r in recommendations:
                action = r.get("action", "")
                priority = str(r.get("priority", "medium")).upper()
                evidence = r.get("evidence", "")

                badge_cls = "tv-badge-crimson" if priority == "HIGH" else ("tv-badge-amber" if priority == "MEDIUM" else "tv-badge-cyan")

                st.markdown(
                    f"""
                    <div class="tv-card" style="padding: 1.1rem; margin-bottom: 10px;">
                        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px;">
                            <span class="{badge_cls}">{priority} PRIORITY</span>
                        </div>
                        <p style="color: #ffffff; font-size: 0.95rem; font-weight: 600; margin: 0 0 6px 0;">{action}</p>
                        <p style="color: #cbd5e1; font-size: 0.85rem; margin: 0;"><strong>Reason:</strong> {evidence}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No recommendations provided.")

        if limitations:
            st.markdown("### ℹ️ Additional Notes")
            for lim in limitations:
                st.caption(f"• *{lim}*")


