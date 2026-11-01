"""Small, repeatable checks for generation and required exception cases."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from anomalies import detect_anomalies
from assignment import generate_assignments
from config import SEED
from data_generation import generate_master_data
from export import export_outputs
from ground_truth import generate_ground_truth
from main import build_dataset, dataset_fingerprint
from metrics import calculate_results
from simulation import simulate_events
from validation import validate_dataset


class ExperimentPipelineTests(unittest.TestCase):
	@classmethod
	def setUpClass(cls) -> None:
		cls.tables, cls.validation = build_dataset(scale=0.1, seed=SEED)
		cls.master_data = {
			name: cls.tables[name]
			for name in [
				"experiments",
				"variants",
				"audience_members",
				"experiment_audience",
				"metric_definitions",
				"guardrail_metrics",
			]
		}
		cls.assignments = cls.tables["assignments"]
		cls.events = {
			name: cls.tables[name]
			for name in ["exposure_events", "conversion_events"]
		}
		cls.results = cls.tables["experiment_results"]
		cls.anomalies = cls.tables["anomalies"]
		cls.ground_truth = cls.tables["ground_truth"]

	def test_scale_and_primary_keys(self) -> None:
		self.assertEqual(len(self.master_data["experiments"]), 10)
		self.assertEqual(len(self.master_data["audience_members"]), 5_000)
		self.assertTrue(self.master_data["experiments"]["experiment_id"].is_unique)
		self.assertTrue(self.assignments["assignment_id"].is_unique)
		self.assertEqual(
			len(self.assignments),
			len(self.master_data["experiment_audience"]) + 1,
		)
		self.assertTrue(self.tables["experiments"]["status"].eq("analyzed").all())
		self.assertTrue(self.tables["variants"]["status"].eq("retired").all())
		self.assertEqual(len(self.tables["experiment_state_events"]), 40)
		self.assertEqual(len(self.tables["variant_state_events"]), 60)

	def test_fixed_seed_recreates_master_data(self) -> None:
		original = generate_master_data(scale=0.1, seed=SEED)
		repeated = generate_master_data(scale=0.1, seed=SEED)
		for table_name, original_frame in original.items():
			pd.testing.assert_frame_equal(original_frame, repeated[table_name])

	def test_fixed_seed_recreates_full_dataset_fingerprints(self) -> None:
		repeated_tables, _ = build_dataset(scale=0.1, seed=SEED)
		self.assertEqual(
			dataset_fingerprint(self.tables),
			dataset_fingerprint(repeated_tables),
		)

	def test_sqlite_export_has_valid_foreign_keys(self) -> None:
		with tempfile.TemporaryDirectory() as directory:
			paths = export_outputs(
				self.tables,
				self.validation,
				output_dir=Path(directory),
				seed=SEED,
			)
			paths = export_outputs(
				self.tables,
				self.validation,
				output_dir=Path(directory),
				seed=SEED,
			)
			connection = sqlite3.connect(paths["sqlite"])
			try:
				self.assertEqual(
					connection.execute("PRAGMA foreign_key_check").fetchall(), []
				)
				ground_truth_schema = connection.execute(
					"PRAGMA table_info(ground_truth)"
				).fetchall()
				self.assertIn(
					"ground_truth_id",
					[row[1] for row in ground_truth_schema if row[5] == 1],
				)
				self.assertEqual(
					next(row[3] for row in ground_truth_schema if row[1] == "ground_truth_id"),
					1,
				)
				self.assertEqual(
					connection.execute("SELECT COUNT(*) FROM ground_truth").fetchone()[0],
					len(self.ground_truth),
				)
			finally:
				connection.close()
			self.assertTrue((Path(directory) / "ground_truth.csv").exists())
			sql_dump = Path(directory) / "seed_data.sql"
			self.assertTrue(sql_dump.exists())
			sql_connection = sqlite3.connect(":memory:")
			try:
				sql_connection.executescript(sql_dump.read_text(encoding="utf-8"))
				sql_ground_truth_schema = sql_connection.execute(
					"PRAGMA table_info(ground_truth)"
				).fetchall()
				self.assertIn(
					"ground_truth_id",
					[row[1] for row in sql_ground_truth_schema if row[5] == 1],
				)
				self.assertEqual(
					next(
						row[3]
						for row in sql_ground_truth_schema
						if row[1] == "ground_truth_id"
					),
					1,
				)
				self.assertEqual(
					sql_connection.execute(
						"SELECT COUNT(*) FROM ground_truth"
					).fetchone()[0],
					len(self.ground_truth),
				)
				self.assertEqual(
					{
						row[0]
						for row in sql_connection.execute(
							"SELECT ground_truth_id FROM ground_truth"
						)
					},
					set(self.ground_truth["ground_truth_id"]),
				)
			finally:
				sql_connection.close()

	def test_assignment_includes_documented_negative_cases(self) -> None:
		assignment_counts = self.assignments.groupby("experiment_id").size()
		self.assertEqual(int(assignment_counts.iloc[0]), 501)
		self.assertTrue(assignment_counts.iloc[1:].eq(500).all())
		duplicate_pairs = self.assignments.duplicated(
			["experiment_id", "user_id"], keep=False
		)
		self.assertEqual(int(duplicate_pairs.sum()), 2)
		self.assertTrue(self.assignments["assignment_id"].str.endswith("-DUP01").sum() == 1)

	def test_required_timing_issues_are_reported_and_labeled(self) -> None:
		issue_types = set(self.validation["issues"]["issue_type"])
		self.assertIn("exposure_before_assignment", issue_types)
		self.assertIn("outcome_window_inconsistent", issue_types)
		truth_types = set(self.ground_truth["issue_type"])
		self.assertIn("multiple_variant_assignment", truth_types)
		self.assertIn("exposure_before_assignment", truth_types)
		self.assertIn("outcome_window_inconsistent", truth_types)
		self.assertIn("sample_ratio_mismatch_ignored", truth_types)
		self.assertIn("metric_definition_changed_after_result", truth_types)

	def test_metric_definition_change_has_distinct_formula_and_auditable_event(self) -> None:
		experiment_id = "EXP-2026-000001"
		metric_definitions = self.master_data["metric_definitions"]
		conversion_definitions = metric_definitions.loc[
			(metric_definitions["metric_name"] == "conversion_rate")
			& metric_definitions["version"].isin([1, 2])
		]
		v1_id = "MET-conversion_rate-V001"
		v2_id = "MET-conversion_rate-V002"
		experiment = self.master_data["experiments"].loc[
			self.master_data["experiments"]["experiment_id"] == experiment_id
		].copy()
		experiment["primary_metric_definition_id"] = v1_id
		variants = self.master_data["variants"].loc[
			self.master_data["variants"]["experiment_id"] == experiment_id
		]
		variant_ids = variants.set_index("variant_key")["variant_id"]
		assignments = pd.DataFrame(
			[
				{
					"assignment_id": f"ASG-{experiment_id}-USR-{user_number:06d}",
					"experiment_id": experiment_id,
					"user_id": f"USR-{user_number:06d}",
					"variant_id": variant_ids[variant_key],
					"assigned_at": "2026-01-01T00:00:00+00:00",
				}
				for user_number, variant_key in [
					(1, "A"),
					(2, "A"),
					(3, "B"),
					(4, "B"),
				]
			]
		)
		conversion_events = pd.DataFrame(
			[
				{
					"assignment_id": assignments.iloc[0]["assignment_id"],
					"converted_at": "2026-01-02T00:00:00+00:00",
					"conversion_value": 10.0,
					"is_refunded": True,
				},
				{
					"assignment_id": assignments.iloc[2]["assignment_id"],
					"converted_at": "2026-01-02T00:00:00+00:00",
					"conversion_value": 10.0,
					"is_refunded": False,
				},
			]
		)
		validation_summary = pd.DataFrame(
			[
				{
					"experiment_id": experiment_id,
					"assignment_integrity_valid": True,
					"assignment_valid": True,
				}
			]
		)
		definitions = metric_definitions.loc[
			metric_definitions["metric_definition_id"].isin([v1_id, v2_id])
		]
		results_by_version = {}
		for definition_id in [v1_id, v2_id]:
			experiment_for_definition = experiment.copy()
			experiment_for_definition["primary_metric_definition_id"] = definition_id
			master_data = {
				"experiments": experiment_for_definition,
				"variants": variants,
				"metric_definitions": definitions,
				"guardrail_metrics": self.master_data["guardrail_metrics"].iloc[0:0],
			}
			result = calculate_results(
				master_data,
				assignments,
				conversion_events,
				validation_summary,
			).iloc[0]
			results_by_version[definition_id] = result

		self.assertEqual(
			results_by_version[v1_id]["estimate"],
			0.0,
			"V1 counts refunded and non-refunded conversions.",
		)
		self.assertEqual(
			results_by_version[v2_id]["estimate"],
			0.5,
			"V2 excludes the refunded control conversion.",
		)
		self.assertNotEqual(
			results_by_version[v1_id]["estimate"],
			results_by_version[v2_id]["estimate"],
		)
		self.assertEqual(set(conversion_definitions["metric_definition_id"]), {v1_id, v2_id})
		self.assertEqual(
			metric_definitions.loc[
				metric_definitions["metric_definition_id"] == v1_id, "numerator"
			].iloc[0],
			"count of assigned users with at least one in-window conversion",
		)
		self.assertEqual(
			metric_definitions.loc[
				metric_definitions["metric_definition_id"] == v2_id, "numerator"
			].iloc[0],
			"count of assigned users with at least one non-refunded in-window conversion",
		)

		event = self.tables["metric_definition_change_events"].iloc[0]
		self.assertEqual(event["old_metric_definition_id"], v1_id)
		self.assertEqual(event["new_metric_definition_id"], v2_id)
		self.assertTrue(event["reason"])
		change_time = pd.Timestamp(event["changed_at"])
		prior_results = self.results.loc[
			self.results["metric_definition_id"] == v1_id, "analyzed_at"
		]
		self.assertTrue((pd.to_datetime(prior_results, utc=True) < change_time).all())
		change_check = self.validation["checks"].set_index("check_name").loc[
			"metric_definition_change_events_reconcile"
		]
		self.assertTrue(bool(change_check["passed"]))
		change_anomaly = self.anomalies.loc[
			self.anomalies["issue_type"] == "metric_definition_changed_after_result"
		].iloc[0]
		self.assertEqual(change_anomaly["entity_id"], event["metric_definition_change_event_id"])
		change_truth = self.ground_truth.loc[
			self.ground_truth["related_event_id"]
			== event["metric_definition_change_event_id"]
		].iloc[0]
		self.assertEqual(change_truth["old_metric_definition_id"], v1_id)
		self.assertEqual(change_truth["new_metric_definition_id"], v2_id)
		self.assertEqual(
			pd.Timestamp(change_truth["event_timestamp"]),
			change_time,
		)
		self.assertEqual(
			change_truth["expected_decision"], "retain_prior_definition_reference"
		)

	def test_sample_ratio_checks_are_explicit(self) -> None:
		check_names = set(self.validation["checks"]["check_name"])
		self.assertIn(
			"EXP-2026-000010_sample_ratio_check",
			check_names,
		)
		srm_summary = self.validation["summary"].set_index("experiment_id").loc[
			"EXP-2026-000010"
		]
		self.assertFalse(bool(srm_summary["assignment_valid"]))
		self.assertTrue(bool(srm_summary["assignment_integrity_valid"]))
		self.assertTrue(
			self.validation["summary"].iloc[:-1]["sample_ratio_p_value"].ge(0.001).all()
		)
		failed_checks = self.validation["checks"].loc[
			~self.validation["checks"]["passed"], "check_name"
		].tolist()
		self.assertEqual(failed_checks, ["EXP-2026-000010_sample_ratio_check"])
		srm_results = self.results.loc[
			self.results["experiment_id"] == "EXP-2026-000010"
		]
		self.assertTrue(srm_results["result_valid"].eq(False).all())
		self.assertTrue(srm_results["decision"].eq("invalid").all())
		self.assertTrue(srm_results["estimate"].notna().all())
		self.assertTrue(srm_results["ci_lower"].notna().all())
		self.assertIn(
			"sample_ratio_mismatch_ignored",
			set(self.anomalies["issue_type"]),
		)

	def test_results_without_srm_failure_remain_valid(self) -> None:
		valid_results = self.results.loc[
			self.results["experiment_id"] == "EXP-2026-000002"
		]
		self.assertTrue(valid_results["result_valid"].eq(True).all())
		self.assertTrue(valid_results["decision"].ne("invalid").all())

	def test_full_scale_guardrail_regression_is_reported(self) -> None:
		full_tables, _ = build_dataset(scale=1.0, seed=SEED)
		guardrail = full_tables["experiment_results"].loc[
			(full_tables["experiment_results"]["experiment_id"] == "EXP-2026-000008")
			& (
				full_tables["experiment_results"]["metric_definition_id"]
				== "MET-revenue_per_assigned_user-V001"
			)
		].iloc[0]
		self.assertEqual(guardrail["decision"], "guardrail_failed")
		self.assertIn(
			"guardrail_regression",
			set(full_tables["ground_truth"]["issue_type"]),
		)

	def test_ground_truth_is_not_a_metric_input(self) -> None:
		self.assertNotIn("ground_truth", self.master_data)
		self.assertNotIn("ground_truth", self.results.columns)
		self.assertIn("ground_truth_id", self.ground_truth.columns)
		expected_effects = self.ground_truth.loc[
			self.ground_truth["issue_type"] == "expected_metric_effect"
		]
		self.assertEqual(len(expected_effects), 30)
		self.assertTrue(expected_effects["expected_effect"].notna().all())
		conversion_effects = expected_effects.loc[
			expected_effects["metric_name"] == "conversion_rate", "expected_effect"
		]
		self.assertTrue(conversion_effects.eq(0.017).all())


if __name__ == "__main__":
	unittest.main()
