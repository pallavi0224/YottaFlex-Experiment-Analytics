"""Write traceable CSV, JSON, SQLite, and SQL exports."""

import hashlib
import json
import os
import sqlite3
from pathlib import Path
from typing import Any

import pandas as pd

from config import OUTPUT_DIR, SEED


TABLE_SCHEMA = {
	"metric_definitions": """
		CREATE TABLE metric_definitions (
			metric_definition_id TEXT PRIMARY KEY,
			metric_name TEXT NOT NULL,
			version INTEGER NOT NULL,
			description TEXT NOT NULL,
			numerator TEXT NOT NULL,
			denominator TEXT,
			unit TEXT NOT NULL,
			analysis_unit TEXT NOT NULL,
			effective_from TEXT NOT NULL,
			effective_to TEXT,
			UNIQUE (metric_name, version)
		)
	""",
	"metric_definition_change_events": """
		CREATE TABLE metric_definition_change_events (
			metric_definition_change_event_id TEXT PRIMARY KEY,
			old_metric_definition_id TEXT NOT NULL,
			new_metric_definition_id TEXT NOT NULL,
			changed_at TEXT NOT NULL,
			reason TEXT NOT NULL,
			CHECK (old_metric_definition_id <> new_metric_definition_id),
			FOREIGN KEY (old_metric_definition_id)
				REFERENCES metric_definitions(metric_definition_id),
			FOREIGN KEY (new_metric_definition_id)
				REFERENCES metric_definitions(metric_definition_id)
		)
	""",
	"experiments": """
		CREATE TABLE experiments (
			experiment_id TEXT PRIMARY KEY,
			name TEXT NOT NULL,
			hypothesis TEXT NOT NULL,
			primary_metric_definition_id TEXT NOT NULL,
			analysis_plan TEXT NOT NULL,
			outcome_window_days INTEGER NOT NULL,
			random_seed INTEGER NOT NULL,
			planned_start_at TEXT NOT NULL,
			planned_end_at TEXT NOT NULL,
			status TEXT NOT NULL,
			created_at TEXT NOT NULL,
			FOREIGN KEY (primary_metric_definition_id)
				REFERENCES metric_definitions(metric_definition_id)
		)
	""",
	"variants": """
		CREATE TABLE variants (
			variant_id TEXT PRIMARY KEY,
			experiment_id TEXT NOT NULL,
			variant_key TEXT NOT NULL,
			name TEXT NOT NULL,
			allocation_probability REAL NOT NULL,
			treatment_parameters_json TEXT NOT NULL,
			effective_from TEXT NOT NULL,
			effective_to TEXT,
			status TEXT NOT NULL,
			UNIQUE (experiment_id, variant_id),
			UNIQUE (experiment_id, variant_key),
			FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
		)
	""",
	"audience_members": """
		CREATE TABLE audience_members (
			user_id TEXT PRIMARY KEY,
			region TEXT NOT NULL,
			device_type TEXT NOT NULL,
			tenure_days INTEGER NOT NULL,
			created_at TEXT NOT NULL
		)
	""",
	"experiment_audience": """
		CREATE TABLE experiment_audience (
			experiment_id TEXT NOT NULL,
			user_id TEXT NOT NULL,
			eligible INTEGER NOT NULL,
			eligibility_reason TEXT NOT NULL,
			evaluated_at TEXT NOT NULL,
			PRIMARY KEY (experiment_id, user_id),
			FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id),
			FOREIGN KEY (user_id) REFERENCES audience_members(user_id)
		)
	""",
	"assignments": """
		CREATE TABLE assignments (
			assignment_id TEXT PRIMARY KEY,
			experiment_id TEXT NOT NULL,
			user_id TEXT NOT NULL,
			variant_id TEXT NOT NULL,
			assigned_at TEXT NOT NULL,
			allocation_probability REAL NOT NULL,
			assignment_method TEXT NOT NULL,
			FOREIGN KEY (experiment_id, user_id)
				REFERENCES experiment_audience(experiment_id, user_id),
			FOREIGN KEY (experiment_id, variant_id)
				REFERENCES variants(experiment_id, variant_id)
		)
	""",
	"exposure_events": """
		CREATE TABLE exposure_events (
			exposure_id TEXT PRIMARY KEY,
			assignment_id TEXT NOT NULL,
			received_variant_id TEXT,
			telemetry_status TEXT NOT NULL,
			exposed_at TEXT,
			surface TEXT NOT NULL,
			created_at TEXT NOT NULL,
			FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id),
			FOREIGN KEY (received_variant_id) REFERENCES variants(variant_id)
		)
	""",
	"conversion_events": """
		CREATE TABLE conversion_events (
			conversion_id TEXT PRIMARY KEY,
			assignment_id TEXT NOT NULL,
			converted_at TEXT NOT NULL,
			outcome_window_days INTEGER NOT NULL,
			conversion_value REAL NOT NULL,
			currency TEXT NOT NULL,
			source TEXT NOT NULL,
			is_refunded INTEGER NOT NULL,
			FOREIGN KEY (assignment_id) REFERENCES assignments(assignment_id)
		)
	""",
	"guardrail_metrics": """
		CREATE TABLE guardrail_metrics (
			experiment_id TEXT NOT NULL,
			metric_definition_id TEXT NOT NULL,
			comparison TEXT NOT NULL,
			threshold REAL NOT NULL,
			alpha REAL NOT NULL,
			effective_from TEXT NOT NULL,
			effective_to TEXT,
			PRIMARY KEY (experiment_id, metric_definition_id),
			FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id),
			FOREIGN KEY (metric_definition_id)
				REFERENCES metric_definitions(metric_definition_id)
		)
	""",
	"experiment_results": """
		CREATE TABLE experiment_results (
			result_id TEXT PRIMARY KEY,
			experiment_id TEXT NOT NULL,
			metric_definition_id TEXT NOT NULL,
			analysis_run INTEGER NOT NULL,
			analysis_plan TEXT NOT NULL,
			control_n INTEGER NOT NULL,
			treatment_n INTEGER NOT NULL,
			estimate REAL NOT NULL,
			standard_error REAL NOT NULL,
			confidence_level REAL NOT NULL,
			ci_lower REAL NOT NULL,
			ci_upper REAL NOT NULL,
			p_value REAL,
			result_valid INTEGER NOT NULL,
			decision TEXT NOT NULL,
			analyzed_at TEXT NOT NULL,
			UNIQUE (experiment_id, metric_definition_id, analysis_run),
			FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id),
			FOREIGN KEY (metric_definition_id)
				REFERENCES metric_definitions(metric_definition_id)
		)
	""",
	"ground_truth": """
		CREATE TABLE ground_truth (
			ground_truth_id TEXT PRIMARY KEY NOT NULL,
			issue_type TEXT,
			entity_type TEXT,
			entity_id TEXT,
			expected_label TEXT,
			expected_decision TEXT,
			metric_name TEXT,
			metric_definition_id TEXT,
			related_event_id TEXT,
			old_metric_definition_id TEXT,
			new_metric_definition_id TEXT,
			event_timestamp TEXT,
			event_reason TEXT,
			expected_control REAL,
			expected_treatment REAL,
			expected_effect REAL,
			reason TEXT
		)
	""",
	"experiment_state_events": """
		CREATE TABLE experiment_state_events (
			state_event_id TEXT PRIMARY KEY,
			experiment_id TEXT NOT NULL,
			from_status TEXT,
			to_status TEXT NOT NULL,
			changed_at TEXT NOT NULL,
			reason TEXT NOT NULL,
			FOREIGN KEY (experiment_id) REFERENCES experiments(experiment_id)
		)
	""",
	"variant_state_events": """
		CREATE TABLE variant_state_events (
			state_event_id TEXT PRIMARY KEY,
			variant_id TEXT NOT NULL,
			from_status TEXT,
			to_status TEXT NOT NULL,
			changed_at TEXT NOT NULL,
			reason TEXT NOT NULL,
			FOREIGN KEY (variant_id) REFERENCES variants(variant_id)
		)
	""",
}


def _json_value(value: Any) -> Any:
	"""Convert pandas/numpy values to JSON-compatible Python values."""
	if pd.isna(value):
		return None
	if hasattr(value, "item"):
		return value.item()
	return value


def export_outputs(
	tables: dict[str, pd.DataFrame],
	validation: dict[str, pd.DataFrame],
	output_dir: Path = OUTPUT_DIR,
	seed: int = SEED,
) -> dict[str, Path]:
	"""Export all source and derived tables, with ground truth kept separate."""
	output_dir.mkdir(parents=True, exist_ok=True)
	all_tables = dict(tables)
	all_tables["validation_summary"] = validation["summary"]
	all_tables["validation_issues"] = validation["issues"]
	all_tables["validation_checks"] = validation["checks"]
	paths: dict[str, Path] = {}
	checksums: dict[str, str] = {}

	for table_name, frame in all_tables.items():
		csv_path = output_dir / f"{table_name}.csv"
		json_path = output_dir / f"{table_name}.json"
		frame.to_csv(csv_path, index=False)
		json_records = [
			{key: _json_value(value) for key, value in row.items()}
			for row in frame.to_dict(orient="records")
		]
		json_path.write_text(json.dumps(json_records, indent=2, allow_nan=False) + "\n", encoding="utf-8")
		csv_digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
		checksums[csv_path.name] = csv_digest
		paths[table_name] = csv_path
		paths[f"{table_name}_json"] = json_path

	database_path = output_dir / "experiment_analytics.sqlite"
	building_database_path = output_dir / "experiment_analytics.building.sqlite"
	if building_database_path.exists():
		building_database_path.unlink()
	connection = sqlite3.connect(building_database_path)
	try:
		connection.execute("PRAGMA foreign_keys = ON")
		for schema_sql in TABLE_SCHEMA.values():
			connection.execute(schema_sql)
		for table_name in TABLE_SCHEMA:
			if table_name in all_tables:
				sql_frame = all_tables[table_name].copy().replace({"": None})
				sql_frame.to_sql(table_name, connection, if_exists="append", index=False)
		for table_name, frame in all_tables.items():
			if table_name not in TABLE_SCHEMA:
				frame.to_sql(table_name, connection, if_exists="replace", index=False)
		violations = connection.execute("PRAGMA foreign_key_check").fetchall()
		if violations:
			raise ValueError(f"SQLite foreign-key validation failed: {violations[:5]}")
		connection.commit()
		sql_dump_path = output_dir / "seed_data.sql"
		sql_dump_path.write_text("\n".join(connection.iterdump()) + "\n", encoding="utf-8")
	finally:
		connection.close()
	os.replace(building_database_path, database_path)

	manifest = {
		"project": "Experiment Analytics Platform",
		"seed": seed,
		"experiment_count": int(len(tables["experiments"])),
		"eligible_user_count": int(len(tables["audience_members"])),
		"analysis_plan": "ITT",
		"generator_command": ".\\.venv\\Scripts\\python.exe main.py --scale 1.0 --seed 20261022",
		"row_counts": {name: int(len(frame)) for name, frame in all_tables.items()},
		"csv_sha256": checksums,
		"ground_truth_separate_from_analysis_inputs": True,
	}
	manifest_path = output_dir / "source_manifest.json"
	manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
	paths["sqlite"] = database_path
	paths["sql_dump"] = sql_dump_path
	paths["manifest"] = manifest_path
	return paths
