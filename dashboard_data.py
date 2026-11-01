"""Load generated CSV outputs and derive actual dashboard arm summaries."""

from pathlib import Path

import pandas as pd

from config import OUTPUT_DIR

REQUIRED_TABLES = {
    "experiments",
    "variants",
    "assignments",
    "conversion_events",
    "experiment_results",
    "metric_definitions",
    "metric_definition_change_events",
    "guardrail_metrics",
    "validation_summary",
    "validation_checks",
    "anomalies",
    "ground_truth",
}


def load_dashboard_data(output_dir: Path = OUTPUT_DIR) -> dict[str, pd.DataFrame]:
    """Load all CSV tables from the pipeline output folder.

    Raises a beginner-friendly error if the pipeline has not generated its
    required files yet. Every displayed value comes from these CSVs.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        raise FileNotFoundError(
            f"Output folder not found: {output_dir}. Run main.py to generate the dataset first."
        )

    tables = {
        csv_path.stem: pd.read_csv(csv_path)
        for csv_path in sorted(output_dir.glob("*.csv"))
    }
    missing_tables = sorted(REQUIRED_TABLES - tables.keys())
    if missing_tables:
        missing_files = ", ".join(f"{name}.csv" for name in missing_tables)
        raise FileNotFoundError(
            f"Required dashboard outputs are missing: {missing_files}. "
            "Run main.py to generate the dataset first."
        )
    return tables


def build_result_detail(tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Add observed control/treatment means to the pipeline's result rows.

    User-level metrics follow the experiment's predeclared conversion window.
    Conversion events outside that window remain in the source files but do not
    contribute to the displayed arm averages.
    """
    experiments = tables["experiments"][
        ["experiment_id", "outcome_window_days"]
    ].rename(columns={"outcome_window_days": "analysis_window_days"})
    variant_keys = tables["variants"][
        ["variant_id", "variant_key"]
    ]
    assignments = tables["assignments"].merge(
        variant_keys, on="variant_id", how="left", validate="many_to_one"
    ).merge(
        experiments, on="experiment_id", how="left", validate="many_to_one"
    )
    assignments["assigned_at_parsed"] = pd.to_datetime(
        assignments["assigned_at"], utc=True
    )

    conversions = tables["conversion_events"].merge(
        assignments[
            [
                "assignment_id",
                "assigned_at_parsed",
                "analysis_window_days",
            ]
        ],
        on="assignment_id",
        how="left",
        validate="many_to_one",
    )
    conversions["converted_at_parsed"] = pd.to_datetime(
        conversions["converted_at"], format="mixed", utc=True
    )
    window_end = conversions["assigned_at_parsed"] + pd.to_timedelta(
        conversions["analysis_window_days"], unit="D"
    )
    in_window = (conversions["converted_at_parsed"] >= conversions["assigned_at_parsed"]) & (
        conversions["converted_at_parsed"] < window_end
    )
    valid_conversions = conversions.loc[in_window]
    conversion_by_assignment = valid_conversions.groupby("assignment_id").agg(
        revenue=("conversion_value", "sum"),
        refunded=("is_refunded", "max"),
    )

    assignments["has_conversion"] = assignments["assignment_id"].isin(
        conversion_by_assignment.index
    )
    assignments["revenue_per_user"] = assignments["assignment_id"].map(
        conversion_by_assignment["revenue"]
    ).fillna(0.0)
    assignments["refunded_user"] = assignments["assignment_id"].map(
        conversion_by_assignment["refunded"]
    ).fillna(False)

    metric_columns = {
        "conversion_rate": "has_conversion",
        "revenue_per_assigned_user": "revenue_per_user",
        "refund_rate": "refunded_user",
    }
    mean_rows = []
    for metric_name, value_column in metric_columns.items():
        means = (
            assignments.groupby(["experiment_id", "variant_key"])[value_column]
            .mean()
            .rename("metric_value")
            .reset_index()
        )
        means["metric_name"] = metric_name
        mean_rows.append(means)
    arm_means = pd.concat(mean_rows, ignore_index=True).pivot(
        index=["experiment_id", "metric_name"],
        columns="variant_key",
        values="metric_value",
    )
    arm_means = arm_means.rename(
        columns={"A": "control_value", "B": "treatment_value"}
    ).reset_index()

    definitions = tables["metric_definitions"][
        ["metric_definition_id", "metric_name"]
    ]
    results = tables["experiment_results"].merge(
        definitions,
        on="metric_definition_id",
        how="left",
        validate="many_to_one",
    ).merge(
        arm_means,
        on=["experiment_id", "metric_name"],
        how="left",
        validate="one_to_one",
    )
    if "result_valid" not in results:
        assignment_validity = tables["validation_summary"][
            ["experiment_id", "assignment_valid"]
        ]
        results = results.merge(
            assignment_validity,
            on="experiment_id",
            how="left",
            validate="many_to_one",
        )
        results["result_valid"] = (
            results["assignment_valid"].astype(bool)
            & results["decision"].ne("invalid")
        )
        results = results.drop(columns="assignment_valid")

    numeric_ground_truth = tables["ground_truth"].loc[
        tables["ground_truth"]["issue_type"] == "expected_metric_effect",
        [
			"entity_id",
            "metric_definition_id",
            "expected_control",
            "expected_treatment",
            "expected_effect",
        ],
    ].rename(columns={"entity_id": "experiment_id"})
    if not numeric_ground_truth.empty:
        results = results.merge(
            numeric_ground_truth,
            on=["experiment_id", "metric_definition_id"],
            how="left",
            validate="one_to_one",
        )
    return results
