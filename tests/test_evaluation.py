"""
Unit and integration tests for Week 7 Evaluation Dataset and Runner.

Covers:
- Dataset schema validation (all 36 scenarios).
- Representation across all 6 required categories.
- ID uniqueness.
- EvaluationRunner execution and metric aggregation.
- Result exports (evaluation_results.json, metrics.json, traces).
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

for d in (REPO_ROOT, SRC_DIR):
    if str(d) not in sys.path:
        sys.path.insert(0, str(d))

from agent.evaluation import (
    load_scenarios,
    validate_scenario_schema,
    EvaluationRunner,
    SCENARIOS_PATH,
)


class TestEvaluation(unittest.TestCase):

    def setUp(self):
        self.scenarios = load_scenarios()

    def test_01_scenario_count_meets_target(self):
        """Must have at least 30 scenarios; prefer 36."""
        self.assertGreaterEqual(len(self.scenarios), 30)
        self.assertEqual(len(self.scenarios), 36)

    def test_02_all_six_categories_represented(self):
        """All 6 required categories must have at least 5 (prefer 6) scenarios each."""
        expected_categories = {
            "normal",
            "edge_cases",
            "incorrect_information",
            "adversarial_prompts",
            "tool_failures",
            "unauthorized_prohibited",
        }
        category_counts = {}
        for sc in self.scenarios:
            cat = sc["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1

        self.assertEqual(set(category_counts.keys()), expected_categories)
        for cat in expected_categories:
            self.assertGreaterEqual(category_counts[cat], 6, f"Category '{cat}' has fewer than 6 scenarios.")

    def test_03_scenario_id_uniqueness_and_naming(self):
        ids = [sc["id"] for sc in self.scenarios]
        self.assertEqual(len(ids), len(set(ids)), "Duplicate scenario IDs detected.")
        for sc_id in ids:
            self.assertTrue(any(sc_id.startswith(p) for p in ("NORM-", "EDGE-", "INCOR-", "ADV-", "TOOL-", "UNAUTH-")))

    def test_04_scenario_schema_completeness(self):
        for sc in self.scenarios:
            validate_scenario_schema(sc)
            self.assertIn("request", sc)
            self.assertIn("member_message", sc["request"])
            self.assertIn("expected_stop_reason", sc)
            self.assertIn("expected_human_handoff", sc)
            self.assertIsInstance(sc["expected_human_handoff"], bool)

    def test_05_runner_executes_single_scenario_accurately(self):
        runner = EvaluationRunner()
        norm_01 = next(sc for sc in self.scenarios if sc["id"] == "NORM-01")
        with tempfile.TemporaryDirectory() as tmp_dir:
            res = runner.execute_scenario(norm_01, temp_dir=Path(tmp_dir))
            self.assertEqual(res["scenario_id"], "NORM-01")
            self.assertTrue(res["passed"])
            self.assertFalse(res["safety_violation"])
            self.assertEqual(res["actual_stop_reason"], "case_complete")

    def test_06_runner_aggregates_metrics_correctly(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            ev_dir = Path(tmp_dir) / "evidence"
            tr_path = Path(tmp_dir) / "traces.jsonl"
            runner = EvaluationRunner(evidence_dir=ev_dir, traces_path=tr_path)
            results_dict, metrics = runner.run_all()

            self.assertEqual(metrics["total_scenarios"], 36)
            self.assertEqual(metrics["scenarios_passed"], 36)
            self.assertEqual(metrics["overall_pass_rate_pct"], 100.0)
            self.assertEqual(metrics["core_metrics"]["safety_violations_count"], 0)
            self.assertGreater(metrics["latency_ms"]["mean_ms"], 0.0)
            self.assertEqual(metrics["acceptance_criteria_verdict"]["overall_verdict"], "PASS")

            # Verify files were exported
            self.assertTrue((ev_dir / "evaluation_results.json").exists())
            self.assertTrue((ev_dir / "metrics.json").exists())
            self.assertTrue(tr_path.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)

