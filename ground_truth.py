"""Build separate evaluation labels from generated rules and calculated outcomes."""

import json

import pandas as pd

from config import (
	BASE_CONVERSION_RATE,
	BASE_REFUND_RATE,
	CONVERSION_VALUE_SCALE,
	CONVERSION_VALUE_SHAPE,
	CONTROL_CROSSOVER_RATE,
	EXPERIMENT_RATE_CYCLE,
	EXPERIMENT_RATE_INCREMENT,
	REFUND_REGRESSION_EXPERIMENT,
	REVENUE_REGRESSION_EXPERIMENT,
	REVENUE_REGRESSION_MULTIPLIER,
	TREATMENT_COMPLIANCE_RATE,
	TREATMENT_REFUND_RATE,
)


def generate_ground_truth(
	master_data: dict[str, pd.DataFrame],
	anomalies: pd.DataFrame,
) -> pd.DataFrame:
	"""Return numeric population expectations and anomaly labels, kept separate."""
	expected_decisions = {
		"multiple_variant_assignment": "invalid",
		"exposure_before_assignment": "invalid",
		"outcome_window_inconsistent": "exclude_out_of_window_conversion",
		"sample_ratio_mismatch_ignored": "block_analysis_and_investigate_srm",
		"guardrail_regression": "guardrail_failed",
		"metric_definition_changed_after_result": "retain_prior_definition_reference",
	}
	change_events = master_data.get(
		"metric_definition_change_events", pd.DataFrame()
	)
	change_events_by_id = (
		change_events.set_index("metric_definition_change_event_id").to_dict("index")
		if not change_events.empty
		else {}
	)
	rows = []
	for anomaly in anomalies.itertuples(index=False):
		change_event = change_events_by_id.get(str(anomaly.entity_id), {})
		rows.append(
			{
				"ground_truth_id": f"GT-{len(rows) + 1:06d}",
				"issue_type": anomaly.issue_type,
				"entity_type": anomaly.entity_type,
				"entity_id": anomaly.entity_id,
				"expected_label": (
					"version_change_after_analysis"
					if anomaly.issue_type == "metric_definition_changed_after_result"
					else "anomaly"
				),
				"expected_decision": expected_decisions[anomaly.issue_type],
				"metric_name": None,
				"metric_definition_id": change_event.get(
					"old_metric_definition_id"
				),
				"related_event_id": (
					str(anomaly.entity_id) if change_event else None
				),
				"old_metric_definition_id": change_event.get(
					"old_metric_definition_id"
				),
				"new_metric_definition_id": change_event.get(
					"new_metric_definition_id"
				),
				"event_timestamp": change_event.get("changed_at"),
				"event_reason": change_event.get("reason"),
				"expected_control": None,
				"expected_treatment": None,
				"expected_effect": None,
				"reason": anomaly.details,
			}
		)

	treatment_variant = master_data["variants"].loc[
		master_data["variants"]["variant_key"] == "B"
	].iloc[0]
	treatment_lift = float(
		json.loads(treatment_variant["treatment_parameters_json"])["conversion_lift"]
	)
	metric_ids = (
		master_data["metric_definitions"]
		.sort_values("version")
		.drop_duplicates("metric_name", keep="first")
		.set_index("metric_name")["metric_definition_id"]
		.to_dict()
	)
	mean_conversion_value = CONVERSION_VALUE_SHAPE * CONVERSION_VALUE_SCALE

	for experiment in master_data["experiments"].itertuples(index=False):
		experiment_number = int(experiment.experiment_id[-6:])
		base_rate = BASE_CONVERSION_RATE + EXPERIMENT_RATE_INCREMENT * (
			(experiment_number - 1) % EXPERIMENT_RATE_CYCLE
		)
		expected_metrics = []
		for arm, treatment_probability in [
			("control", CONTROL_CROSSOVER_RATE),
			("treatment", TREATMENT_COMPLIANCE_RATE),
		]:
			conversion_rate = base_rate + treatment_probability * treatment_lift
			refund_rate = (
				TREATMENT_REFUND_RATE
				if experiment_number == REFUND_REGRESSION_EXPERIMENT
				else BASE_REFUND_RATE
			)
			expected_refund_rate = conversion_rate * refund_rate
			revenue_multiplier = (
				REVENUE_REGRESSION_MULTIPLIER
				if experiment_number == REVENUE_REGRESSION_EXPERIMENT
				else 1.0
			)
			expected_revenue = mean_conversion_value * (
				(1 - treatment_probability) * base_rate
				+ treatment_probability * (base_rate + treatment_lift) * revenue_multiplier
			)
			expected_metrics.append(
				{
					"conversion_rate": conversion_rate,
					"refund_rate": expected_refund_rate,
					"revenue_per_assigned_user": expected_revenue,
				}
			)

		for metric_name in [
			"conversion_rate",
			"revenue_per_assigned_user",
			"refund_rate",
		]:
			control_value = expected_metrics[0][metric_name]
			treatment_value = expected_metrics[1][metric_name]
			rows.append(
				{
					"ground_truth_id": f"GT-{len(rows) + 1:06d}",
					"issue_type": "expected_metric_effect",
					"entity_type": "Experiment",
					"entity_id": experiment.experiment_id,
					"expected_label": "numeric_population_expectation",
					"expected_decision": "compare_with_estimate_and_uncertainty",
					"metric_name": metric_name,
					"metric_definition_id": metric_ids[metric_name],
					"related_event_id": None,
					"old_metric_definition_id": None,
					"new_metric_definition_id": None,
					"event_timestamp": None,
					"event_reason": None,
					"expected_control": control_value,
					"expected_treatment": treatment_value,
					"expected_effect": treatment_value - control_value,
					"reason": (
						"Expected arm means from base conversion rate, declared treatment lift, "
						"assignment compliance, and documented outcome-value/refund rules."
					),
				}
			)

	return pd.DataFrame(
		rows,
		columns=[
			"ground_truth_id",
			"issue_type",
			"entity_type",
			"entity_id",
			"expected_label",
			"expected_decision",
			"metric_name",
			"metric_definition_id",
			"related_event_id",
			"old_metric_definition_id",
			"new_metric_definition_id",
			"event_timestamp",
			"event_reason",
			"expected_control",
			"expected_treatment",
			"expected_effect",
			"reason",
		],
	)
