"""Randomly assign each eligible experiment-user pair to a variant."""

import numpy as np
import pandas as pd

from config import EXPERIMENT_COUNT, SEED


def generate_assignments(
	master_data: dict[str, pd.DataFrame],
	seed: int = SEED,
) -> pd.DataFrame:
	"""Return immutable seeded assignments for eligible audience members.

	The final experiment deliberately uses a 65/35 split despite its declared
	50/50 allocation, creating a reproducible sample-ratio-mismatch case.
	"""
	rng = np.random.default_rng(seed + 1)
	experiments = master_data["experiments"]
	variants = master_data["variants"]
	eligibility = master_data["experiment_audience"]
	rows = []

	for experiment_index, experiment in experiments.iterrows():
		experiment_id = str(experiment["experiment_id"])
		experiment_variants = variants.loc[variants["experiment_id"] == experiment_id]
		variant_ids = experiment_variants["variant_id"].tolist()
		declared_probabilities = experiment_variants["allocation_probability"].to_numpy(
			dtype=float
		)
		eligible_users = eligibility.loc[
			(eligibility["experiment_id"] == experiment_id)
			& eligibility["eligible"]
		]["user_id"].to_numpy()
		assigned_at = str(experiment["planned_start_at"])

		if experiment_index == EXPERIMENT_COUNT - 1:
			first_variant_count = round(len(eligible_users) * 0.65)
		else:
			first_variant_count = (len(eligible_users) + 1) // 2
		second_variant_count = len(eligible_users) - first_variant_count
		selected_variants = np.concatenate(
			[
				np.repeat(variant_ids[0], first_variant_count),
				np.repeat(variant_ids[1], second_variant_count),
			]
		)
		selected_variants = rng.permutation(selected_variants)
		for user_id, variant_id in zip(eligible_users, selected_variants):
			rows.append(
				{
					"assignment_id": f"ASG-{experiment_id}-{user_id}",
					"experiment_id": experiment_id,
					"user_id": str(user_id),
					"variant_id": str(variant_id),
					"assigned_at": assigned_at,
					"allocation_probability": float(
						declared_probabilities[variant_ids.index(variant_id)]
					),
					"assignment_method": "seeded_random",
				}
			)

	assignments = pd.DataFrame(rows)

	# Keep one duplicate as an explicit row so the integrity validator can
	# surface the exception; never change the original assignment.
	first_assignment = assignments.iloc[0].copy()
	experiment_variants = variants.loc[
		variants["experiment_id"] == first_assignment["experiment_id"]
	]
	alternate_variant = experiment_variants.loc[
		experiment_variants["variant_id"] != first_assignment["variant_id"],
		"variant_id",
	].iloc[0]
	first_assignment["assignment_id"] = f"{first_assignment['assignment_id']}-DUP01"
	first_assignment["variant_id"] = alternate_variant
	assignments = pd.concat(
		[assignments, first_assignment.to_frame().T], ignore_index=True
	)
	return assignments
