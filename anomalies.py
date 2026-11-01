"""Surface labeled validation issues and statistically detected guardrail failures."""

import pandas as pd


def detect_anomalies(
	validation_issues: pd.DataFrame,
	experiment_results: pd.DataFrame,
	master_data: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
	"""Return required negative cases plus calculated guardrail regressions."""
	required_cases = {
		"multiple_variant_assignment",
		"exposure_before_assignment",
		"outcome_window_inconsistent",
		"sample_ratio_mismatch_ignored",
		"metric_definition_changed_after_result",
	}
	rows = []
	change_events = (
		master_data.get("metric_definition_change_events", pd.DataFrame())
		if master_data is not None
		else pd.DataFrame()
	)
	change_event_ids = (
		set(change_events["metric_definition_change_event_id"].astype(str))
		if "metric_definition_change_event_id" in change_events
		else None
	)
	for issue in validation_issues.itertuples(index=False):
		if issue.issue_type in required_cases:
			if (
				issue.issue_type == "metric_definition_changed_after_result"
				and change_event_ids is not None
				and str(issue.entity_id) not in change_event_ids
			):
				continue
			if issue.issue_type == "sample_ratio_mismatch_ignored":
				result_decisions = experiment_results.loc[
					experiment_results["experiment_id"] == issue.entity_id,
					"decision",
				]
				if result_decisions.empty:
					continue
			rows.append(
				{
					"issue_type": issue.issue_type,
					"entity_type": issue.entity_type,
					"entity_id": issue.entity_id,
					"details": issue.details,
				}
			)

	guardrail_failures = experiment_results.loc[
		experiment_results["decision"] == "guardrail_failed"
	]
	for result in guardrail_failures.itertuples(index=False):
		rows.append(
			{
				"issue_type": "guardrail_regression",
				"entity_type": "ExperimentResult",
				"entity_id": result.result_id,
				"details": f"Guardrail metric failed with estimated effect {result.estimate}.",
			}
		)

	return pd.DataFrame(
		rows, columns=["issue_type", "entity_type", "entity_id", "details"]
	)
