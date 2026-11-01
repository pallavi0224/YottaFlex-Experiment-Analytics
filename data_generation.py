"""Create deterministic parent and master records for synthetic experiments."""

import json
import math

import numpy as np
import pandas as pd

from config import (
	EXPERIMENT_COUNT,
	EXPERIMENT_YEAR,
	REVENUE_GUARDRAIL_MAX_DECREASE,
	SEED,
	TREATMENT_CONVERSION_LIFT,
	USERS_PER_EXPERIMENT,
)


def generate_master_data(
	scale: float = 1.0,
	seed: int = SEED,
) -> dict[str, pd.DataFrame]:
	"""Return reproducible experiment, variant, metric, and audience tables.

	A scale of 1.0 creates the full 50,000-user dataset. Smaller positive
	scales create a starter dataset with the same 10-experiment structure.
	"""
	if not math.isfinite(scale) or not 0 < scale <= 1:
		raise ValueError("scale must be greater than 0 and no greater than 1")

	rng = np.random.default_rng(seed)
	users_per_experiment = max(1, int(USERS_PER_EXPERIMENT * scale))

	metric_rows = [
		{
			"metric_definition_id": f"MET-{metric_name}-V001",
			"metric_name": metric_name,
			"version": 1,
			"description": description,
			"numerator": numerator,
			"denominator": denominator,
			"unit": unit,
			"analysis_unit": "assigned_user",
			"effective_from": f"{EXPERIMENT_YEAR}-01-01T00:00:00Z",
			"effective_to": "",
		}
		for metric_name, description, numerator, denominator, unit in [
			(
				"conversion_rate",
				"Share of assigned users with at least one in-window conversion, including refunded conversions.",
				"count of assigned users with at least one in-window conversion",
				"count of assigned users",
				"fraction",
			),
			(
				"revenue_per_assigned_user",
				"Total in-window conversion value divided by assigned users.",
				"sum of in-window conversion_value",
				"count of assigned users",
				"USD",
			),
			(
				"refund_rate",
				"Share of assigned users with an in-window refunded conversion.",
				"count of refunded converted users",
				"count of assigned users",
				"fraction",
			),
		]
	]
	updated_conversion_metric = metric_rows[0].copy()
	updated_conversion_metric.update(
		{
			"metric_definition_id": "MET-conversion_rate-V002",
			"version": 2,
			"description": (
				"Share of assigned users with at least one non-refunded in-window conversion."
			),
			"numerator": (
				"count of assigned users with at least one non-refunded in-window conversion"
			),
			"effective_from": "",
			"effective_to": "",
		}
	)
	metric_rows.append(updated_conversion_metric)
	experiment_rows = []
	variant_rows = []
	experiment_state_rows = []
	variant_state_rows = []
	audience_rows = []
	eligibility_rows = []
	guardrail_rows = []
	primary_metric_id = "MET-conversion_rate-V001"
	metric_ids = {
		row["metric_name"]: row["metric_definition_id"]
		for row in metric_rows
		if row["version"] == 1
	}

	for experiment_number in range(1, EXPERIMENT_COUNT + 1):
		experiment_id = f"EXP-{EXPERIMENT_YEAR}-{experiment_number:06d}"
		start = pd.Timestamp(f"{EXPERIMENT_YEAR}-01-01T00:00:00Z") + pd.Timedelta(
			days=(experiment_number - 1) * 30
		)
		end = start + pd.Timedelta(days=14)
		experiment_rows.append(
			{
				"experiment_id": experiment_id,
				"name": f"Synthetic experiment {experiment_number:02d}",
				"hypothesis": (
					"The treatment variant increases the conversion rate for "
					"eligible assigned users."
				),
				"primary_metric_definition_id": primary_metric_id,
				"analysis_plan": "ITT",
				"outcome_window_days": 7,
				"random_seed": seed,
				"planned_start_at": start.isoformat(),
				"planned_end_at": end.isoformat(),
				"status": "designed",
				"created_at": (start - pd.Timedelta(days=7)).isoformat(),
			}
		)
		experiment_state_rows.append(
			{
				"state_event_id": f"EXPSTATE-{experiment_id}-001",
				"experiment_id": experiment_id,
				"from_status": "draft",
				"to_status": "designed",
				"changed_at": (start - pd.Timedelta(days=7)).isoformat(),
				"reason": "Experiment design and analysis plan recorded.",
			}
		)

		for variant_key, variant_name in [("A", "control"), ("B", "treatment")]:
			variant_id = f"VAR-{experiment_id}-{variant_key}"
			variant_rows.append(
				{
					"variant_id": variant_id,
					"experiment_id": experiment_id,
					"variant_key": variant_key,
					"name": variant_name,
					"allocation_probability": 0.5,
					"treatment_parameters_json": "{}" if variant_key == "A" else json.dumps(
						{"conversion_lift": TREATMENT_CONVERSION_LIFT},
						separators=(",", ":"),
					),
					"effective_from": start.isoformat(),
					"effective_to": "",
					"status": "planned",
				}
			)
			variant_state_rows.append(
				{
					"state_event_id": f"VARSTATE-{experiment_id}-{variant_key}-001",
					"variant_id": variant_id,
					"from_status": "",
					"to_status": "planned",
					"changed_at": (start - pd.Timedelta(days=1)).isoformat(),
					"reason": "Variant registered for the experiment.",
				}
			)

		guardrail_rows.extend(
			[
				{
					"experiment_id": experiment_id,
					"metric_definition_id": metric_ids["revenue_per_assigned_user"],
					"comparison": "max_decrease",
					"threshold": REVENUE_GUARDRAIL_MAX_DECREASE,
					"alpha": 0.05,
					"effective_from": start.isoformat(),
					"effective_to": "",
				},
				{
					"experiment_id": experiment_id,
					"metric_definition_id": metric_ids["refund_rate"],
					"comparison": "max_increase",
					"threshold": 0.01,
					"alpha": 0.05,
					"effective_from": start.isoformat(),
					"effective_to": "",
				},
			]
		)

		first_user_number = (experiment_number - 1) * users_per_experiment + 1
		last_user_number = first_user_number + users_per_experiment
		for user_number in range(first_user_number, last_user_number):
			user_id = f"USR-{user_number:06d}"
			tenure_days = int(rng.integers(0, 731))
			audience_rows.append(
				{
					"user_id": user_id,
					"region": str(rng.choice(["north", "south", "east", "west"])),
					"device_type": str(rng.choice(["web", "ios", "android"])),
					"tenure_days": tenure_days,
					"created_at": (
						start - pd.Timedelta(days=tenure_days)
					).isoformat(),
				}
			)
			eligibility_rows.append(
				{
					"experiment_id": experiment_id,
					"user_id": user_id,
					"eligible": True,
					"eligibility_reason": "Meets synthetic experiment criteria.",
					"evaluated_at": start.isoformat(),
				}
			)

	change_at = max(
		pd.Timestamp(experiment["planned_end_at"])
		+ pd.Timedelta(days=int(experiment["outcome_window_days"]))
		+ pd.Timedelta(seconds=1)
		for experiment in experiment_rows
	) + pd.Timedelta(days=1)
	change_at_text = change_at.isoformat()
	metric_rows[0]["effective_to"] = change_at_text
	updated_conversion_metric["effective_from"] = change_at_text

	return {
		"experiments": pd.DataFrame(experiment_rows),
		"variants": pd.DataFrame(variant_rows),
		"audience_members": pd.DataFrame(audience_rows),
		"experiment_audience": pd.DataFrame(eligibility_rows),
		"metric_definitions": pd.DataFrame(metric_rows),
		"metric_definition_change_events": pd.DataFrame(
			[
				{
					"metric_definition_change_event_id": (
						"METRICDEFCHANGE-conversion_rate-V002"
					),
					"old_metric_definition_id": "MET-conversion_rate-V001",
					"new_metric_definition_id": "MET-conversion_rate-V002",
					"changed_at": change_at_text,
					"reason": (
						"After all experiment results were analyzed, conversion rate was "
						"redefined to count only assigned users with a non-refunded "
						"in-window conversion."
					),
				}
			]
		),
		"guardrail_metrics": pd.DataFrame(guardrail_rows),
		"experiment_state_events": pd.DataFrame(experiment_state_rows),
		"variant_state_events": pd.DataFrame(variant_state_rows),
	}
