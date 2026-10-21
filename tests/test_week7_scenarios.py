"""
Week 7 — runs the evaluation dataset as tests.

1. The dataset itself must meet the brief (30+ scenarios, all six categories).
2. Every scenario must pass against the real loop, tools and guardrails.
3. Each catalogued failure (F1..F11, G1) has a named test, so a regression
   points straight at the Failure Catalogue entry it re-opens.

Run from the repo root:
    python3 -m unittest tests.test_week7_scenarios -v
"""
import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent.run_week7_eval import SCENARIO_FILE, run_scenario  # noqa: E402

SCENARIOS = {s["id"]: s for s in json.loads(Path(SCENARIO_FILE).read_text(encoding="utf-8"))}
REQUIRED_CATEGORIES = {"normal", "edge", "incorrect_info", "adversarial", "tool_failure", "unauthorized"}


def passed(result):
    return result["completed_as_expected"] and result["tool_selection_ok"] and not result["safety_violations"]


class DatasetShape(unittest.TestCase):
    def test_at_least_thirty_scenarios(self):
        self.assertGreaterEqual(len(SCENARIOS), 30)

    def test_all_six_categories_present(self):
        self.assertEqual({s["category"] for s in SCENARIOS.values()}, REQUIRED_CATEGORIES)

    def test_every_scenario_states_an_expected_outcome(self):
        for sid, s in SCENARIOS.items():
            with self.subTest(scenario=sid):
                self.assertTrue(s["expect"], "no expectations defined")
                self.assertTrue(s["request"]["message"])


class AllScenarios(unittest.TestCase):
    def test_every_scenario_passes(self):
        failures = []
        for sid, scenario in SCENARIOS.items():
            result = run_scenario(scenario)
            if not passed(result):
                failures.append(f"{sid}: stop={result['stop_reason']} checks={result['checks']} "
                                f"safety={result['safety_violations']}")
        self.assertEqual(failures, [], "\n".join(failures))


class FailureCatalogueRegressions(unittest.TestCase):
    def run_ids(self, *ids):
        for sid in ids:
            with self.subTest(scenario=sid):
                result = run_scenario(SCENARIOS[sid])
                self.assertTrue(passed(result), f"{sid}: {result['stop_reason']} {result['checks']} {result['safety_violations']}")

    def test_F1_member_fields_reach_the_model(self):
        self.run_ids("E03")

    def test_F2_refusal_wording_does_not_break_a_complete_case(self):
        self.run_ids("N07")

    def test_F3_natural_clarification_is_recognised(self):
        self.run_ids("I05")

    def test_F4_malformed_membership_number_is_rejected(self):
        self.run_ids("I02")

    def test_F5_prompt_injection_in_user_input_is_blocked(self):
        self.run_ids("A01", "A02")

    def test_F6_injected_text_in_policy_document_is_blocked(self):
        self.run_ids("A04")

    def test_F7_asserted_decision_in_output_is_blocked(self):
        self.run_ids("A06")

    def test_F8_other_member_identifier_in_output_is_blocked(self):
        self.run_ids("A07")

    def test_F9_model_timeout_does_not_crash_the_run(self):
        self.run_ids("T03")

    def test_F10_api_key_is_not_persisted(self):
        self.run_ids("T07")

    def test_F11_malformed_tool_result_is_rejected(self):
        self.run_ids("T05")

    def test_G1_legitimate_question_is_not_over_blocked(self):
        self.run_ids("N08")


if __name__ == "__main__":
    unittest.main(verbosity=2)
