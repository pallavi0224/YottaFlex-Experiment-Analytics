"""Simulate exposure telemetry and conversions from randomized assignments."""

import json

import numpy as np
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
	SEED,
	TREATMENT_COMPLIANCE_RATE,
	TREATMENT_REFUND_RATE,
)


def simulate_events(
	master_data: dict[str, pd.DataFrame],
	assignments: pd.DataFrame,
	seed: int = SEED,
) -> dict[str, pd.DataFrame]:
	"""Create exposure and conversion events with controlled synthetic effects."""
	rng = np.random.default_rng(seed + 2)
	experiments = master_data["experiments"].set_index("experiment_id")
	variants = master_data["variants"].set_index("variant_id")
	exposure_rows = []
	conversion_rows = []
	exposure_counter = 1
	conversion_counter = 1
	early_exposure_injected = False

	for assignment in assignments.itertuples(index=False):
		experiment_id = assignment.experiment_id
		experiment_number = int(experiment_id[-6:])
		experiment = experiments.loc[experiment_id]
		assigned_variant = assignment.variant_id
		assigned_key = variants.loc[assigned_variant, "variant_key"]
		user_has_duplicate = assignment.assignment_id.endswith("-DUP01")

		# Treatment recipients can differ from their randomized assignment.
		received_key = assigned_key
		if assigned_key == "B" and rng.random() >= TREATMENT_COMPLIANCE_RATE:
			received_key = "A"
		elif assigned_key == "A" and rng.random() < CONTROL_CROSSOVER_RATE:
			received_key = "B"
		received_variant_id = f"VAR-{experiment_id}-{received_key}"

		assignment_time = pd.Timestamp(assignment.assigned_at)
		has_missing_telemetry = rng.random() < 0.03
		exposure_time = ""
		if not has_missing_telemetry:
			exposure_time = (
				assignment_time + pd.Timedelta(minutes=int(rng.integers(1, 1441)))
			).isoformat()
		exposure_id = f"EXPOS-{2026}-{exposure_counter:06d}"
		exposure_counter += 1
		exposure_rows.append(
			{
				"exposure_id": exposure_id,
				"assignment_id": assignment.assignment_id,
				"received_variant_id": "" if has_missing_telemetry else received_variant_id,
				"telemetry_status": "missing" if has_missing_telemetry else "observed",
				"exposed_at": exposure_time,
				"surface": str(rng.choice(["web", "ios", "android"])),
				"created_at": (
					(assignment_time + pd.Timedelta(hours=1)).isoformat()
					if has_missing_telemetry
					else (pd.Timestamp(exposure_time) + pd.Timedelta(seconds=1)).isoformat()
				),
			}
		)

		# Inject timing issues into dedicated labeled records, not baseline rows.
		if not early_exposure_injected and not user_has_duplicate:
			early_exposure_id = f"EXPOS-{2026}-{exposure_counter:06d}"
			exposure_counter += 1
			early_time = (assignment_time - pd.Timedelta(hours=1)).isoformat()
			exposure_rows.append(
				{
					"exposure_id": early_exposure_id,
					"assignment_id": assignment.assignment_id,
					"received_variant_id": received_variant_id,
					"telemetry_status": "observed",
					"exposed_at": early_time,
					"surface": "web",
					"created_at": early_time,
				}
			)
			early_exposure_injected = True

		base_conversion_rate = BASE_CONVERSION_RATE + EXPERIMENT_RATE_INCREMENT * (
			(experiment_number - 1) % EXPERIMENT_RATE_CYCLE
		)
		treatment_parameters = json.loads(
			variants.loc[received_variant_id, "treatment_parameters_json"]
		)
		treatment_lift = float(treatment_parameters.get("conversion_lift", 0.0))
		conversion_probability = base_conversion_rate + treatment_lift
		if rng.random() >= conversion_probability:
			continue

		delay_days = float(rng.uniform(0.05, 6.8))
		converted_at = (assignment_time + pd.Timedelta(days=delay_days)).isoformat()
		refund_rate = (
			TREATMENT_REFUND_RATE
			if experiment_number == REFUND_REGRESSION_EXPERIMENT and received_key == "B"
			else BASE_REFUND_RATE
		)
		is_refunded = rng.random() < refund_rate
		conversion_value = float(
			rng.gamma(shape=CONVERSION_VALUE_SHAPE, scale=CONVERSION_VALUE_SCALE)
		)
		if experiment_number == REVENUE_REGRESSION_EXPERIMENT and received_key == "B":
			conversion_value *= REVENUE_REGRESSION_MULTIPLIER

		conversion_rows.append(
			{
				"conversion_id": f"CONV-{2026}-{conversion_counter:06d}",
				"assignment_id": assignment.assignment_id,
				"converted_at": converted_at,
				"outcome_window_days": int(experiment["outcome_window_days"]),
				"conversion_value": conversion_value,
				"currency": "USD",
				"source": str(rng.choice(["web", "ios", "android"])),
				"is_refunded": bool(is_refunded),
			}
		)
		conversion_counter += 1

	# Keep the known window issue separate from valid outcomes so the analysis
	# can exclude it using the experiment's predeclared seven-day window.
	assignment = assignments.loc[
		~assignments["assignment_id"].str.endswith("-DUP01")
	].iloc[0]
	experiment = experiments.loc[assignment["experiment_id"]]
	assignment_time = pd.Timestamp(assignment["assigned_at"])
	conversion_rows.append(
		{
			"conversion_id": f"CONV-{2026}-{conversion_counter:06d}",
			"assignment_id": assignment["assignment_id"],
			"converted_at": (assignment_time + pd.Timedelta(days=8)).isoformat(),
			"outcome_window_days": int(experiment["outcome_window_days"]) + 30,
			"conversion_value": 24.0,
			"currency": "USD",
			"source": "web",
			"is_refunded": False,
		}
	)

	return {
		"exposure_events": pd.DataFrame(exposure_rows),
		"conversion_events": pd.DataFrame(conversion_rows),
	}
