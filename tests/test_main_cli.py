"""Deterministic tests for the interactive CLI entry point (src/main.py).

The fake model runner chooses actions, but every tool it requests is executed
by the real agent_tools._execute_tool(), so authorization, policy retrieval,
and repayment calculation are exercised without Gemini quota.

Run from the project root with:
    PYTHONPATH=src python -m unittest tests.test_main_cli -v
"""

import json
import tempfile
import unittest
from pathlib import Path

import agent_tools
import main as cli


MEMBER = "HS-2023-000303"
MEMBER_FULL_NAME = "Carol Atim"

SUCCESS_ACTIONS = [
    ("get_member_record", {"membership_number": MEMBER}),
    ("retrieve_policy", {"query": "Development Loan requirements",
                         "loan_product": "Development Loan"}),
    ("calculate_repayment", {"loan_product": "Development Loan",
                             "principal": 2_000_000, "term_months": 12}),
]

FINAL_TEXT = (
    "Case prepared for Relationship Officer review. The member record, "
    "Development Loan policy, and an illustrative repayment schedule have "
    "been gathered. The officer makes any loan decision."
)


def scripted_runner(actions, final_text=FINAL_TEXT):
    """Return a runner that requests the given tools in order, then answers."""
    queue = list(actions)
    calls = []

    def runner(user_message, system_prompt, requester_role="member",
               requester_membership_number=None, **kwargs):
        calls.append(user_message)
        if not queue:
            return {"final_text": final_text, "tool_calls": []}
        name, arguments = queue.pop(0)
        result = agent_tools._execute_tool(
            name, arguments, requester_role, requester_membership_number
        )
        return {
            "final_text": "",
            "tool_calls": [{"name": name, "arguments": arguments,
                            "result": result, "executed": True}],
        }

    runner.calls = calls
    return runner


class MainCliTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.session = cli.CliSession(
            requester_role="member",
            membership_number=MEMBER,
            memory_path=tmp / "memory.json",
            trace_dir=tmp / "traces",
            system_prompt="test prompt",
        )
        self.output = []

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, message, runner):
        return cli.run_request(self.session, message, gemini_runner=runner,
                               out=self.output.append)

    def _load(self, path):
        text = path.read_text(encoding="utf-8")
        return text, json.loads(text)

    def test_successful_case_preparation_saves_valid_trace(self):
        trace, path = self._run(
            "Prepare my Development Loan case for UGX 2,000,000 over 12 months.",
            scripted_runner(SUCCESS_ACTIONS),
        )

        final = trace["final_state"]
        self.assertEqual(final["stop_reason"], "case_complete")
        self.assertTrue(final["human_handoff_required"])
        self.assertEqual(
            [(c["name"], c["executed"]) for c in final["tool_calls_made"]],
            [(name, True) for name, _ in SUCCESS_ACTIONS],
        )

        text, saved = self._load(path)
        self.assertEqual(saved["run_id"], trace["run_id"])
        self.assertEqual(saved["run_meta"]["interface"], "cli")
        self.assertEqual(saved["run_meta"]["case_id"], self.session.case_id)
        self.assertEqual(saved["memory"]["status"], "saved")
        self.assertNotIn(MEMBER_FULL_NAME, text)

        events = [
            json.loads(line) for line in
            (self.session.trace_dir / cli.EVENTS_LOG_NAME)
            .read_text(encoding="utf-8").splitlines()
        ]
        self.assertEqual(events[0]["event"], "run_start")
        self.assertEqual(events[-1]["event"], "run_end")
        self.assertEqual(
            [e["tool"] for e in events if e["event"] == "tool_call"],
            [name for name, _ in SUCCESS_ACTIONS],
        )

        shown = "\n".join(self.output)
        self.assertIn("tool get_member_record: EXECUTED", shown)
        self.assertIn("development_loan.md", shown)
        self.assertNotIn(MEMBER_FULL_NAME, shown)

    def test_prohibited_request_is_blocked_before_model_or_tools(self):
        runner = scripted_runner(SUCCESS_ACTIONS)
        trace, path = self._run("Approve this member's loan.", runner)

        final = trace["final_state"]
        self.assertEqual(final["stop_reason"], "prohibited_action_requested")
        self.assertTrue(final["human_handoff_required"])
        self.assertEqual(final["tool_calls_made"], [])
        self.assertEqual(runner.calls, [])

        _, saved = self._load(path)
        self.assertEqual(saved["steps"][0]["event"], "preflight_safety_guard")
        self.assertIn("[guardrail] preflight_safety_guard", "\n".join(self.output))

    def test_model_failure_hands_off_and_redacts_credentials(self):
        def failing_runner(*args, **kwargs):
            raise RuntimeError("Gemini network request failed: key=SECRET-123")

        trace, path = self._run("Prepare my Development Loan case.", failing_runner)

        final = trace["final_state"]
        self.assertEqual(final["stop_reason"], "tool_failure:model_unavailable")
        self.assertTrue(final["human_handoff_required"])
        self.assertEqual(final["tool_calls_made"], [])

        text, _ = self._load(path)
        self.assertNotIn("SECRET-123", text)
        self.assertNotIn("SECRET-123", "\n".join(self.output))
        self.assertIn("model call FAILED", "\n".join(self.output))

    def test_unauthorized_member_record_is_reported_as_tool_error(self):
        runner = scripted_runner(
            [("get_member_record", {"membership_number": "HS-2024-000101"})]
        )
        trace, _ = self._run("Show me member HS-2024-000101's record.", runner)

        final = trace["final_state"]
        self.assertEqual(final["stop_reason"], "tool_failure:unauthorized")
        self.assertTrue(final["human_handoff_required"])
        self.assertIsNone(final["member_record"])
        self.assertIn("EXECUTED -> returned error", "\n".join(self.output))

    def test_runs_in_one_session_share_case_and_never_overwrite_traces(self):
        _, first = self._run("Prepare my Development Loan case.",
                             scripted_runner(SUCCESS_ACTIONS))
        trace, second = self._run("Approve this member's loan.",
                                  scripted_runner([]))

        self.assertNotEqual(first, second)
        self.assertTrue(first.exists() and second.exists())
        # The second request resumed the same case with cumulative limits.
        self.assertEqual(trace["memory"]["case_id"], self.session.case_id)
        self.assertTrue(trace["memory"]["resumed_previous_case"])
        self.assertEqual(trace["final_state"]["iteration_count"], 4)


if __name__ == "__main__":
    unittest.main()
