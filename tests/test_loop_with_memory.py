
"""Integration tests for Week 6 history retrieval and decision boundaries.

Run from the full project root with:
    PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_loop_with_memory.py' -v

A JSON report is written to:
    evidence/memory/loop_integration_test_results.json
"""

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path


# The isolated package may omit the Week 5 application modules.
# Use import-only stubs when those modules are unavailable.
if importlib.util.find_spec("baseline_chat") is None:
    baseline_stub = types.ModuleType("baseline_chat")
    baseline_stub.load_system_prompt = lambda: "test prompt"
    sys.modules["baseline_chat"] = baseline_stub

if importlib.util.find_spec("agent_tools") is None:
    tools_stub = types.ModuleType("agent_tools")
    tools_stub.call_gemini_with_tools = lambda *args, **kwargs: None
    sys.modules["agent_tools"] = tools_stub


from agent.memory import CaseMemoryStore
from agent.state import new_workflow_state, apply_preparation_observation
from agent.loop_with_memory import run_agent_loop


REPO_ROOT = Path(__file__).resolve().parents[1]
JSON_RESULTS_PATH = (
    REPO_ROOT
    / "evidence"
    / "memory"
    / "loop_integration_test_results.json"
)


class JSONTestResult(unittest.TextTestResult):
    """Collect individual test outcomes for the JSON report."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.test_records = []

    @staticmethod
    def _test_name(test):
        return test.id()

    def _record(self, test, status, error_message=None):
        self.test_records.append({
            "test": self._test_name(test),
            "status": status,
            "error_message": error_message,
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(
            test, "FAIL", self._exc_info_to_string(err, test)
        )

    def addError(self, test, err):
        super().addError(test, err)
        self._record(
            test, "ERROR", self._exc_info_to_string(err, test)
        )

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "SKIP", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(
            test,
            "EXPECTED_FAILURE",
            self._exc_info_to_string(err, test),
        )

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "UNEXPECTED_SUCCESS")


class JSONTestRunner(unittest.TextTestRunner):
    """Run tests and save a JSON report after the suite finishes."""

    resultclass = JSONTestResult

    def __init__(self, *args, json_results_path=JSON_RESULTS_PATH, **kwargs):
        super().__init__(*args, **kwargs)
        self.json_results_path = Path(json_results_path)

    def run(self, test):
        result = super().run(test)
        records = result.test_records

        summary = {
            "total": len(records),
            "passed": sum(r["status"] == "PASS" for r in records),
            "failed": sum(r["status"] == "FAIL" for r in records),
            "errors": sum(r["status"] == "ERROR" for r in records),
            "skipped": sum(r["status"] == "SKIP" for r in records),
            "expected_failures": sum(
                r["status"] == "EXPECTED_FAILURE" for r in records
            ),
            "unexpected_successes": sum(
                r["status"] == "UNEXPECTED_SUCCESS" for r in records
            ),
        }

        report = {
            "suite": "Week 6 loop-with-memory integration tests",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "overall_status": (
                "PASS" if result.wasSuccessful() else "FAIL"
            ),
            "summary": summary,
            "tests": records,
        }

        self.json_results_path.parent.mkdir(
            parents=True, exist_ok=True
        )
        self.json_results_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        self.stream.writeln(
            f"\nJSON test report: {self.json_results_path}"
        )
        return result


class LoopMemoryIntegrationTests(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.temp.name) / "memory.json"
        self.store = CaseMemoryStore(self.store_path)
        self.owner = "HS-SYNTHETIC-0001"

        state = new_workflow_state(
            self.owner,
            "member",
            "Prepare a Development Loan case.",
            "case-1",
        )

        apply_preparation_observation(
            state,
            member_record_retrieved=True,
            policy_documents=["development_loan.md"],
            repayment_calculated=False,
            missing_requirements=["Confirm repayment term"],
        )

        self.store.save(state, self.owner)

    def tearDown(self):
        self.temp.cleanup()

    def _runner_that_must_not_run(self, *args, **kwargs):
        self.fail(
            "Gemini/tool runner must not be called for this test path"
        )

    def test_authorized_officer_gets_visible_read_only_history(self):
        result = run_agent_loop(
            member_message="Show the saved case history.",
            system_prompt="test prompt",
            requester_role="officer",
            requester_membership_number="OFFICER-SYNTHETIC-01",
            case_owner_membership_number=self.owner,
            case_id="case-1",
            memory_store_path=self.store_path,
            resume_saved_case=True,
            authorized_member_numbers={self.owner},
            gemini_runner=self._runner_that_must_not_run,
        )

        self.assertEqual(
            result["memory"]["status"],
            "history_retrieved_read_only",
        )
        self.assertEqual(
            result["final_state"]["stop_reason"],
            "history_retrieved_read_only",
        )
        self.assertIn(
            "SACCO CASE HISTORY — READ ONLY",
            result["final_state"]["case_summary"],
        )
        self.assertIn(
            "Confirm repayment term",
            result["final_state"]["case_summary"],
        )
        self.assertEqual(result["steps"][0]["tool_calls"], [])

    def test_unauthorized_officer_is_denied_without_history(self):
        result = run_agent_loop(
            member_message="Show the saved case history.",
            system_prompt="test prompt",
            requester_role="officer",
            requester_membership_number="OFFICER-SYNTHETIC-02",
            case_owner_membership_number=self.owner,
            case_id="case-1",
            memory_store_path=self.store_path,
            resume_saved_case=True,
            authorized_member_numbers={"HS-SYNTHETIC-9999"},
            gemini_runner=self._runner_that_must_not_run,
        )

        self.assertEqual(result["memory"]["status"], "access_denied")
        self.assertEqual(
            result["final_state"]["stop_reason"],
            "unauthorized_case_history_access",
        )
        self.assertNotIn(
            "Confirm repayment term",
            result["final_state"]["case_summary"],
        )
        self.assertEqual(result["steps"][0]["tool_calls"], [])

    def test_missing_history_is_reported_without_running_agent(self):
        result = run_agent_loop(
            member_message="Show the saved case history.",
            system_prompt="test prompt",
            requester_role="officer",
            requester_membership_number="OFFICER-SYNTHETIC-01",
            case_owner_membership_number=self.owner,
            case_id="does-not-exist",
            memory_store_path=self.store_path,
            resume_saved_case=True,
            authorized_member_numbers={self.owner},
            gemini_runner=self._runner_that_must_not_run,
        )

        self.assertEqual(
            result["memory"]["status"], "history_not_found"
        )
        self.assertEqual(
            result["final_state"]["stop_reason"],
            "case_history_not_found",
        )
        self.assertEqual(result["steps"][0]["tool_calls"], [])

    def test_resumed_case_preserves_cumulative_counters(self):
        # Resuming a case at the iteration ceiling must not reset its budget.
        state = self.store.load("case-1", self.owner)
        state["workflow"]["iteration_count"] = 6
        state["workflow"]["tool_call_counts"]["get_member_record"] = 2
        self.store.save(state, self.owner)

        result = run_agent_loop(
            member_message="Continue preparing my saved case.",
            system_prompt="test prompt",
            requester_role="member",
            requester_membership_number=self.owner,
            case_id="case-1",
            memory_store_path=self.store_path,
            resume_saved_case=True,
            gemini_runner=self._runner_that_must_not_run,
        )

        self.assertEqual(result["final_state"]["iteration_count"], 6)
        self.assertEqual(
            result["final_state"]["tool_call_counts"]["get_member_record"],
            2,
        )
        self.assertEqual(
            result["final_state"]["stop_reason"],
            "max_iterations_reached",
        )
        self.assertEqual(result["steps"], [])

    def test_approval_request_is_refused_before_model_or_tools(self):
        result = run_agent_loop(
            member_message="Approve this loan.",
            system_prompt="test prompt",
            requester_role="member",
            requester_membership_number=None,
            memory_store_path=self.store_path,
            persist_memory=False,
            gemini_runner=self._runner_that_must_not_run,
        )

        self.assertEqual(
            result["final_state"]["stop_reason"],
            "prohibited_action_requested",
        )
        self.assertTrue(
            result["final_state"]["human_handoff_required"]
        )
        self.assertEqual(result["steps"][0]["tool_calls"], [])


if __name__ == "__main__":
    runner = JSONTestRunner(verbosity=2)
    suite = unittest.defaultTestLoader.loadTestsFromModule(
        sys.modules[__name__]
    )
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
