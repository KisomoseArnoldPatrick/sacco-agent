"""Regression tests for CLI conversation handling and per-request budgets.

Covers the issues seen in a live CLI session: small talk and pauses turned
into incomplete case packets, a prohibited request that ran a tool before
refusing, and a case-wide iteration budget exhausted by unrelated messages.

Budget tests fake only Gemini's HTTP response (agent_tools._post), so the real
call_gemini_with_tools limit check and the real tools run.

Run from the project root with:
    PYTHONPATH=src python -m unittest tests.test_cli_conversation -v
"""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent_tools
import main as cli
from agent.conversation import classify_message
from agent.guardrails import detect_prohibited_action
from agent.loop_with_memory import MAX_CALLS_PER_TOOL, MAX_ITERATIONS
from agent.tools import POLICY_DIR, retrieve_policy


MEMBER = "HS-2023-000303"


def gemini_http(actions, final_text="Prepared for Relationship Officer review."):
    """Fake Gemini HTTP replies: one functionCall per action, then final text."""
    queue = list(actions)
    calls = []

    def post(url, api_key, payload, max_retries=3):
        calls.append(payload)
        if queue:
            name, args = queue.pop(0)
            part = {"functionCall": {"name": name, "args": args}}
        else:
            part = {"text": final_text}
        return {"candidates": [{"content": {"parts": [part]}}]}

    post.calls = calls
    return post


def never_called(*args, **kwargs):
    raise AssertionError("the model must not be called for this message")


class CliConversationTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        tmp = Path(self._tmp.name)
        self.memory_path = tmp / "memory.json"
        self.session = cli.CliSession(
            requester_role="member", membership_number=MEMBER,
            memory_path=self.memory_path, trace_dir=tmp / "traces",
            system_prompt="test prompt",
        )
        self.shown = []
        env = mock.patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self._tmp.cleanup()

    def send(self, message, http=None):
        """Send a message through the real CLI routing and Gemini runner."""
        with mock.patch.object(agent_tools, "_post", http or never_called):
            return cli.handle_message(self.session, message, out=self.shown.append)

    def text(self):
        return "\n".join(map(str, self.shown))

    # 1-3: small talk -------------------------------------------------------

    def test_name_question_gets_direct_answer_not_a_case_packet(self):
        trace, path = self.send("what is your name")
        final = trace["final_state"]
        self.assertIn("SACCO Member-Case Preparation Agent", final["case_summary"])
        self.assertIn("cannot approve or reject loans", final["case_summary"])
        self.assertNotIn("INCOMPLETE", self.text())
        self.assertEqual(final["tool_calls_made"], [])
        self.assertEqual(final["iteration_count"], 0)

    def test_capabilities_lists_tools_and_boundaries(self):
        trace, _ = self.send("What can you do?")
        reply = trace["final_state"]["case_summary"]
        for expected in ("get_member_record", "retrieve_policy", "calculate_repayment",
                         f"{MAX_ITERATIONS} steps", "Relationship Officer",
                         "cannot approve or reject loans"):
            self.assertIn(expected, reply)

    def test_greeting_and_thanks_use_no_tools_or_model(self):
        for message in ("hello", "Thank you!", "how do i use this system"):
            with self.subTest(message=message):
                trace, _ = self.send(message)
                self.assertEqual(trace["handling"], "direct_response")
                self.assertEqual(trace["final_state"]["tool_calls_made"], [])

    # 4-5: pause and resume ---------------------------------------------------

    def _prepare_school_fees_case(self):
        http = gemini_http(
            [("retrieve_policy", {"query": "school fees loan", "loan_product": "School Fees Loan"})],
            "The School Fees Loan requires 2 guarantors. Guarantor details are missing; "
            "please provide the loan amount, repayment period and payment frequency.",
        )
        # A case-preparation request (not a question), so the case is saved.
        return self.send("I want a school fees loan for my daughter", http)

    def test_pause_is_acknowledged_without_touching_case_state(self):
        self._prepare_school_fees_case()
        saved_before = self.memory_path.read_bytes()

        trace, _ = self.send("i will gt back to you next week")

        self.assertEqual(self.memory_path.read_bytes(), saved_before)
        reply = trace["final_state"]["case_summary"]
        self.assertIn(f"Your case {self.session.case_id} is saved", reply)
        self.assertIn("school_fees_loan.md", reply)
        self.assertIn("guarantors", reply)
        self.assertEqual(trace["memory"]["status"], "history_read")

    def test_resume_uses_saved_context(self):
        self._prepare_school_fees_case()
        trace, _ = self.send("continue my school fees application")
        reply = trace["final_state"]["case_summary"]
        self.assertIn(f"Continuing case {self.session.case_id}", reply)
        self.assertIn("school_fees_loan.md", reply)

    def test_resume_without_saved_context_asks_instead_of_inventing(self):
        trace, _ = self.send("continue my school fees application")
        reply = trace["final_state"]["case_summary"]
        self.assertIn("I don't have a saved case", reply)
        self.assertNotIn("school_fees_loan.md", reply)

    # 6-7: legitimate request and grounding ---------------------------------

    def test_school_fees_request_goes_to_agent_and_retrieves_policy(self):
        self.assertIsNone(classify_message("I want a school fees loan for my daughter"))
        self.assertFalse(detect_prohibited_action("I want to apply for a school fees loan")[0])
        trace, _ = self._prepare_school_fees_case()
        self.assertEqual(trace["run_meta"]["handling"], "agent_loop")
        self.assertEqual(
            [item["document"] for item in trace["final_state"]["policy_excerpts"]],
            ["school_fees_loan.md"],
        )

    def test_school_fees_claims_are_in_the_retrieved_policy(self):
        # Claims made in the live answer, checked against the retrieved text.
        content = retrieve_policy("school fees loan", loan_product="School Fees Loan")["results"][0]["content"]
        for claim in ("UGX 5,000,000", "Up to 4 months", "up to 12 months",
                      "Guarantors required | 2", "official fee structure or invoice"):
            self.assertIn(claim, content)
        self.assertEqual(POLICY_DIR.name, "Knowledge")

    # 8: prohibited request ----------------------------------------------------

    def test_prohibited_request_refused_before_any_tool_or_model_call(self):
        for message in ("approve for me a loan", "can you approve my school fees loan"):
            with self.subTest(message=message):
                trace, _ = self.send(message)          # never_called guards the model
                final = trace["final_state"]
                self.assertEqual(final["stop_reason"], "prohibited_action_requested")
                self.assertTrue(final["human_handoff_required"])
                self.assertEqual(final["tool_calls_made"], [])

    def test_questions_about_approval_are_not_blocked(self):
        for message in ("Can an officer approve a member's loan the same day?",
                        "How long does it take for a loan application to be approved?"):
            with self.subTest(message=message):
                self.assertFalse(detect_prohibited_action(message)[0])

    # 9-10: budgets ------------------------------------------------------------

    FULL_BUDGET = [
        ("get_member_record", {"membership_number": MEMBER}),
        ("get_member_record", {"membership_number": MEMBER}),
        ("retrieve_policy", {"query": "development loan", "loan_product": "Development Loan"}),
        ("retrieve_policy", {"query": "guarantors"}),
        ("calculate_repayment", {"loan_product": "Development Loan", "principal": 2000000, "term_months": 12}),
        ("calculate_repayment", {"loan_product": "Development Loan", "principal": 1000000, "term_months": 12}),
    ]

    def test_exhausted_request_does_not_exhaust_the_next_request(self):
        first, _ = self.send("Prepare my Development Loan case.", gemini_http(self.FULL_BUDGET))
        self.assertEqual(first["final_state"]["stop_reason"], "max_iterations_reached")
        self.assertEqual(first["final_state"]["iteration_count"], MAX_ITERATIONS)

        second, _ = self.send(
            "Show my member record.",
            gemini_http([("get_member_record", {"membership_number": MEMBER})]),
        )
        final = second["final_state"]
        self.assertEqual(final["iteration_count"], 2)
        self.assertEqual(final["tool_call_counts"]["get_member_record"], 1)
        self.assertNotEqual(final["stop_reason"], "max_iterations_reached")
        self.assertTrue(second["memory"]["resumed_previous_case"])   # same case, own budget
        self.assertEqual(self.session.case_totals["iterations"], MAX_ITERATIONS + 2)

        # The final question of the demo is still answered.
        third, _ = self.send("what is your name")
        self.assertIn("SACCO Member-Case Preparation Agent", third["final_state"]["case_summary"])

    def test_per_tool_limit_still_applies_within_one_request(self):
        actions = [("get_member_record", {"membership_number": MEMBER})] * (MAX_CALLS_PER_TOOL + 1)
        trace, _ = self.send("Prepare my case.", gemini_http(actions))
        final = trace["final_state"]
        self.assertEqual(final["stop_reason"], "tool_call_limit_exceeded")
        self.assertEqual([c["executed"] for c in final["tool_calls_made"]],
                         [True] * MAX_CALLS_PER_TOOL + [False])
        self.assertEqual(final["tool_call_counts"]["get_member_record"], MAX_CALLS_PER_TOOL)

    # 11: traces ---------------------------------------------------------------

    def test_direct_response_trace_is_truthful(self):
        trace, path = self.send("what is your name")
        saved = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(saved["handling"], "direct_response")
        self.assertEqual(saved["run_meta"]["handling"], "direct_response")
        self.assertEqual(saved["steps"], [])
        self.assertIsNone(saved["prompt_version"])           # no prompt was sent
        self.assertEqual(saved["final_state"]["stop_reason"], "direct_response:identity")
        self.assertFalse(saved["final_state"]["human_handoff_required"])
        events = [json.loads(line)["event"] for line in
                  (self.session.trace_dir / cli.EVENTS_LOG_NAME).read_text(encoding="utf-8").splitlines()]
        self.assertEqual(events, ["run_start", "run_end"])

    def test_incomplete_packet_separates_this_request_from_case_history(self):
        self._prepare_school_fees_case()
        # A case-preparation message the model answers without any tool.
        trace, _ = self.send("I want to borrow for my farm", gemini_http([], "Sure."))
        packet = trace["final_state"]["case_summary"]
        self.assertIn("Information gathered in this request:", packet)
        self.assertIn("Earlier in this case (saved history, not re-checked in this request):", packet)
        self.assertIn("Policy document previously retrieved: school_fees_loan.md", packet)
        self.assertIsNone(trace["final_state"]["member_record"])


if __name__ == "__main__":
    unittest.main()
