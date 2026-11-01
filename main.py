"""Run the end-to-end synthetic experiment analytics workflow."""

import argparse
import gc
import hashlib
import json
from pathlib import Path

import pandas as pd

from anomalies import detect_anomalies
from assignment import generate_assignments
from config import DEFAULT_SCALE, OUTPUT_DIR, SEED
from data_generation import generate_master_data
from export import export_outputs
from ground_truth import generate_ground_truth
from metrics import calculate_results
from simulation import simulate_events
from validation import validate_dataset


def _advance_lifecycle(
	tables: dict[str, pd.DataFrame],
	entity_kind: str,
	target_status: str,
	changed_at_by_id: dict[str, str],
	reason: str,
) -> None:
	"""Append valid state-change events and update each current-state snapshot."""
	if entity_kind == "experiment":
		entities = tables["experiments"]
		state_events = tables["experiment_state_events"]
		id_column = "experiment_id"
		event_table = "experiment_state_events"
		transitions = {
			"designed": {"running"},
			"running": {"completed"},
			"completed": {"analyzed"},
		}
	else:
		entities = tables["variants"]
		state_events = tables["variant_state_events"]
		id_column = "variant_id"
		event_table = "variant_state_events"
		transitions = {"planned": {"active"}, "active": {"retired"}}

	new_events = []
	for index, entity in entities.iterrows():
		entity_id = str(entity[id_column])
		from_status = str(entity["status"])
		if target_status not in transitions.get(from_status, set()):
			continue
		changed_at = changed_at_by_id[entity_id]
		event_count = int(
			(state_events[id_column].astype(str) == entity_id).sum()
		) + 1
		if entity_kind == "experiment":
			event_id = f"EXPSTATE-{entity_id}-{event_count:03d}"
			event = {
				"state_event_id": event_id,
				"experiment_id": entity_id,
				"from_status": from_status,
				"to_status": target_status,
				"changed_at": changed_at,
				"reason": reason,
			}
		else:
			event_id = f"VARSTATE-{entity['experiment_id']}-{entity['variant_key']}-{event_count:03d}"
			event = {
				"state_event_id": event_id,
				"variant_id": entity_id,
				"from_status": from_status,
				"to_status": target_status,
				"changed_at": changed_at,
				"reason": reason,
			}
		new_events.append(event)
		entities.loc[index, "status"] = target_status
		if entity_kind == "variant" and target_status == "retired":
			entities.loc[index, "effective_to"] = changed_at

	if new_events:
		tables[event_table] = pd.concat(
			[state_events, pd.DataFrame(new_events)], ignore_index=True
		)
	if entity_kind == "experiment":
		tables["experiments"] = entities
	else:
		tables["variants"] = entities


def build_dataset(scale: float, seed: int) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
	"""Generate and analyze all tables without mixing in evaluation labels."""
	tables = generate_master_data(scale=scale, seed=seed)
	start_times = tables["experiments"].set_index("experiment_id")[
		"planned_start_at"
	].to_dict()
	variant_start_times = tables["variants"].set_index("variant_id")[
		"effective_from"
	].to_dict()
	_advance_lifecycle(
		tables,
		"experiment",
		"running",
		start_times,
		"Experiment enrollment and assignment started.",
	)
	_advance_lifecycle(
		tables,
		"variant",
		"active",
		variant_start_times,
		"Variant activated for randomized assignment.",
	)
	assignments = generate_assignments(tables, seed=seed)
	events = simulate_events(tables, assignments, seed=seed)
	tables["assignments"] = assignments
	tables.update(events)
	completed_times = (
		tables["experiments"].set_index("experiment_id")["planned_end_at"]
		.pipe(pd.to_datetime, utc=True)
		.add(pd.to_timedelta(tables["experiments"].set_index("experiment_id")["outcome_window_days"], unit="D"))
		.map(lambda value: value.isoformat())
		.to_dict()
	)
	_advance_lifecycle(
		tables,
		"experiment",
		"completed",
		completed_times,
		"Experiment and all predeclared outcome windows completed.",
	)

	pre_analysis_validation = validate_dataset(tables)
	results = calculate_results(
		tables,
		assignments,
		tables["conversion_events"],
		pre_analysis_validation["summary"],
	)
	tables["experiment_results"] = results
	analyzed_times = {
		experiment_id: (pd.Timestamp(completed_at) + pd.Timedelta(seconds=1)).isoformat()
		for experiment_id, completed_at in completed_times.items()
	}
	_advance_lifecycle(
		tables,
		"experiment",
		"analyzed",
		analyzed_times,
		"Predeclared intent-to-treat analysis completed.",
	)
	_advance_lifecycle(
		tables,
		"variant",
		"retired",
		{variant_id: analyzed_times[experiment_id] for variant_id, experiment_id in zip(
			tables["variants"]["variant_id"], tables["variants"]["experiment_id"]
		)},
		"Experiment analysis completed; variant retired.",
	)
	analysis_validation = validate_dataset(tables)
	anomalies = detect_anomalies(analysis_validation["issues"], results, tables)
	tables["anomalies"] = anomalies
	tables["ground_truth"] = generate_ground_truth(tables, anomalies)
	validation = validate_dataset(tables)
	return tables, validation


def dataset_fingerprint(tables: dict[str, pd.DataFrame]) -> dict[str, dict[str, object]]:
	"""Return deterministic row counts and CSV-content checksums per table."""
	fingerprints = {}
	for name in sorted(tables):
		csv_bytes = tables[name].to_csv(index=False, lineterminator="\n").encode("utf-8")
		fingerprints[name] = {
			"row_count": int(len(tables[name])),
			"sha256": hashlib.sha256(csv_bytes).hexdigest(),
		}
	return fingerprints


def run_pipeline(
	scale: float = DEFAULT_SCALE,
	seed: int = SEED,
	output_dir: Path = OUTPUT_DIR,
	verify_reproducibility: bool = False,
) -> dict[str, object]:
	"""Generate, validate, analyze, and export the complete project dataset."""
	tables, validation = build_dataset(scale=scale, seed=seed)
	fingerprints = dataset_fingerprint(tables)
	issue_count = int(len(validation["issues"]))
	outputs = export_outputs(tables, validation, output_dir=output_dir, seed=seed)

	if verify_reproducibility:
		del tables, validation
		gc.collect()
		second_tables, _ = build_dataset(scale=scale, seed=seed)
		second_fingerprints = dataset_fingerprint(second_tables)
		if fingerprints != second_fingerprints:
			raise RuntimeError("Reproducibility check failed: generated fingerprints differ.")
		del second_tables
		gc.collect()

	summary = {
		"seed": seed,
		"scale": scale,
		"experiment_count": int(fingerprints["experiments"]["row_count"]),
		"eligible_user_count": int(fingerprints["audience_members"]["row_count"]),
		"assignment_count": int(fingerprints["assignments"]["row_count"]),
		"conversion_count": int(fingerprints["conversion_events"]["row_count"]),
		"issue_count": issue_count,
		"ground_truth_count": int(fingerprints["ground_truth"]["row_count"]),
		"outputs": {name: str(path) for name, path in outputs.items()},
		"fingerprints": fingerprints,
		"reproducibility_verified": verify_reproducibility,
	}
	summary_path = output_dir / "run_summary.json"
	summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
	return summary


def parse_args() -> argparse.Namespace:
	"""Parse command-line options for a starter or full run."""
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument("--scale", type=float, default=DEFAULT_SCALE)
	parser.add_argument("--seed", type=int, default=SEED)
	parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
	parser.add_argument("--verify-reproducibility", action="store_true")
	return parser.parse_args()


if __name__ == "__main__":
	arguments = parse_args()
	result = run_pipeline(
		scale=arguments.scale,
		seed=arguments.seed,
		output_dir=arguments.output_dir,
		verify_reproducibility=arguments.verify_reproducibility,
	)
	print(json.dumps(result, indent=2))
