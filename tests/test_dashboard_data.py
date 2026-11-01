"""Tests for loading pipeline outputs and deriving dashboard result values."""

import tempfile
import unittest
from pathlib import Path

import pandas as pd

from dashboard_data import REQUIRED_TABLES, build_result_detail, load_dashboard_data


class DashboardDataTests(unittest.TestCase):
    def test_loader_reads_required_csv_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            for table_name in REQUIRED_TABLES:
                pd.DataFrame({"sample_value": [1]}).to_csv(
                    output_dir / f"{table_name}.csv", index=False
                )

            tables = load_dashboard_data(output_dir)

            self.assertTrue(REQUIRED_TABLES.issubset(tables))
            self.assertEqual(tables["experiments"].loc[0, "sample_value"], 1)

    def test_loader_explains_when_outputs_are_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(FileNotFoundError, "Run main.py"):
                load_dashboard_data(Path(directory))

    def test_result_arm_means_use_only_in_window_conversions(self) -> None:
        experiment_id = "EXP-2026-000001"
        metric_ids = {
            "conversion_rate": "MET-conversion_rate-V001",
            "revenue_per_assigned_user": "MET-revenue_per_assigned_user-V001",
            "refund_rate": "MET-refund_rate-V001",
        }
        tables = {
            "experiments": pd.DataFrame(
                [{"experiment_id": experiment_id, "outcome_window_days": 7}]
            ),
            "variants": pd.DataFrame(
                [
                    {"variant_id": f"VAR-{experiment_id}-A", "variant_key": "A"},
                    {"variant_id": f"VAR-{experiment_id}-B", "variant_key": "B"},
                ]
            ),
            "assignments": pd.DataFrame(
                [
                    {
                        "assignment_id": f"ASG-{experiment_id}-USR-000001",
                        "experiment_id": experiment_id,
                        "variant_id": f"VAR-{experiment_id}-A",
                        "assigned_at": "2026-01-01T00:00:00+00:00",
                    },
                    {
                        "assignment_id": f"ASG-{experiment_id}-USR-000002",
                        "experiment_id": experiment_id,
                        "variant_id": f"VAR-{experiment_id}-B",
                        "assigned_at": "2026-01-01T00:00:00+00:00",
                    },
                ]
            ),
            "conversion_events": pd.DataFrame(
                [
                    {
                        "assignment_id": f"ASG-{experiment_id}-USR-000001",
                        "converted_at": "2026-01-02T00:00:00+00:00",
                        "outcome_window_days": 7,
                        "conversion_value": 10.0,
                        "is_refunded": False,
                    },
                    {
                        "assignment_id": f"ASG-{experiment_id}-USR-000002",
                        "converted_at": "2026-01-03T00:00:00+00:00",
                        "outcome_window_days": 7,
                        "conversion_value": 20.0,
                        "is_refunded": True,
                    },
                    {
                        "assignment_id": f"ASG-{experiment_id}-USR-000002",
                        "converted_at": "2026-01-10T00:00:00+00:00",
                        "outcome_window_days": 7,
                        "conversion_value": 99.0,
                        "is_refunded": False,
                    },
                ]
            ),
            "metric_definitions": pd.DataFrame(
                [
                    {"metric_definition_id": metric_id, "metric_name": metric_name}
                    for metric_name, metric_id in metric_ids.items()
                ]
            ),
            "experiment_results": pd.DataFrame(
                [
                    {
                        "experiment_id": experiment_id,
                        "metric_definition_id": metric_id,
                        "estimate": estimate,
                        "decision": "inconclusive",
                        "ci_lower": -1.0,
                        "ci_upper": 1.0,
                        "p_value": 0.5,
                    }
                    for metric_id, estimate in [
                        (metric_ids["conversion_rate"], 0.0),
                        (metric_ids["revenue_per_assigned_user"], 10.0),
                        (metric_ids["refund_rate"], 1.0),
                    ]
                ]
            ),
            "validation_summary": pd.DataFrame(
                [{"experiment_id": experiment_id, "assignment_valid": True}]
            ),
            "ground_truth": pd.DataFrame(
                columns=[
                    "issue_type",
                    "entity_id",
                    "metric_definition_id",
                    "expected_control",
                    "expected_treatment",
                    "expected_effect",
                ]
            ),
        }

        detail = build_result_detail(tables).set_index("metric_name")

        self.assertTrue(detail["result_valid"].all())
        self.assertEqual(detail.loc["conversion_rate", "control_value"], 1.0)
        self.assertEqual(detail.loc["conversion_rate", "treatment_value"], 1.0)
        self.assertEqual(detail.loc["revenue_per_assigned_user", "control_value"], 10.0)
        self.assertEqual(detail.loc["revenue_per_assigned_user", "treatment_value"], 20.0)
        self.assertEqual(detail.loc["refund_rate", "control_value"], 0.0)
        self.assertEqual(detail.loc["refund_rate", "treatment_value"], 1.0)

        tables["validation_summary"]["assignment_valid"] = False
        srm_detail = build_result_detail(tables).set_index("metric_name")
        self.assertFalse(srm_detail["result_valid"].any())
        self.assertTrue(srm_detail["decision"].eq("inconclusive").all())


if __name__ == "__main__":
    unittest.main()
