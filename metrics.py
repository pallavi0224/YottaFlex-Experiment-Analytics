"""Calculate predeclared ITT metrics, treatment effects, and uncertainty."""

import math

import numpy as np
import pandas as pd
from scipy import stats


def calculate_results(
	master_data: dict[str, pd.DataFrame],
	assignments: pd.DataFrame,
	conversion_events: pd.DataFrame,
	validation_summary: pd.DataFrame,
	confidence_level: float = 0.95,
) -> pd.DataFrame:
	"""Calculate one experiment-result row per primary or guardrail metric."""
	if not 0 < confidence_level < 1:
		raise ValueError("confidence_level must be between 0 and 1")

	experiments = master_data["experiments"].set_index("experiment_id")
	variants = master_data["variants"].set_index("variant_id")
	definitions = master_data["metric_definitions"]
	guardrails = master_data["guardrail_metrics"]
	validation_by_experiment = validation_summary.set_index("experiment_id")
	results = []

	for experiment_id, experiment in experiments.iterrows():
		experiment_assignments = assignments.loc[
			assignments["experiment_id"] == experiment_id
		].copy()
		experiment_assignments["variant_key"] = experiment_assignments[
			"variant_id"
		].map(variants["variant_key"])
		experiment_assignments["assigned_at"] = pd.to_datetime(
			experiment_assignments["assigned_at"], utc=True
		)
		experiment_assignments["has_conversion"] = False
		experiment_assignments["revenue"] = 0.0
		experiment_assignments["refunded"] = False
		experiment_assignments["has_non_refunded_conversion"] = False

		experiment_conversions = conversion_events.loc[
			conversion_events["assignment_id"].isin(
				experiment_assignments["assignment_id"]
			)
		].copy()
		if not experiment_conversions.empty:
			conversion_times = pd.to_datetime(
				experiment_conversions["converted_at"], format="mixed", utc=True
			)
			assignment_times = experiment_conversions["assignment_id"].map(
				experiment_assignments.set_index("assignment_id")["assigned_at"]
			)
			window_ends = assignment_times + pd.to_timedelta(
				int(experiment["outcome_window_days"]), unit="D"
			)
			in_window = (conversion_times >= assignment_times) & (
				conversion_times < window_ends
			)
			eligible_conversions = experiment_conversions.loc[in_window].copy()
			if not eligible_conversions.empty:
				per_assignment = eligible_conversions.groupby("assignment_id").agg(
					revenue=("conversion_value", "sum"),
					refunded=("is_refunded", "max"),
				)
				experiment_assignments["has_conversion"] = experiment_assignments[
					"assignment_id"
				].isin(per_assignment.index)
				experiment_assignments["revenue"] = experiment_assignments[
					"assignment_id"
				].map(per_assignment["revenue"]).fillna(0.0)
				experiment_assignments["refunded"] = experiment_assignments[
					"assignment_id"
				].map(per_assignment["refunded"]).fillna(False)
				non_refunded_assignments = eligible_conversions.loc[
					~eligible_conversions["is_refunded"].astype(bool), "assignment_id"
				].unique()
				experiment_assignments["has_non_refunded_conversion"] = (
					experiment_assignments["assignment_id"].isin(non_refunded_assignments)
				)

		experiment_guardrails = guardrails.loc[
			guardrails["experiment_id"] == experiment_id
		]
		metric_ids = [str(experiment["primary_metric_definition_id"])] + (
			experiment_guardrails["metric_definition_id"].astype(str).tolist()
		)
		validation_row = validation_by_experiment.loc[experiment_id]
		assignment_valid = bool(validation_row["assignment_valid"])

		for metric_definition_id in metric_ids:
			metric = definitions.loc[
				definitions["metric_definition_id"] == metric_definition_id
			].iloc[0]
			metric_name = str(metric["metric_name"])
			values = experiment_assignments.copy()
			metric_version = int(metric["version"])
			if metric_name == "conversion_rate" and metric_version == 1:
				values["metric_value"] = values["has_conversion"].astype(float)
			elif metric_name == "conversion_rate" and metric_version == 2:
				values["metric_value"] = values[
					"has_non_refunded_conversion"
				].astype(float)
			elif metric_name == "conversion_rate":
				raise ValueError(
					f"Unsupported conversion_rate definition version: {metric_version}"
				)
			elif metric_name == "revenue_per_assigned_user":
				values["metric_value"] = values["revenue"].astype(float)
			elif metric_name == "refund_rate":
				values["metric_value"] = values["refunded"].astype(float)
			else:
				raise ValueError(f"Unsupported metric definition: {metric_name}")

			control = values.loc[values["variant_key"] == "A", "metric_value"].to_numpy(
				dtype=float
			)
			treatment = values.loc[
				values["variant_key"] == "B", "metric_value"
			].to_numpy(dtype=float)
			result_valid = assignment_valid and bool(len(control) and len(treatment))
			if not len(control) or not len(treatment):
				estimate = standard_error = ci_lower = ci_upper = p_value = math.nan
				decision = "invalid"
			else:
				estimate = float(np.mean(treatment) - np.mean(control))
				control_variance = float(np.var(control, ddof=1)) if len(control) > 1 else 0.0
				treatment_variance = (
					float(np.var(treatment, ddof=1)) if len(treatment) > 1 else 0.0
				)
				standard_error = math.sqrt(
					control_variance / len(control) + treatment_variance / len(treatment)
				)
				if standard_error == 0:
					ci_lower = ci_upper = estimate
					p_value = 1.0 if estimate == 0 else 0.0
				else:
					degrees_of_freedom = (
						(control_variance / len(control) + treatment_variance / len(treatment)) ** 2
						/ (
							(control_variance / len(control)) ** 2 / max(len(control) - 1, 1)
							+ (treatment_variance / len(treatment)) ** 2
							/ max(len(treatment) - 1, 1)
						)
					)
					critical_value = stats.t.ppf(
						(1 + confidence_level) / 2, degrees_of_freedom
					)
					test_statistic = estimate / standard_error
					ci_lower = estimate - critical_value * standard_error
					ci_upper = estimate + critical_value * standard_error
					p_value = float(
						2 * stats.t.sf(abs(test_statistic), degrees_of_freedom)
					)

				decision = (
					"invalid"
					if not result_valid
					else "positive"
					if ci_lower > 0
					else "negative"
					if ci_upper < 0
					else "inconclusive"
				)

			guardrail = experiment_guardrails.loc[
				experiment_guardrails["metric_definition_id"] == metric_definition_id
			]
			if decision != "invalid" and not guardrail.empty:
				rule = guardrail.iloc[0]
				threshold = float(rule["threshold"])
				comparison = str(rule["comparison"])
				if comparison == "max_decrease" and ci_upper < -threshold:
					decision = "guardrail_failed"
				elif comparison == "max_increase" and ci_lower > threshold:
					decision = "guardrail_failed"
				elif comparison == "min_value" and float(np.mean(treatment)) < threshold:
					decision = "guardrail_failed"
				elif comparison == "max_value" and float(np.mean(treatment)) > threshold:
					decision = "guardrail_failed"

			results.append(
				{
					"result_id": f"RES-{experiment_id}-{metric_definition_id}-R001",
					"experiment_id": experiment_id,
					"metric_definition_id": metric_definition_id,
					"analysis_run": 1,
					"analysis_plan": str(experiment["analysis_plan"]),
					"control_n": int(len(control)),
					"treatment_n": int(len(treatment)),
					"estimate": estimate,
					"standard_error": standard_error,
					"confidence_level": confidence_level,
					"ci_lower": ci_lower,
					"ci_upper": ci_upper,
					"p_value": p_value,
					"result_valid": result_valid,
					"decision": decision,
					"analyzed_at": (
						pd.Timestamp(experiment["planned_end_at"])
						+ pd.Timedelta(days=int(experiment["outcome_window_days"]))
					).isoformat(),
				}
			)

	return pd.DataFrame(results)
