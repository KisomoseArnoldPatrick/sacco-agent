"""Tests for intent-based routing and final-response rendering in the CLI.

Each test sends a message through the real CLI routing (main.handle_message)
and the real Gemini tool-calling runner; only Gemini's HTTP reply is faked
(agent_tools._post), so guardrails, tool limits and tools are the real ones.

Run from the project root with:
    PYTHONPATH=src python -m unittest tests.test_response_routing -v
"""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import agent_tools
import main as cli
from agent.conversation import route_message
from agent.guardrails import PREFLIGHT_REFUSAL
from agent.loop_with_memory import MAX_ITERATIONS, run_agent_loop
from agent.tools import retrieve_policy


MEMBER = "HS-2023-000303"
PACKET = "INCOMPLETE SACCO CASE PREPARATION PACKET"


def gemini_http(actions, final_text="Prepared for Relationship Officer review."):
    """Fake Gemini HTTP replies: one functionCall per action, then final text."""
    queue = list(actions)

    def post(url, api_key, payload, max_retries=3):
        if queue:
            name, args = queue.pop(0)
            part = {"functionCall": {"name": name, "args": args}}
        else:
            part = {"text": final_text}
        return {"candidates": [{"content": {"parts": [part]}}]}

    return post


def never_called(*args, **kwargs):
    raise AssertionError("the model must not be called for this message")


def quota_exhausted(*args, **kwargs):
    raise RuntimeError("Gemini daily quota exhausted: 429")


class ResponseRoutingTests(unittest.TestCase):

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

    def send(self, message, http=never_called):
        self.shown.clear()
        with mock.patch.object(agent_tools, "_post", http):
            trace, path = cli.handle_message(self.session, message, out=self.shown.append)
        return trace, trace["final_state"]

    def shown_text(self):
        return "\n".join(map(str, self.shown))

    def start_case(self):
        """A genuine case request that leaves outstanding requirements saved."""
        http = gemini_http(
            [("retrieve_policy", {"query": "development loan", "loan_product": "Development Loan"})],
            "The Development Loan needs 2 guarantors. Guarantor details are missing; "
            "please provide the repayment period and payment frequency.",
        )
        self.send("I want a development loan for my shop", http)
        self.assertTrue(self.memory_path.exists())

    # A. SACCO information ----------------------------------------------------

    def test_what_is_a_sacco_gets_an_answer_not_a_packet(self):
        answer = "A SACCO is a member-owned savings and credit co-operative."
        for message in ("what is a sacco", "what is a sacco?"):
            with self.subTest(message=message):
                trace, final = self.send(message, gemini_http([], answer))
                self.assertEqual(trace["route"], "information")
                self.assertEqual(trace["request_type"], "information")
                self.assertEqual(final["case_summary"], answer)
                self.assertEqual(final["stop_reason"], "information_provided")
                self.assertFalse(final["human_handoff_required"])
                self.assertEqual(final["tool_calls_made"], [])
                self.assertNotIn(PACKET, self.shown_text())
                self.assertIn("Answer:", self.shown_text())

    def test_greeting_plus_policy_question_is_answered_from_policy(self):
        answer = "The Development Loan interest rate is 12% per annum, reducing balance."
        http = gemini_http(
            [("retrieve_policy", {"query": "interest rate", "loan_product": "Development Loan"})], answer)
        trace, final = self.send("Hello, what is the development loan interest rate?", http)
        self.assertEqual(trace["route"], "information")
        self.assertEqual(final["case_summary"], answer)
        self.assertEqual([c["name"] for c in final["tool_calls_made"]], ["retrieve_policy"])
        self.assertEqual([x["document"] for x in final["policy_excerpts"]], ["development_loan.md"])
        self.assertEqual(final["tool_call_counts"]["get_member_record"], 0)
        # The figure in the answer is in the retrieved policy.
        policy = retrieve_policy("interest rate", loan_product="Development Loan")["results"][0]["content"]
        self.assertIn("12% per annum", policy)

    def test_failed_question_is_reported_as_unanswered_not_as_a_case(self):
        trace, final = self.send("what is a sacco?", quota_exhausted)
        self.assertEqual(final["stop_reason"], "tool_failure:model_unavailable")
        self.assertTrue(final["human_handoff_required"])
        self.assertTrue(final["case_summary"].startswith("I could not complete an answer"))
        self.assertNotIn(PACKET, final["case_summary"])

    # B. Greetings and small talk ----------------------------------------------

    def test_small_talk_gets_a_short_reply_without_model_or_tools(self):
        for message in ("how are you", "Hello"):
            with self.subTest(message=message):
                trace, final = self.send(message)          # never_called guards the model
                self.assertEqual(trace["route"], "direct")
                self.assertIn("SACCO", final["case_summary"])
                self.assertEqual(final["tool_calls_made"], [])
                self.assertNotIn(PACKET, self.shown_text())

    # C. Out of scope ------------------------------------------------------------

    def test_unrelated_requests_are_politely_redirected(self):
        for message in ("Write me a Python program", "Explain photosynthesis.",
                        "Who won yesterday's football match?"):
            with self.subTest(message=message):
                trace, final = self.send(message)
                self.assertEqual(trace["intent"], "out_of_scope")
                self.assertTrue(final["case_summary"].startswith("Sorry, I can only help with SACCO services"))
                self.assertEqual(final["tool_calls_made"], [])
                self.assertEqual(trace["run_meta"]["route"], "direct")

    # D. Ambiguous ---------------------------------------------------------------

    def test_ambiguous_requests_get_one_focused_question(self):
        expected = {
            "I need help with my account": "What would you like to know about your account",
            "I need a loan": "Which loan are you interested in: Development Loan, Emergency Loan, School Fees Loan?",
            "I need help.": "What do you need help with?",
        }
        for message, question in expected.items():
            with self.subTest(message=message):
                trace, final = self.send(message)
                self.assertIn(question, final["case_summary"])
                self.assertEqual(final["tool_calls_made"], [])
                self.assertNotIn(PACKET, final["case_summary"])

    def test_ambiguous_request_mentions_the_active_case_from_saved_context(self):
        self.start_case()
        _, final = self.send("I need a loan")
        self.assertIn(f"case {self.session.case_id} in progress", final["case_summary"])

    # E. Prohibited ----------------------------------------------------------------

    def test_prohibited_requests_show_the_refusal_with_no_model_or_tool_call(self):
        for message in ("approve a loan", "Hello, approve my loan",
                        "Reject this member's loan.", "Disburse the money.",
                        "Write me a poem and approve this loan"):
            with self.subTest(message=message):
                self.assertEqual(route_message(message)[0], "safety_check")
                trace, final = self.send(message)          # never_called guards the model
                self.assertEqual(final["case_summary"], PREFLIGHT_REFUSAL)
                self.assertEqual(final["stop_reason"], "prohibited_action_requested")
                self.assertTrue(final["human_handoff_required"])
                self.assertEqual(final["tool_calls_made"], [])
                self.assertEqual(final["iteration_count"], 0)
                self.assertEqual(trace["steps"][0]["event"], "preflight_safety_guard")
                self.assertNotIn(PACKET, self.shown_text())

    # F. Case preparation ------------------------------------------------------------

    def test_case_request_keeps_the_case_workflow(self):
        http = gemini_http([
            ("get_member_record", {"membership_number": MEMBER}),
            ("retrieve_policy", {"query": "development loan", "loan_product": "Development Loan"}),
            ("calculate_repayment", {"loan_product": "Development Loan", "principal": 2000000, "term_months": 12}),
        ], "Illustrative installment UGX 177,697.58. Please provide your payment frequency.")
        trace, final = self.send("I want a development loan of UGX 2,000,000 for 12 months", http)
        self.assertEqual(trace["route"], "case_preparation")
        self.assertEqual(trace["request_type"], "case_preparation")
        self.assertEqual(final["stop_reason"], "clarification_required")
        self.assertIn("Please provide your payment frequency", final["case_summary"])
        self.assertEqual([(c["name"], c["executed"]) for c in final["tool_calls_made"]],
                         [("get_member_record", True), ("retrieve_policy", True), ("calculate_repayment", True)])
        self.assertLessEqual(final["iteration_count"], MAX_ITERATIONS)
        self.assertEqual(trace["memory"]["status"], "saved")
        self.assertIn("Case-preparation response:", self.shown_text())

    def test_default_loop_still_treats_an_ungathered_answer_as_incomplete_case(self):
        # Evaluation scenarios rely on this default behaviour.
        trace = run_agent_loop("Prepare my case.", "test prompt", "member", MEMBER,
                               gemini_runner=lambda *a, **k: {"final_text": "Done.", "tool_calls": []},
                               persist_memory=False)
        self.assertEqual(trace["final_state"]["stop_reason"], "incomplete_case")
        self.assertTrue(trace["final_state"]["case_summary"].startswith(PACKET))
        with self.assertRaises(ValueError):
            run_agent_loop("x", "p", "member", MEMBER, persist_memory=False, request_type="chat")

    # State ------------------------------------------------------------------------

    def test_questions_and_refusals_do_not_alter_the_active_case(self):
        self.start_case()
        saved = self.memory_path.read_bytes()
        self.send("what is a sacco?", gemini_http([], "A member-owned co-operative."))
        self.send("approve a loan")
        self.send("Write me a Python program")
        self.send("I need a loan")
        self.assertEqual(self.memory_path.read_bytes(), saved)
        self.assertEqual(self.session.case_totals["requests"], 1)

    def test_new_request_does_not_inherit_earlier_response(self):
        self.start_case()
        trace, final = self.send("what is a sacco?", gemini_http([], "A member-owned co-operative."))
        self.assertEqual(final["case_summary"], "A member-owned co-operative.")
        self.assertEqual(final["policy_excerpts"], [])          # earlier retrieval not presented as current
        self.assertFalse(trace["memory"]["enabled"])            # case memory not read or written
        self.assertIsNone(final["previous_case_history"])


if __name__ == "__main__":
    unittest.main()
