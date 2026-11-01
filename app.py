"""Streamlit dashboard for the generated experiment analytics outputs."""

from pathlib import Path

import pandas as pd
import streamlit as st

from dashboard_data import build_result_detail, load_dashboard_data


st.set_page_config(
    page_title="YottaFlex.ai | Experiment Analytics",
    page_icon="EA",
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
    :root {
        --canvas: #0b1118;
        --surface: #121b26;
        --surface-raised: #172331;
        --border: #263545;
        --text: #e8eef5;
        --muted: #91a1b2;
        --cyan: #55d6c2;
        --blue: #82aaff;
        --purple: #a78bfa;
        --green: #67d6a5;
        --amber: #f3bd62;
        --red: #ff7b82;
    }
    .stApp {
        background: linear-gradient(145deg, #0b1118 0%, #101a26 48%, #111225 100%);
        color: var(--text);
    }
    [data-testid="stHeader"] { background: rgba(11, 17, 24, 0.88); }
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #101a26 0%, #0d141d 100%);
        border-right: 1px solid var(--border);
    }
    [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3 {
        color: var(--text); font-size: 1.1rem; margin-bottom: 0.1rem;
    }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: var(--muted); }
    [data-testid="stSidebar"] [role="radiogroup"] label {
        border: 1px solid transparent; border-radius: 7px; padding: 0.35rem 0.55rem;
        transition: background-color 140ms ease, border-color 140ms ease;
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:hover {
        background: rgba(85, 214, 194, 0.08); border-color: rgba(85, 214, 194, 0.22);
    }
    [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
        background: rgba(85, 214, 194, 0.13); border-color: rgba(85, 214, 194, 0.4);
    }
    .block-container { max-width: 1500px; padding-top: 1.25rem; padding-bottom: 3rem; }
    .app-topbar {
        display: flex; justify-content: space-between; align-items: center; gap: 1rem;
        border-bottom: 1px solid var(--border); padding: 0.3rem 0 1rem; margin-bottom: 1.6rem;
    }
    .brand-lockup { display: flex; align-items: center; gap: 0.7rem; }
    .brand-mark {
        display: grid; place-items: center; width: 35px; height: 35px; border-radius: 8px;
        background: linear-gradient(135deg, #55d6c2, #82aaff); color: #08141c;
        font-size: 1rem; font-weight: 800;
    }
    .brand-name { color: var(--text); font-size: 0.96rem; font-weight: 750; }
    .brand-product { color: var(--muted); font-size: 0.72rem; margin-top: 0.12rem; }
    .sidebar-brand { display: flex; align-items: center; gap: 0.65rem; margin: 0.25rem 0 1.4rem; }
    .sidebar-mark {
        display: grid; place-items: center; width: 31px; height: 31px; border-radius: 7px;
        background: linear-gradient(135deg, #55d6c2, #82aaff); color: #08141c; font-weight: 800;
    }
    .sidebar-name { color: var(--text); font-weight: 750; font-size: 0.95rem; }
    .sidebar-subtitle { color: var(--muted); font-size: 0.66rem; margin-top: 0.1rem; }
    .sidebar-label { color: #718497; font-size: 0.67rem; font-weight: 750; text-transform: uppercase; margin: 0 0 0.45rem; }
    .sidebar-note { border-top: 1px solid var(--border); margin-top: 1.4rem; padding-top: 0.9rem; color: var(--muted); font-size: 0.74rem; }
    .header-meta { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0.55rem; }
    .meta-chip {
        display: inline-flex; align-items: center; gap: 0.42rem; padding: 0.35rem 0.65rem;
        border: 1px solid var(--border); border-radius: 7px; background: rgba(18, 27, 38, 0.88);
        color: #c3ceda; font-size: 0.72rem; white-space: nowrap;
    }
    .live-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--green); }
    .page-heading { display: flex; justify-content: space-between; align-items: flex-end; gap: 1rem; margin-bottom: 1.45rem; }
    .page-heading h1 { margin: 0.1rem 0 0.35rem; color: var(--text); font-size: 2rem; line-height: 1.15; }
    .page-heading p { margin: 0; }
    .page-kicker { color: var(--cyan); font-size: 0.7rem; font-weight: 750; text-transform: uppercase; }
    .page-description { color: var(--muted); font-size: 0.92rem; max-width: 760px; }
    .page-tag { border: 1px solid var(--border); border-radius: 7px; padding: 0.4rem 0.65rem; color: var(--muted); font-size: 0.72rem; white-space: nowrap; }
    .heading-icon { display: inline-grid; place-items: center; width: 34px; height: 34px; margin-right: 0.55rem; border: 1px solid #334254; border-radius: 8px; background: #172331; font-size: 1rem; vertical-align: 0.12em; }
    .overview-hero {
        display: grid; grid-template-columns: 1.03fr 0.97fr; gap: 1.2rem;
        padding: 1.55rem; margin: 0 0 1.35rem; border: 1px solid #2a394b; border-radius: 10px;
        background: linear-gradient(118deg, rgba(22, 38, 51, 0.98), rgba(22, 28, 48, 0.94) 64%, rgba(32, 29, 58, 0.92));
        box-shadow: 0 18px 50px rgba(0, 0, 0, 0.18);
    }
    .hero-kicker { display: inline-flex; align-items: center; gap: 0.45rem; color: var(--cyan); font-size: 0.68rem; font-weight: 750; text-transform: uppercase; }
    .hero-kicker-dot { width: 6px; height: 6px; border-radius: 50%; background: var(--green); }
    .hero-title { max-width: 620px; margin: 0.85rem 0 0.7rem; color: #f3f6fb; font-size: 2rem; font-weight: 760; line-height: 1.12; }
    .hero-title span { color: var(--cyan); }
    .hero-description { max-width: 570px; color: #adbac8; font-size: 0.91rem; line-height: 1.65; }
    .hero-footnote { margin-top: 1.25rem; color: #7f91a4; font-size: 0.72rem; }
    .workflow-panel { align-self: stretch; padding: 1rem; border: 1px solid rgba(135, 159, 190, 0.19); border-radius: 8px; background: rgba(8, 15, 23, 0.4); }
    .workflow-header { display: flex; justify-content: space-between; gap: 0.75rem; margin-bottom: 0.9rem; color: #dce5ed; font-size: 0.76rem; font-weight: 700; }
    .workflow-header span:last-child { color: #91a1b2; font-size: 0.67rem; font-weight: 500; }
    .workflow-steps { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 0.45rem; }
    .workflow-step { position: relative; min-width: 0; padding: 0.65rem 0.48rem; border: 1px solid #2a394a; border-radius: 7px; background: linear-gradient(160deg, #172432, #111b26); }
    .workflow-step:not(:last-child)::after { content: "›"; position: absolute; z-index: 1; top: 0.63rem; right: -0.42rem; color: #71859a; font-size: 1rem; }
    .workflow-icon { font-size: 1.1rem; }
    .workflow-label { margin-top: 0.5rem; color: #e7edf4; font-size: 0.71rem; font-weight: 700; }
    .workflow-detail { margin-top: 0.25rem; color: #91a1b2; font-size: 0.61rem; line-height: 1.35; overflow-wrap: anywhere; }
    .section-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 0.75rem; margin: 1.25rem 0 0.6rem; }
    .section-heading h2 { margin: 0; }
    .section-heading span { color: var(--muted); font-size: 0.72rem; }
    .finding-card { min-height: 125px; padding: 1rem; border: 1px solid var(--border); border-radius: 8px; background: linear-gradient(145deg, var(--surface-raised), var(--surface)); }
    .finding-label { color: #a5b2c0; font-size: 0.7rem; font-weight: 700; text-transform: uppercase; }
    .finding-title { margin: 0.55rem 0 0.3rem; color: var(--text); font-size: 0.94rem; font-weight: 700; }
    .finding-copy { color: var(--muted); font-size: 0.75rem; line-height: 1.5; }
    h1, h2, h3 { color: var(--text); }
    h2 { font-size: 1.12rem; }
    h3 { font-size: 0.98rem; }
    p, label, [data-testid="stMarkdownContainer"] { color: var(--text); }
    [data-testid="stCaptionContainer"], .subtle { color: var(--muted); }
    [data-testid="stMetric"] {
        background: linear-gradient(145deg, var(--surface-raised), var(--surface));
        border: 1px solid var(--border); border-radius: 8px;
        padding: 1rem 1.1rem; min-height: 112px;
        transition: transform 140ms ease, border-color 140ms ease;
    }
    [data-testid="stMetric"]:hover { transform: translateY(-2px); border-color: #3a5666; }
    [data-testid="stMetricLabel"] { color: #a6b5c3; }
    [data-testid="stMetricValue"] { color: #f4f7fb; font-weight: 700; }
    [data-testid="stMetricDelta"] { color: var(--cyan); }
    [data-testid="stDataFrame"] { border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
    [data-testid="stAlert"] { border-radius: 8px; }
    [data-testid="stExpander"] { border: 1px solid var(--border); border-radius: 8px; background: rgba(18, 27, 38, 0.72); }
    [data-baseweb="select"] > div { background: var(--surface); border-color: var(--border); }
    [data-testid="stDownloadButton"] button, [data-testid="stButton"] button {
        border: 1px solid #395266; border-radius: 7px; background: #172534; color: var(--text);
    }
    [data-testid="stDownloadButton"] button:hover, [data-testid="stButton"] button:hover {
        border-color: var(--cyan); color: var(--cyan);
    }
    hr { border-color: var(--border); }
    @media (max-width: 720px) {
        .block-container { padding: 1rem 1rem 2rem; }
        .app-topbar { align-items: flex-start; flex-direction: column; }
        .header-meta { justify-content: flex-start; }
        .page-heading { align-items: flex-start; flex-direction: column; }
        .page-heading h1 { font-size: 1.65rem; }
        .overview-hero { grid-template-columns: 1fr; padding: 1rem; }
        .hero-title { font-size: 1.65rem; }
        .workflow-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
        .workflow-step:not(:last-child)::after { display: none; }
        .section-heading { align-items: flex-start; flex-direction: column; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(show_spinner="Loading generated experiment data...")
def cached_tables() -> dict[str, pd.DataFrame]:
    """Cache CSV reads for the current Streamlit session."""
    return load_dashboard_data()


def format_metric_value(metric_name: str, value: float) -> str:
    """Format the common dashboard metrics in their natural units."""
    if metric_name in {"conversion_rate", "refund_rate"}:
        return f"{value:.2%}"
    if metric_name == "revenue_per_assigned_user":
        sign = "-" if value < 0 else ""
        return f"{sign}${abs(value):,.2f}"
    return f"{value:,.3f}"


def render_page_header(
    tables: dict[str, pd.DataFrame],
    title: str,
    description: str,
) -> None:
    """Show consistent product branding and the currently loaded data seed."""
    seed = int(tables["experiments"]["random_seed"].iloc[0])
    page_icons = {
        "Experiment Intelligence Platform": "🧪",
        "Experiments": "🧭",
        "Experiment results": "📈",
        "Guardrail metrics": "🛡️",
        "Data quality": "🔎",
        "Data explorer": "🗂️",
    }
    page_icon = page_icons.get(title, "📊")
    st.markdown(
        f"""
        <div class="app-topbar">
            <div class="brand-lockup">
                <div class="brand-mark">Y</div>
                <div>
                    <div class="brand-name">YottaFlex.ai</div>
                    <div class="brand-product">Experiment intelligence</div>
                </div>
            </div>
            <div class="header-meta">
                <span class="meta-chip"><span class="live-dot"></span>Generated dataset</span>
                <span class="meta-chip">Seed {seed}</span>
                <span class="meta-chip">{len(tables['experiments']):,} experiments</span>
            </div>
        </div>
        <div class="page-heading">
            <div>
                <p class="page-kicker">Analytics workspace</p>
                <h1><span class="heading-icon">{page_icon}</span>{title}</h1>
                <p class="page-description">{description}</p>
            </div>
            <div class="page-tag">CSV source · outputs/</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_overview_hero(tables: dict[str, pd.DataFrame]) -> None:
    """Show a data-driven workflow illustration for the generated run."""
    experiments = tables["experiments"]
    analyzed_count = int(experiments["status"].eq("analyzed").sum())
    workflow = [
        ("🧪", "Design", f"{len(experiments):,} plans"),
        ("🎲", "Randomize", f"{len(tables['assignments']):,} assignments"),
        ("👁️", "Observe", f"{len(tables['exposure_events']):,} exposures"),
        ("📈", "Analyze", f"{len(tables['experiment_results']):,} estimates"),
        ("🛡️", "Decide", f"{analyzed_count:,} analyzed"),
    ]
    workflow_markup = "".join(
        f"""
        <div class="workflow-step">
            <div class="workflow-icon">{icon}</div>
            <div class="workflow-label">{label}</div>
            <div class="workflow-detail">{detail}</div>
        </div>
        """
        for icon, label, detail in workflow
    )
    seed = int(experiments["random_seed"].iloc[0])
    st.markdown(
        f"""
        <section class="overview-hero">
            <div class="hero-copy">
                <div class="hero-kicker"><span class="hero-kicker-dot"></span>Experiment intelligence · reproducible run</div>
                <div class="hero-title">Run the experiment.<br><span>Trust the signal.</span></div>
                <div class="hero-description">
                    Follow each product change from randomized assignment through outcomes,
                    uncertainty, and guardrail review. This dashboard is showing the generated
                    cohort, not placeholder metrics.
                </div>
                <div class="hero-footnote">🧬 Synthetic dataset &nbsp;·&nbsp; Fixed seed {seed} &nbsp;·&nbsp; Intent-to-treat analysis</div>
            </div>
            <div class="workflow-panel">
                <div class="workflow-header">
                    <span>EXPERIMENT WORKFLOW</span>
                    <span>Observed run volume</span>
                </div>
                <div class="workflow-steps">{workflow_markup}</div>
            </div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def render_overview(tables: dict[str, pd.DataFrame], result_detail: pd.DataFrame) -> None:
    experiments = tables["experiments"]
    validation = tables["validation_summary"]
    checks = tables["validation_checks"]
    failed_check_count = int((~checks["passed"].astype(bool)).sum())
    conversions = len(tables["conversion_events"])
    guardrail_failures = result_detail.loc[
        result_detail["decision"] == "guardrail_failed"
    ]
    analyzed_count = int(experiments["status"].eq("analyzed").sum())
    passed_check_count = len(checks) - failed_check_count

    render_page_header(
        tables,
        "Experiment Intelligence Platform",
        "See how experiments move from randomized assignment to measurable outcomes and trustworthy decisions.",
    )
    render_overview_hero(tables)

    first_row = st.columns(5)
    first_row[0].metric("🧪 Experiments", f"{len(experiments):,}")
    first_row[1].metric("👥 Eligible users", f"{len(tables['audience_members']):,}")
    first_row[2].metric("🎲 Assignments", f"{len(tables['assignments']):,}")
    first_row[3].metric("⚡ Conversion events", f"{conversions:,}")
    first_row[4].metric("🔎 Data quality findings", f"{len(tables['anomalies']):,}")

    st.markdown(
        '<div class="section-heading"><h2>Portfolio health</h2>'
        '<span>Operational status of the generated run</span></div>',
        unsafe_allow_html=True,
    )
    health = st.columns(3)
    health[0].metric("Experiments analyzed", f"{analyzed_count} / {len(experiments)}")
    health[1].metric(
        "Validation checks passed",
        f"{passed_check_count} / {len(checks)}",
        delta=f"{failed_check_count} flagged" if failed_check_count else "All checks clear",
        delta_color="inverse" if failed_check_count else "normal",
    )
    health[2].metric("Guardrail failures", f"{len(guardrail_failures):,}")

    if failed_check_count:
        srm_cases = tables["anomalies"].loc[
            tables["anomalies"]["issue_type"] == "sample_ratio_mismatch_ignored"
        ]
        if not srm_cases.empty:
            srm_id = srm_cases.iloc[0]["entity_id"]
            st.warning(
                f"{srm_id} has a sample-ratio mismatch. Pause interpretation and investigate "
                "the assignment imbalance before trusting this experiment's results."
            )

    if not guardrail_failures.empty:
        failure = guardrail_failures.iloc[0]
        effect = format_metric_value(failure["metric_name"], failure["estimate"])
        st.error(
            f"Guardrail alert · {failure['experiment_id']} · "
            f"{failure['metric_name'].replace('_', ' ')} changed by {effect}. "
            "Review the Guardrail Metrics page before making a decision."
        )
    else:
        st.success("No guardrail failures were reported in this run.")

    left, right = st.columns([1.5, 1])
    with left:
        st.subheader("📈 Conversion rate by experiment")
        conversion_rows = result_detail.loc[
            result_detail["metric_name"] == "conversion_rate",
            ["experiment_id", "control_value", "treatment_value"],
        ].sort_values("experiment_id").rename(
            columns={"control_value": "Control", "treatment_value": "Treatment"}
        )
        st.bar_chart(
            conversion_rows.set_index("experiment_id"),
            x_label="Experiment",
            y_label="Share of assigned users",
            color=["#a78bfa", "#55d6c2"],
        )
        st.caption(
            "Each bar shows the observed share of assigned users who converted. "
            "Control is the current experience; treatment is the proposed change."
        )
    with right:
        st.subheader("🧭 Assignment review")
        review = validation.loc[
            ~validation["assignment_valid"],
            ["experiment_id", "assigned_n", "sample_ratio_p_value", "duplicate_assignment_count"],
        ]
        if review.empty:
            st.success("All experiments passed assignment checks.")
        else:
            st.dataframe(review, hide_index=True, width="stretch")
        st.caption("A small p-value means the observed arm split is unlikely under the declared allocation.")

    with st.expander("ℹ️ How to read this page"):
        st.write(
            "An assignment is a user's randomized group. A conversion event is a recorded event; "
            "the analysis only counts conversions inside each experiment's predeclared time window."
        )


def render_experiments(tables: dict[str, pd.DataFrame]) -> None:
    render_page_header(
        tables,
        "Experiments",
        "Review the experiment design, lifecycle, and declared control and treatment variants.",
    )
    experiments = tables["experiments"].copy()
    variants = tables["variants"]
    variant_names = variants.groupby("experiment_id").apply(
        lambda group: " · ".join(
            f"{row.variant_key}: {row.name}"
            for row in group.sort_values("variant_key").itertuples(index=False)
        ),
        include_groups=False,
    )
    experiments["variants"] = experiments["experiment_id"].map(variant_names)
    st.subheader("🧪 Experiment registry")
    st.caption("Each row is one predeclared experiment with its control and treatment variants.")
    status_options = sorted(experiments["status"].dropna().unique().tolist())
    selected_statuses = st.multiselect(
        "Filter by lifecycle status", status_options, default=status_options
    )
    filtered = experiments.loc[experiments["status"].isin(selected_statuses)]
    display_columns = ["experiment_id", "name", "status", "variants", "hypothesis"]
    st.dataframe(filtered[display_columns], hide_index=True, width="stretch")
    st.caption(f"Showing {len(filtered):,} of {len(experiments):,} experiments.")


def render_results(tables: dict[str, pd.DataFrame], result_detail: pd.DataFrame) -> None:
    render_page_header(
        tables,
        "Experiment results",
        "Compare observed control and treatment values, estimated effects, and uncertainty.",
    )
    experiments = tables["experiments"]
    selected_experiment = st.selectbox(
        "Choose an experiment",
        experiments["experiment_id"].tolist(),
        format_func=lambda experiment_id: (
            f"{experiment_id} · "
            f"{experiments.loc[experiments['experiment_id'] == experiment_id, 'name'].iloc[0]}"
        ),
    )
    experiment_results = result_detail.loc[
        result_detail["experiment_id"] == selected_experiment
    ].copy()
    metric_names = experiment_results["metric_name"].tolist()
    selected_metric = st.selectbox("Choose a metric", metric_names)
    result = experiment_results.loc[
        experiment_results["metric_name"] == selected_metric
    ].iloc[0]

    control_label, treatment_label = st.columns(2)
    control_label.metric("Control", format_metric_value(selected_metric, result["control_value"]))
    treatment_label.metric("Treatment", format_metric_value(selected_metric, result["treatment_value"]))

    effect_label = format_metric_value(selected_metric, result["estimate"])
    metric_label = selected_metric.replace("_", " ").title()
    ci_label = (
        f"{format_metric_value(selected_metric, result['ci_lower'])} to "
        f"{format_metric_value(selected_metric, result['ci_upper'])}"
    )
    result_left, result_right = st.columns([1, 1.5])
    result_valid = bool(result["result_valid"])
    with result_left:
        st.metric("Treatment effect", effect_label, help="Treatment average minus control average.")
        st.metric("95% confidence interval", ci_label)
        st.metric(
            "Result validity",
            "Valid" if result_valid else "Invalid",
            help="Invalid results are displayed for diagnosis but must not guide decisions.",
        )
        decision_label = "Invalid" if not result_valid else str(result["decision"])
        st.metric("Decision", decision_label.replace("_", " ").title())
        if not result_valid:
            st.warning(
                "This result is invalid because an assignment validity check failed. "
                "The estimate is shown for diagnosis only; do not use it for decisions."
            )
        elif result["decision"] == "positive":
            st.success("The interval is above zero, so this run shows evidence of a positive effect.")
        elif result["decision"] == "guardrail_failed":
            st.error("A safety metric crossed its predeclared guardrail.")
        else:
            st.info("The uncertainty interval includes zero; this run does not show a clear directional effect.")
        st.caption(f"p-value: {result['p_value']:.4f} · Smaller values indicate stronger evidence against no difference.")
    with result_right:
        chart = pd.DataFrame(
            {
                "Arm": ["Control", "Treatment"],
                "Observed value": [result["control_value"], result["treatment_value"]],
            }
        )
        st.bar_chart(
            chart,
            x="Arm",
            y="Observed value",
            y_label=metric_label,
            color="#55d6c2",
        )
        st.caption(
            "The confidence interval shows a range of effects consistent with the data. "
            "If it crosses zero, the result is not clearly different from no effect."
        )

    if pd.notna(result.get("expected_effect")):
        expected = format_metric_value(selected_metric, result["expected_effect"])
        st.info(
            f"Ground-truth population expectation for this metric: {expected}. "
            "This is a simulation reference value, not another observed result."
        )
    display = experiment_results[
        [
            "metric_name",
            "control_value",
            "treatment_value",
            "estimate",
            "ci_lower",
            "ci_upper",
            "p_value",
            "result_valid",
            "decision",
        ]
    ].copy()
    display.loc[~display["result_valid"], "decision"] = "invalid"
    display["metric_name"] = display["metric_name"].str.replace("_", " ").str.title()
    display["decision"] = display["decision"].str.replace("_", " ").str.title()
    display = display.rename(
        columns={
            "metric_name": "Metric",
            "control_value": "Control average",
            "treatment_value": "Treatment average",
            "estimate": "Effect",
            "ci_lower": "CI lower",
            "ci_upper": "CI upper",
            "p_value": "p-value",
            "result_valid": "Result valid",
            "decision": "Decision",
        }
    )
    st.subheader("📊 All metrics for this experiment")
    st.dataframe(display, hide_index=True, width="stretch")


def render_guardrails(tables: dict[str, pd.DataFrame], result_detail: pd.DataFrame) -> None:
    render_page_header(
        tables,
        "Guardrail metrics",
        "Check whether the primary change harmed revenue, refunds, or another protected outcome.",
    )
    guardrails = tables["guardrail_metrics"].merge(
        tables["metric_definitions"][
            ["metric_definition_id", "metric_name", "description", "unit"]
        ],
        on="metric_definition_id",
        validate="many_to_one",
    ).merge(
        result_detail[
            [
                "experiment_id",
                "metric_definition_id",
                "estimate",
                "ci_lower",
                "ci_upper",
                "decision",
            ]
        ],
        on=["experiment_id", "metric_definition_id"],
        validate="one_to_one",
    ).merge(
        tables["experiments"]["experiment_id"].to_frame(),
        on="experiment_id",
        validate="many_to_one",
    )
    failures = guardrails.loc[guardrails["decision"] == "guardrail_failed"]
    if failures.empty:
        st.success("No guardrail failures were reported in the generated results.")
    else:
        for failure in failures.itertuples(index=False):
            st.error(
                f"{failure.experiment_id}: {failure.metric_name.replace('_', ' ')} failed. "
                f"Observed effect {format_metric_value(failure.metric_name, failure.estimate)}; "
                f"95% interval {format_metric_value(failure.metric_name, failure.ci_lower)} to "
                f"{format_metric_value(failure.metric_name, failure.ci_upper)}."
            )
    display = guardrails[
        [
            "experiment_id",
            "metric_name",
            "comparison",
            "threshold",
            "estimate",
            "ci_lower",
            "ci_upper",
            "decision",
        ]
    ].sort_values(["experiment_id", "metric_name"])
    st.dataframe(display, hide_index=True, width="stretch")
    st.caption("A negative revenue effect beyond its allowed decrease is highlighted as a failure.")


def render_data_quality(tables: dict[str, pd.DataFrame]) -> None:
    render_page_header(
        tables,
        "Data quality",
        "Inspect validation results, labeled anomalies, and the separate ground-truth reference.",
    )
    checks = tables["validation_checks"].copy()
    checks["passed"] = checks["passed"].astype(bool)
    passed_count = int(checks["passed"].sum())
    failed_count = int((~checks["passed"]).sum())
    metrics = st.columns(3)
    metrics[0].metric("Checks passed", f"{passed_count:,}")
    metrics[1].metric("Checks flagged", f"{failed_count:,}")
    metrics[2].metric("Anomalies detected", f"{len(tables['anomalies']):,}")

    flagged = checks.loc[~checks["passed"]]
    if not flagged.empty:
        st.warning(
            "The flagged sample-ratio check is intentional: it demonstrates an experiment "
            "that should be paused and investigated before interpreting results."
        )
    with st.expander("Validation checks", expanded=True):
        st.dataframe(checks, hide_index=True, width="stretch", height=360)
    st.subheader("🚩 Detected anomalies")
    st.dataframe(tables["anomalies"], hide_index=True, width="stretch")
    st.subheader("🎯 Ground truth")
    st.caption("Ground truth is a separate evaluation reference; it is not used to calculate results.")
    truth_filter = st.selectbox(
        "Ground-truth rows",
        ["All rows", "Anomaly labels", "Numeric metric expectations"],
    )
    ground_truth = tables["ground_truth"]
    if truth_filter == "Anomaly labels":
        ground_truth = ground_truth.loc[ground_truth["issue_type"] != "expected_metric_effect"]
    elif truth_filter == "Numeric metric expectations":
        ground_truth = ground_truth.loc[ground_truth["issue_type"] == "expected_metric_effect"]
    st.dataframe(ground_truth, hide_index=True, width="stretch", height=400)


def render_data_explorer(tables: dict[str, pd.DataFrame]) -> None:
    render_page_header(
        tables,
        "Data explorer",
        "Search and filter the generated CSV tables, then download a focused slice.",
    )
    table_name = st.selectbox("Generated table", sorted(tables))
    frame = tables[table_name].copy()
    st.subheader("🗂️ Generated CSV browser")
    low_cardinality = [
        column
        for column in frame.columns
        if 1 < frame[column].nunique(dropna=True) <= 30
        and (pd.api.types.is_object_dtype(frame[column]) or pd.api.types.is_bool_dtype(frame[column]))
    ]
    filter_choices = ["No filter", "Text contains"] + low_cardinality
    filter_column = st.selectbox("Filter type or column", filter_choices)
    if filter_column == "Text contains":
        search_text = st.text_input("Search text", placeholder="For example: EXP-2026-000008")
        if search_text:
            searchable = frame.select_dtypes(include=["object", "string"])
            mask = searchable.apply(
                lambda column: column.str.contains(search_text, case=False, na=False)
            ).any(axis=1)
            frame = frame.loc[mask]
    elif filter_column != "No filter":
        options = sorted(frame[filter_column].dropna().astype(str).unique().tolist())
        selected = st.multiselect(f"Keep {filter_column} values", options, default=options)
        frame = frame.loc[frame[filter_column].astype(str).isin(selected)]

    st.caption(f"Showing {len(frame):,} rows from {table_name}.csv")
    st.dataframe(frame, hide_index=True, width="stretch", height=540)
    st.download_button(
        "Download filtered CSV",
        data=frame.to_csv(index=False).encode("utf-8"),
        file_name=f"{table_name}_filtered.csv",
        mime="text/csv",
    )


def main() -> None:
    st.sidebar.markdown(
        '<div class="sidebar-brand"><div class="sidebar-mark">Y</div>'
        '<div><div class="sidebar-name">YottaFlex.ai</div>'
        '<div class="sidebar-subtitle">EXPERIMENT ANALYTICS</div></div></div>',
        unsafe_allow_html=True,
    )
    st.sidebar.markdown(
        '<p class="sidebar-label">Workspace</p>', unsafe_allow_html=True
    )
    section = st.sidebar.radio(
        "Navigate",
        [
            "Overview",
            "Experiments",
            "Experiment Results",
            "Guardrail Metrics",
            "Data Quality",
            "Data Explorer",
        ],
    )
    st.sidebar.markdown(
        '<div class="sidebar-note">Read-only dashboard<br>Source: generated CSV outputs</div>',
        unsafe_allow_html=True,
    )
    try:
        tables = cached_tables()
    except FileNotFoundError as error:
        st.title("Experiment Analytics")
        st.warning(str(error))
        st.markdown("Generate the CSV outputs from the project folder first:")
        st.code(
            r".\.venv\Scripts\python.exe main.py --scale 1.0 --seed 20261022",
            language="powershell",
        )
        st.stop()

    result_detail = build_result_detail(tables)
    if section == "Overview":
        render_overview(tables, result_detail)
    elif section == "Experiments":
        render_experiments(tables)
    elif section == "Experiment Results":
        render_results(tables, result_detail)
    elif section == "Guardrail Metrics":
        render_guardrails(tables, result_detail)
    elif section == "Data Quality":
        render_data_quality(tables)
    else:
        render_data_explorer(tables)


if __name__ == "__main__":
    main()
