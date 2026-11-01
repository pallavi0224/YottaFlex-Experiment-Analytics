"""Validate key integrity, randomization, lifecycle, and derived results."""

import re

import numpy as np
import pandas as pd
from scipy import stats


def validate_dataset(tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
	"""Return per-experiment checks, detailed issues, and check totals."""
	issues: list[dict[str, str]] = []
	check_rows: list[dict[str, object]] = []

	def add_issue(
		issue_type: str,
		entity_type: str,
		entity_id: str,
		details: str,
		severity: str = "error",
	) -> None:
		issues.append(
			{
				"issue_type": issue_type,
				"entity_type": entity_type,
				"entity_id": entity_id,
				"severity": severity,
				"details": details,
			}
		)

	def record_check(check_name: str, passed: bool, rows_checked: int) -> None:
		check_rows.append(
			{
				"check_name": check_name,
				"passed": bool(passed),
				"rows_checked": int(rows_checked),
			}
		)

	primary_keys = {
		"experiments": ["experiment_id"],
		"variants": ["variant_id"],
		"audience_members": ["user_id"],
		"experiment_audience": ["experiment_id", "user_id"],
		"assignments": ["assignment_id"],
		"exposure_events": ["exposure_id"],
		"conversion_events": ["conversion_id"],
		"metric_definitions": ["metric_definition_id"],
		"metric_definition_change_events": [
			"metric_definition_change_event_id"
		],
		"guardrail_metrics": ["experiment_id", "metric_definition_id"],
		"experiment_results": ["result_id"],
		"experiment_state_events": ["state_event_id"],
		"variant_state_events": ["state_event_id"],
		"ground_truth": ["ground_truth_id"],
	}
	for table_name, key_columns in primary_keys.items():
		frame = tables.get(table_name, pd.DataFrame())
		if frame.empty and table_name not in tables:
			continue
		duplicate_mask = frame.duplicated(key_columns, keep=False)
		duplicate_count = int(duplicate_mask.sum())
		for _, row in frame.loc[duplicate_mask].iterrows():
			add_issue(
				"duplicate_primary_key",
				table_name,
				"|".join(str(row[column]) for column in key_columns),
				f"Duplicate values for primary key columns {key_columns}.",
			)
		record_check(f"{table_name}_primary_key_unique", duplicate_count == 0, len(frame))

	experiments = tables["experiments"].set_index("experiment_id")
	variants = tables["variants"]
	audience = tables["audience_members"]
	eligibility = tables["experiment_audience"]
	assignments = tables["assignments"]
	exposures = tables["exposure_events"]
	conversions = tables["conversion_events"]
	metric_definitions = tables["metric_definitions"]
	guardrails = tables["guardrail_metrics"]
	results = tables.get("experiment_results", pd.DataFrame())

	enum_specs = {
		("experiments", "analysis_plan"): {"ITT"},
		("experiments", "status"): {
			"draft", "designed", "running", "completed", "analyzed", "archived"
		},
		("variants", "variant_key"): {"A", "B"},
		("variants", "status"): {"planned", "active", "paused", "retired"},
		("audience_members", "region"): {"north", "south", "east", "west"},
		("audience_members", "device_type"): {"web", "ios", "android"},
		("assignments", "assignment_method"): {"seeded_random"},
		("exposure_events", "telemetry_status"): {"observed", "missing"},
		("exposure_events", "surface"): {"web", "ios", "android"},
		("conversion_events", "currency"): {"USD"},
		("conversion_events", "source"): {"web", "ios", "android"},
		("metric_definitions", "unit"): {"count", "fraction", "USD", "days"},
		("metric_definitions", "analysis_unit"): {"assigned_user"},
		("guardrail_metrics", "comparison"): {
			"max_increase", "max_decrease", "min_value", "max_value"
		},
		("experiment_results", "analysis_plan"): {"ITT"},
		("experiment_results", "decision"): {
			"positive", "negative", "inconclusive", "guardrail_failed", "invalid"
		},
	}
	for (table_name, column), allowed_values in enum_specs.items():
		frame = tables.get(table_name, pd.DataFrame())
		if frame.empty or column not in frame:
			continue
		invalid_values = frame[column].notna() & ~frame[column].astype(str).isin(
			allowed_values
		)
		for value in frame.loc[invalid_values, column].astype(str).unique():
			add_issue(
				"invalid_enum_value",
				table_name,
				value,
				f"{column} must be one of {sorted(allowed_values)}.",
			)
		record_check(
			f"{table_name}_{column}_allowed_values",
			not bool(invalid_values.any()),
			len(frame),
		)

	id_patterns = {
		("experiments", "experiment_id"): r"EXP-2026-\d{6}",
		("audience_members", "user_id"): r"USR-\d{6}",
		("variants", "variant_id"): r"VAR-EXP-2026-\d{6}-[AB]",
		("exposure_events", "exposure_id"): r"EXPOS-2026-\d{6}",
		("conversion_events", "conversion_id"): r"CONV-2026-\d{6}",
		("metric_definitions", "metric_definition_id"): r"MET-[a-z_]+-V\d{3}",
	}
	for (table_name, column), pattern in id_patterns.items():
		frame = tables.get(table_name, pd.DataFrame())
		if frame.empty or column not in frame:
			continue
		invalid_ids = ~frame[column].astype(str).map(
			lambda value: re.fullmatch(pattern, value) is not None
		)
		for value in frame.loc[invalid_ids, column].astype(str):
			add_issue(
				"invalid_id_format",
				table_name,
				value,
				f"{column} does not match {pattern}.",
			)
		record_check(
			f"{table_name}_{column}_format",
			not bool(invalid_ids.any()),
			len(frame),
		)

	assignment_ids_valid = assignments.apply(
		lambda row: row["assignment_id"]
		in {
			f"ASG-{row['experiment_id']}-{row['user_id']}",
			f"ASG-{row['experiment_id']}-{row['user_id']}-DUP01",
		},
		axis=1,
	)
	for row in assignments.loc[~assignment_ids_valid].itertuples(index=False):
		add_issue(
			"invalid_id_format",
			"Assignment",
			row.assignment_id,
			"Assignment ID does not match the experiment/user naming convention.",
		)
	record_check(
		"assignments_assignment_id_format",
		bool(assignment_ids_valid.all()),
		len(assignments),
	)

	numeric_rules = [
		("experiments", "outcome_window_days", 0, False, None, False),
		("audience_members", "tenure_days", 0, True, None, False),
		("variants", "allocation_probability", 0, False, 1, True),
		("assignments", "allocation_probability", 0, False, 1, True),
		("guardrail_metrics", "alpha", 0, False, 1, False),
		("conversion_events", "outcome_window_days", 0, False, None, False),
		("conversion_events", "conversion_value", 0, True, None, False),
		("experiment_results", "control_n", 0, True, None, False),
		("experiment_results", "treatment_n", 0, True, None, False),
		("experiment_results", "standard_error", 0, True, None, False),
		("experiment_results", "confidence_level", 0, False, 1, False),
	]
	for table_name, column, low, low_inclusive, high, high_inclusive in numeric_rules:
		frame = tables.get(table_name, pd.DataFrame())
		if frame.empty or column not in frame:
			continue
		values = pd.to_numeric(frame[column], errors="coerce")
		invalid_values = ~np.isfinite(values)
		if low is not None:
			invalid_values |= values.lt(low) if low_inclusive else values.le(low)
		if high is not None:
			invalid_values |= values.gt(high) if high_inclusive else values.ge(high)
		for index in frame.index[invalid_values]:
			add_issue(
				"numeric_value_out_of_range",
				table_name,
				str(frame.loc[index].iloc[0]),
				f"{column} is not finite or is outside its allowed range.",
			)
		record_check(
			f"{table_name}_{column}_range",
			not bool(invalid_values.any()),
			len(frame),
		)

	for metric_name, versions in metric_definitions.groupby("metric_name"):
		ordered_versions = versions.sort_values("version")
		version_rows = list(ordered_versions.itertuples(index=False))
		for previous, current in zip(version_rows, version_rows[1:]):
			previous_end = previous.effective_to
			if pd.isna(previous_end) or str(previous_end) == "":
				valid_interval = False
			else:
				valid_interval = pd.Timestamp(current.effective_from) >= pd.Timestamp(previous_end)
			if not valid_interval:
				add_issue(
					"metric_definition_effective_dates_overlap",
					"MetricDefinition",
				str(current.metric_definition_id),
				f"Versions for {metric_name} have overlapping or open-ended prior dates.",
				)

	# Validate direct and composite parent references before joining records.
	foreign_key_specs = [
		("variants", "experiment_id", "experiments", "experiment_id"),
		(
			"experiments",
			"primary_metric_definition_id",
			"metric_definitions",
			"metric_definition_id",
		),
		(
			"metric_definition_change_events",
			"old_metric_definition_id",
			"metric_definitions",
			"metric_definition_id",
		),
		(
			"metric_definition_change_events",
			"new_metric_definition_id",
			"metric_definitions",
			"metric_definition_id",
		),
		("experiment_audience", "experiment_id", "experiments", "experiment_id"),
		("experiment_audience", "user_id", "audience_members", "user_id"),
		("assignments", "experiment_id", "experiments", "experiment_id"),
		("assignments", "user_id", "audience_members", "user_id"),
		("assignments", "variant_id", "variants", "variant_id"),
		("exposure_events", "assignment_id", "assignments", "assignment_id"),
		("exposure_events", "received_variant_id", "variants", "variant_id"),
		("conversion_events", "assignment_id", "assignments", "assignment_id"),
		("guardrail_metrics", "experiment_id", "experiments", "experiment_id"),
		(
			"guardrail_metrics",
			"metric_definition_id",
			"metric_definitions",
			"metric_definition_id",
		),
		(
			"experiment_state_events",
			"experiment_id",
			"experiments",
			"experiment_id",
		),
		("variant_state_events", "variant_id", "variants", "variant_id"),
		("experiment_results", "experiment_id", "experiments", "experiment_id"),
		(
			"experiment_results",
			"metric_definition_id",
			"metric_definitions",
			"metric_definition_id",
		),
	]
	for child_name, child_column, parent_name, parent_column in foreign_key_specs:
		child = tables.get(child_name, pd.DataFrame())
		if child.empty or child_column not in child:
			continue
		parent_values = set(tables[parent_name][parent_column].dropna().astype(str))
		child_values = child[child_column].astype(str)
		invalid_mask = child[child_column].notna() & child_values.ne("") & ~child_values.isin(
			parent_values
		)
		for value in child.loc[invalid_mask, child_column].astype(str):
			add_issue(
				"foreign_key_violation",
				child_name,
				value,
				f"{child_column} does not reference an existing {parent_name} row.",
			)
		record_check(
			f"{child_name}_{child_column}_foreign_key",
			not bool(invalid_mask.any()),
			len(child),
		)

	variants_by_id = variants.set_index("variant_id")
	variant_counts = variants.groupby("experiment_id").agg(
		variant_count=("variant_id", "size"),
		allocation_probability_sum=("allocation_probability", "sum"),
	)
	for experiment_id in experiments.index:
		if experiment_id in variant_counts.index:
			variant_summary = variant_counts.loc[experiment_id]
			variant_count = int(variant_summary["variant_count"])
			allocation_probability_sum = float(
				variant_summary["allocation_probability_sum"]
			)
		else:
			variant_count = 0
			allocation_probability_sum = 0.0
		experiment_keys = set(
			variants.loc[variants["experiment_id"] == experiment_id, "variant_key"]
		)
		valid_variant_design = (
			variant_count == 2
			and experiment_keys == {"A", "B"}
			and np.isclose(allocation_probability_sum, 1.0)
		)
		if not valid_variant_design:
			add_issue(
				"invalid_variant_design",
				"Experiment",
				str(experiment_id),
				"Experiment must have one A and one B variant with probabilities totaling 1.",
			)
		record_check(f"{experiment_id}_variant_design", valid_variant_design, 2)

	bad_variant_parents = assignments.loc[
		assignments["experiment_id"]
		!= assignments["variant_id"].map(variants_by_id["experiment_id"])
	]
	for row in bad_variant_parents.itertuples(index=False):
		add_issue(
			"variant_experiment_mismatch",
			"Assignment",
			row.assignment_id,
			"Assigned variant belongs to a different experiment.",
		)
	declared_probability = assignments["variant_id"].map(
		variants_by_id["allocation_probability"]
	)
	probability_mismatch = ~np.isclose(
		assignments["allocation_probability"].astype(float),
		declared_probability.astype(float),
	)
	for row in assignments.loc[probability_mismatch].itertuples(index=False):
		add_issue(
			"assignment_probability_mismatch",
			"Assignment",
			row.assignment_id,
			"Recorded allocation probability differs from the assigned variant definition.",
		)
	record_check(
			"assignment_probabilities_match_variants",
		not bool(probability_mismatch.any()),
		len(assignments),
	)

	experiment_dates = experiments.copy()
	experiment_dates["planned_start_at"] = pd.to_datetime(
		experiment_dates["planned_start_at"], utc=True, errors="coerce"
	)
	experiment_dates["planned_end_at"] = pd.to_datetime(
		experiment_dates["planned_end_at"], utc=True, errors="coerce"
	)
	experiment_dates["created_at"] = pd.to_datetime(
		experiment_dates["created_at"], utc=True, errors="coerce"
	)
	bad_experiment_dates = (experiment_dates["planned_start_at"] >= experiment_dates["planned_end_at"]) | (
		experiment_dates["created_at"] > experiment_dates["planned_start_at"]
	)
	for experiment_id in experiment_dates.index[bad_experiment_dates]:
		add_issue(
			"date_ordering_violation",
			"Experiment",
			str(experiment_id),
			"Experiment creation/start/end dates are not in the required order.",
		)

	assignment_times = pd.to_datetime(assignments["assigned_at"], utc=True, errors="coerce")
	assignment_starts = assignments["experiment_id"].map(
		experiment_dates["planned_start_at"]
	)
	assignment_ends = assignments["experiment_id"].map(experiment_dates["planned_end_at"])
	bad_assignment_dates = (assignment_times < assignment_starts) | (
		assignment_times > assignment_ends
	)
	for row in assignments.loc[bad_assignment_dates].itertuples(index=False):
		add_issue(
			"date_ordering_violation",
			"Assignment",
			row.assignment_id,
			"Assignment falls outside the experiment's planned window.",
		)

	assignment_eligibility = assignments.merge(
		eligibility[["experiment_id", "user_id", "evaluated_at"]],
		on=["experiment_id", "user_id"],
		how="left",
	)
	assigned_at = pd.to_datetime(assignment_eligibility["assigned_at"], utc=True)
	evaluated_at = pd.to_datetime(
		assignment_eligibility["evaluated_at"], utc=True, errors="coerce"
	)
	assigned_before_eligibility = assigned_at < evaluated_at
	for row in assignment_eligibility.loc[assigned_before_eligibility].itertuples(index=False):
		add_issue(
			"assignment_before_eligibility",
			"Assignment",
			row.assignment_id,
			"Assignment time precedes the eligibility evaluation.",
		)
	record_check(
			"assignment_after_eligibility",
			not bool(assigned_before_eligibility.any())
			and bool(assignment_eligibility["evaluated_at"].notna().all()),
			len(assignment_eligibility),
	)

	eligible_rows = eligibility.loc[eligibility["eligible"]]
	eligibility_keys = set(
		zip(eligible_rows["experiment_id"].astype(str), eligible_rows["user_id"].astype(str))
	)
	assigned_pair_counts = assignments.groupby(["experiment_id", "user_id"]).size()
	missing_eligible_pairs = [
		pair for pair in eligibility_keys if pair not in assigned_pair_counts.index
	]
	for experiment_id, user_id in missing_eligible_pairs:
		add_issue(
			"eligible_user_not_assigned",
			"ExperimentAudience",
			f"{experiment_id}|{user_id}",
			"Eligible experiment-user pair has no assignment.",
		)
	record_check(
			"all_eligible_pairs_assigned",
		not missing_eligible_pairs,
		len(eligible_rows),
	)
	invalid_assignments = assignments.loc[
		[
			(str(row.experiment_id), str(row.user_id)) not in eligibility_keys
			for row in assignments.itertuples(index=False)
		]
	]
	for row in invalid_assignments.itertuples(index=False):
		add_issue(
			"ineligible_assignment",
			"Assignment",
			row.assignment_id,
			"Assignment does not reference an eligible experiment-user pair.",
		)

	duplicate_pairs = assignments.duplicated(["experiment_id", "user_id"], keep=False)
	for row in assignments.loc[duplicate_pairs].itertuples(index=False):
		add_issue(
			"multiple_variant_assignment",
			"Assignment",
			row.assignment_id,
			"User has more than one assignment for the same experiment.",
		)

	assignment_lookup = assignments.set_index("assignment_id")
	missing_telemetry = exposures["telemetry_status"] == "missing"
	blank_exposure_time = exposures["exposed_at"].isna() | exposures["exposed_at"].astype(str).eq("")
	blank_received_variant = (
		exposures["received_variant_id"].isna()
		| exposures["received_variant_id"].astype(str).eq("")
	)
	telemetry_consistent = (
		(missing_telemetry & blank_exposure_time & blank_received_variant)
		| (~missing_telemetry & ~blank_exposure_time & ~blank_received_variant)
	)
	for row in exposures.loc[~telemetry_consistent].itertuples(index=False):
		add_issue(
			"telemetry_status_inconsistent",
			"ExposureEvent",
			row.exposure_id,
			"Telemetry status conflicts with exposure time or received-variant fields.",
		)
	record_check(
			"exposure_telemetry_fields_consistent",
			bool(telemetry_consistent.all()),
			len(exposures),
	)

	exposure_lookup = exposures.copy()
	exposure_lookup["assigned_at"] = exposure_lookup["assignment_id"].map(
		assignment_lookup["assigned_at"]
	)
	exposure_lookup["exposed_at_parsed"] = pd.to_datetime(
		exposure_lookup["exposed_at"].replace("", pd.NA), utc=True, errors="coerce"
	)
	exposure_lookup["assigned_at_parsed"] = pd.to_datetime(
		exposure_lookup["assigned_at"], utc=True, errors="coerce"
	)
	early_exposures = exposure_lookup.loc[
		exposure_lookup["exposed_at_parsed"] < exposure_lookup["assigned_at_parsed"]
	]
	for row in early_exposures.itertuples(index=False):
		add_issue(
			"exposure_before_assignment",
			"ExposureEvent",
			row.exposure_id,
			"Observed exposure time precedes assignment time.",
		)

	assignment_experiment = assignments.set_index("assignment_id")["experiment_id"]
	received_experiment = exposures["received_variant_id"].map(
		variants_by_id["experiment_id"]
	)
	exposure_assignment_experiment = exposures["assignment_id"].map(assignment_experiment)
	mismatched_received_variant = exposures["received_variant_id"].notna() & (
		exposures["received_variant_id"].astype(str) != ""
	) & (received_experiment != exposure_assignment_experiment)
	for row in exposures.loc[mismatched_received_variant].itertuples(index=False):
		add_issue(
			"exposure_variant_experiment_mismatch",
			"ExposureEvent",
			row.exposure_id,
			"Received variant belongs to a different experiment than its assignment.",
		)

	conversion_lookup = conversions.copy()
	conversion_lookup["assigned_at"] = conversion_lookup["assignment_id"].map(
		assignment_lookup["assigned_at"]
	)
	conversion_lookup["experiment_id"] = conversion_lookup["assignment_id"].map(
		assignment_experiment
	)
	conversion_lookup["experiment_window_days"] = conversion_lookup["experiment_id"].map(
		experiments["outcome_window_days"]
	)
	conversion_lookup["converted_at_parsed"] = pd.to_datetime(
		conversion_lookup["converted_at"],
		format="mixed",
		utc=True,
		errors="coerce",
	)
	conversion_lookup["assigned_at_parsed"] = pd.to_datetime(
		conversion_lookup["assigned_at"], utc=True, errors="coerce"
	)
	for row in conversion_lookup.itertuples(index=False):
		if row.outcome_window_days != row.experiment_window_days:
			add_issue(
				"outcome_window_inconsistent",
				"ConversionEvent",
				row.conversion_id,
				"Event-declared window differs from the predeclared experiment window.",
			)
		if row.converted_at_parsed < row.assigned_at_parsed:
			add_issue(
				"conversion_before_assignment",
				"ConversionEvent",
				row.conversion_id,
				"Conversion time precedes assignment time.",
			)

	summary_rows = []
	for experiment_id, experiment in experiments.iterrows():
		experiment_assignments = assignments.loc[
			assignments["experiment_id"] == experiment_id
		]
		experiment_variants = variants.loc[variants["experiment_id"] == experiment_id]
		observed_counts = experiment_assignments["variant_id"].value_counts()
		expected_counts = np.array(
			[
				len(experiment_assignments)
				* float(variant.allocation_probability)
				for variant in experiment_variants.itertuples(index=False)
			],
			dtype=float,
		)
		observed = np.array(
			[int(observed_counts.get(variant_id, 0)) for variant_id in experiment_variants["variant_id"]],
			dtype=float,
		)
		if len(observed) and expected_counts.sum() and len(experiment_assignments):
			srm_p_value = float(stats.chisquare(observed, f_exp=expected_counts).pvalue)
		else:
			srm_p_value = 0.0
		record_check(
			f"{experiment_id}_sample_ratio_check",
			srm_p_value >= 0.001,
			len(experiment_assignments),
		)
		if srm_p_value < 0.001:
			add_issue(
				"sample_ratio_mismatch_ignored",
				"Experiment",
				str(experiment_id),
				f"Observed assignment counts {observed.tolist()} differ from the declared allocation.",
			)

		duplicate_count = int(
			experiment_assignments.duplicated(["experiment_id", "user_id"], keep=False).sum()
		)
		assignment_integrity_valid = bool(
			duplicate_count == 0
			and not bool((bad_variant_parents["experiment_id"] == experiment_id).any())
			and not bool((invalid_assignments["experiment_id"] == experiment_id).any())
		)
		invalid = srm_p_value < 0.001 or not assignment_integrity_valid
		control_n = int(
			experiment_assignments["variant_id"].map(variants_by_id["variant_key"]).eq("A").sum()
		)
		treatment_n = int(
			experiment_assignments["variant_id"].map(variants_by_id["variant_key"]).eq("B").sum()
		)
		summary_rows.append(
			{
				"experiment_id": experiment_id,
				"eligible_n": int(
					eligibility.loc[
						eligibility["experiment_id"] == experiment_id, "eligible"
					].sum()
				),
				"assigned_n": int(len(experiment_assignments)),
				"control_n": control_n,
				"treatment_n": treatment_n,
				"sample_ratio_p_value": srm_p_value,
				"duplicate_assignment_count": duplicate_count,
				"assignment_integrity_valid": assignment_integrity_valid,
				"assignment_valid": not invalid,
				"outcome_window_days": int(experiment["outcome_window_days"]),
			}
		)

	if not results.empty:
		expected_counts = assignments.assign(
			variant_key=assignments["variant_id"].map(variants_by_id["variant_key"])
		).groupby(["experiment_id", "variant_key"]).size()
		for row in results.itertuples(index=False):
			if expected_counts.get((row.experiment_id, "A"), 0) != row.control_n or expected_counts.get(
				(row.experiment_id, "B"), 0
			) != row.treatment_n:
				add_issue(
					"result_count_reconciliation_failed",
					"ExperimentResult",
					row.result_id,
					"Reported arm sample sizes do not reconcile to assignment rows.",
				)
			if pd.notna(row.p_value) and not 0 <= row.p_value <= 1:
				add_issue(
					"invalid_p_value",
					"ExperimentResult",
					row.result_id,
					"p_value must be within [0, 1].",
				)
			if pd.notna(row.ci_lower) and not row.ci_lower <= row.estimate <= row.ci_upper:
				add_issue(
					"invalid_confidence_interval",
					"ExperimentResult",
					row.result_id,
					"Confidence interval must contain the point estimate.",
				)
			metric = metric_definitions.loc[
				metric_definitions["metric_definition_id"] == row.metric_definition_id
			].iloc[0]
			analyzed_at = pd.Timestamp(row.analyzed_at)
			effective_from = pd.Timestamp(metric["effective_from"])
			effective_to = metric["effective_to"]
			if analyzed_at < effective_from or (
				pd.notna(effective_to)
				and str(effective_to) != ""
				and analyzed_at >= pd.Timestamp(effective_to)
			):
				add_issue(
					"metric_definition_not_effective",
					"ExperimentResult",
				row.result_id,
				"Referenced metric definition is not effective at analysis time.",
				)

	change_events = tables.get("metric_definition_change_events", pd.DataFrame())
	definitions_by_id = metric_definitions.set_index("metric_definition_id")
	change_events_reconcile = not change_events.empty
	for event in change_events.itertuples(index=False):
		event_id = str(event.metric_definition_change_event_id)
		old_id = str(event.old_metric_definition_id)
		new_id = str(event.new_metric_definition_id)
		changed_at = pd.to_datetime(event.changed_at, utc=True, errors="coerce")
		event_valid = (
			old_id != new_id
			and old_id in definitions_by_id.index
			and new_id in definitions_by_id.index
			and pd.notna(changed_at)
			and bool(str(event.reason).strip())
		)
		if old_id in definitions_by_id.index and new_id in definitions_by_id.index:
			old_definition = definitions_by_id.loc[old_id]
			new_definition = definitions_by_id.loc[new_id]
			old_end = pd.to_datetime(
				old_definition["effective_to"], utc=True, errors="coerce"
			)
			new_start = pd.to_datetime(
				new_definition["effective_from"], utc=True, errors="coerce"
			)
			old_version = pd.to_numeric(old_definition["version"], errors="coerce")
			new_version = pd.to_numeric(new_definition["version"], errors="coerce")
			event_valid = bool(
				event_valid
				and old_definition["metric_name"] == new_definition["metric_name"]
				and pd.notna(old_version)
				and pd.notna(new_version)
				and new_version == old_version + 1
				and pd.notna(old_end)
				and pd.notna(new_start)
				and old_end == changed_at
				and new_start == changed_at
			)

		if not results.empty and pd.notna(changed_at) and old_id in definitions_by_id.index:
			old_results = results.loc[results["metric_definition_id"] == old_id]
			result_times = pd.to_datetime(
				old_results["analyzed_at"], utc=True, errors="coerce"
			)
			prior_results = old_results.loc[result_times < changed_at]
			later_results = old_results.loc[result_times >= changed_at]
			has_prior_result = not prior_results.empty
			event_valid = bool(event_valid and has_prior_result and later_results.empty)
			if has_prior_result:
				metric_name = str(definitions_by_id.loc[old_id, "metric_name"])
				details = (
					f"{metric_name} changed from {old_id} to {new_id} at "
					f"{changed_at.isoformat()} after prior results; "
					f"reason: {event.reason}"
				)
				add_issue(
					"metric_definition_changed_after_result",
					"MetricDefinitionChangeEvent",
					event_id,
					details,
				)

		if not event_valid:
			change_events_reconcile = False
			add_issue(
				"invalid_metric_definition_change_event",
				"MetricDefinitionChangeEvent",
				event_id,
				"Change event must reference consecutive versions of the same metric, "
				"match both effective dates, and follow all results using the old definition.",
			)
	if not results.empty:
		record_check(
			"metric_definition_change_events_reconcile",
			change_events_reconcile,
			len(change_events),
		)

	ground_truth = tables.get("ground_truth", pd.DataFrame())
	if not ground_truth.empty:
		expected_metrics = ground_truth.loc[
			ground_truth["issue_type"] == "expected_metric_effect"
		]
		effects_reconcile = np.isclose(
			expected_metrics["expected_treatment"].astype(float)
			- expected_metrics["expected_control"].astype(float),
			expected_metrics["expected_effect"].astype(float),
		).all()
		if not effects_reconcile:
			for row in expected_metrics.itertuples(index=False):
				if not np.isclose(
					row.expected_treatment - row.expected_control,
					row.expected_effect,
				):
					add_issue(
						"ground_truth_effect_reconciliation_failed",
						"GroundTruth",
						row.ground_truth_id,
						"Expected effect does not equal treatment expectation minus control expectation.",
					)
		record_check(
			"ground_truth_effects_reconcile",
			bool(effects_reconcile),
			len(expected_metrics),
		)
		change_truth = ground_truth.loc[
			ground_truth["issue_type"] == "metric_definition_changed_after_result"
		]
		expected_change_ids = {
			str(issue["entity_id"])
			for issue in issues
			if issue["issue_type"] == "metric_definition_changed_after_result"
		}
		matching_change_truth = True
		change_events_by_id = change_events.set_index(
			"metric_definition_change_event_id"
		)
		for row in change_truth.itertuples(index=False):
			event_id = str(row.related_event_id)
			if event_id not in change_events_by_id.index:
				matching_change_truth = False
				continue
			event = change_events_by_id.loc[event_id]
			matching_change_truth = bool(
				matching_change_truth
				and row.old_metric_definition_id == event["old_metric_definition_id"]
				and row.new_metric_definition_id == event["new_metric_definition_id"]
				and row.metric_definition_id == event["old_metric_definition_id"]
				and pd.to_datetime(row.event_timestamp, utc=True)
				== pd.to_datetime(event["changed_at"], utc=True)
				and row.event_reason == event["reason"]
			)
		matching_change_truth = bool(
			matching_change_truth
			and set(change_truth["related_event_id"].astype(str)) == expected_change_ids
		)
		record_check(
			"ground_truth_metric_definition_change_events_reconcile",
			matching_change_truth,
			len(change_truth),
		)

	for event_table, entity_name, parent_table, parent_column in [
		("experiment_state_events", "ExperimentStateEvent", "experiments", "experiment_id"),
		("variant_state_events", "VariantStateEvent", "variants", "variant_id"),
	]:
		state_events = tables.get(event_table, pd.DataFrame())
		entity_ids = set(tables[parent_table][parent_column].astype(str))
		event_parent_ids = (
			set(state_events[parent_column].astype(str))
			if not state_events.empty
			else set()
		)
		missing_history = entity_ids - event_parent_ids
		for parent_id in missing_history:
			add_issue(
				"lifecycle_history_missing",
				entity_name,
				parent_id,
				"Entity has no lifecycle history event.",
			)
		record_check(
			f"{event_table}_history_present",
			not missing_history,
			len(entity_ids),
		)
		allowed_transitions = {
			"experiment_state_events": {
				"draft": {"designed"},
				"designed": {"running"},
				"running": {"completed"},
				"completed": {"analyzed"},
				"analyzed": {"archived"},
			},
			"variant_state_events": {
				"planned": {"active", "retired"},
				"active": {"paused", "retired"},
				"paused": {"active", "retired"},
			},
		}[event_table]
		if state_events.empty:
			continue
		state_events = state_events.sort_values("changed_at")
		for parent_id, group in state_events.groupby(parent_column, sort=False):
			previous_status = ""
			previous_time = None
			for event in group.itertuples(index=False):
				if previous_status == "":
					if event_table == "experiment_state_events":
						valid_transition = (
							event.from_status == "draft" and event.to_status == "designed"
						)
					else:
						valid_transition = (
							event.from_status in ("", None) and event.to_status == "planned"
						)
				else:
					valid_transition = (
						event.from_status == previous_status
						and event.to_status in allowed_transitions.get(previous_status, set())
					)
				if not valid_transition:
					add_issue(
						"invalid_lifecycle_transition",
						entity_name,
						event.state_event_id,
						"State event is not a valid forward transition from the prior state.",
					)
				event_time = pd.Timestamp(event.changed_at)
				if previous_time is not None and event_time <= previous_time:
					add_issue(
						"invalid_lifecycle_timestamp",
						entity_name,
						event.state_event_id,
						"Lifecycle timestamps must increase strictly.",
					)
				previous_status = event.to_status
				previous_time = event_time
			if str(tables[parent_table].set_index(parent_column).loc[parent_id, "status"]) != previous_status:
				add_issue(
					"lifecycle_state_mismatch",
					entity_name,
					str(parent_id),
					"Current entity status differs from the final lifecycle event.",
				)

	issues_frame = pd.DataFrame(
		issues,
		columns=["issue_type", "entity_type", "entity_id", "severity", "details"],
	)
	checks_frame = pd.DataFrame(
		check_rows, columns=["check_name", "passed", "rows_checked"]
	)
	return {
		"summary": pd.DataFrame(summary_rows),
		"issues": issues_frame,
		"checks": checks_frame,
	}
