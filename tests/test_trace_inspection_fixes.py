"""Regression tests for defects found by inspecting live CLI traces (Week 8).

A. Member financial fields were dropped before reaching the model.
B. The policy directory name did not match Git ("knowledge" vs "Knowledge").
C. Output validation flagged decision claims but still showed them.
D. Traces labelled the prompt "v1.2" while the agent loaded v1.0.

Each test exercises both agent loops (agent.loop and agent.loop_with_memory)
where the defect affected both. Tools are real; the model is scripted.

Run from the project root with:
    PYTHONPATH=src python -m unittest tests.test_trace_inspection_fixes -v
"""

import json
import os
import tempfile
import unittest
from pathlib import Path

import agent_tools
import main as cli
from agent import loop, loop_with_memory
from agent.guardrails import OUTPUT_WITHHELD_NOTICE, validate_agent_output
from agent.observability import AgentTracer
from agent.tools import (
    POLICY_DIR,
    get_member_record,
    retrieve_policy,
    summarize_member_record_for_model,
)
from baseline_chat import (
    DEFAULT_PROMPT_VERSION,
    PROMPTS_DIR,
    identify_prompt_version,
    load_system_prompt,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
MEMBER = "HS-2023-000303"   # synthetic: savings 1,200,000; active Development Loan

APPROVAL_CLAIM = "Good news: your loan has been approved for UGX 2,000,000."


def run_loop(module, message, runner, system_prompt="test prompt"):
    """Run either agent loop without touching persistent memory."""
    kwargs = dict(requester_role="member", requester_membership_number=MEMBER,
                  gemini_runner=runner)
    if module is loop_with_memory:
        kwargs["persist_memory"] = False
    return module.run_agent_loop(message, system_prompt, **kwargs)


def scripted_runner(actions, final_text):
    """Request the given tools in order (executed by the real tools), then answer."""
    queue = list(actions)
    seen_states = []

    def runner(user_message, system_prompt, requester_role="member",
               requester_membership_number=None, agent_state=None, **kwargs):
        seen_states.append(agent_state)
        if not queue:
            return {"final_text": final_text, "tool_calls": []}
        name, arguments = queue.pop(0)
        result = agent_tools._execute_tool(
            name, arguments, requester_role, requester_membership_number)
        return {"final_text": "", "tool_calls": [
            {"name": name, "arguments": arguments, "result": result, "executed": True}]}

    runner.seen_states = seen_states
    return runner


FULL_CASE_ACTIONS = [
    ("get_member_record", {"membership_number": MEMBER}),
    ("retrieve_policy", {"query": "Development Loan requirements",
                         "loan_product": "Development Loan"}),
    ("calculate_repayment", {"loan_product": "Development Loan",
                             "principal": 2_000_000, "term_months": 12}),
]


class DefectA_MemberSummary(unittest.TestCase):

    def test_summary_uses_real_record_schema(self):
        summary = summarize_member_record_for_model(
            get_member_record(MEMBER, "member", MEMBER))
        self.assertEqual(summary["savings_balance_ugx"], 1_200_000)
        self.assertEqual(summary["share_capital_ugx"], 50_000)
        self.assertEqual(summary["active_loan"]["outstanding_balance_ugx"], 2_500_000)
        self.assertEqual(summary["membership_start_date"], "2023-03-10")
        self.assertNotIn("full_name", summary)
        self.assertNotIn("fields_not_in_record", summary)

    def test_null_active_loan_is_stated_not_invented(self):
        summary = summarize_member_record_for_model(
            get_member_record("HS-2024-000101", "member", "HS-2024-000101"))
        self.assertEqual(summary["active_loan"], "none_recorded")

    def test_missing_fields_are_reported_not_zeroed(self):
        summary = summarize_member_record_for_model(
            {"membership_number": "HS-X", "guarantee_commitments": []})
        self.assertNotIn("savings_balance_ugx", summary)
        self.assertEqual(
            summary["fields_not_in_record"],
            ["membership_start_date", "savings_balance_ugx",
             "share_capital_ugx", "active_loan"],
        )

    def test_both_loops_send_financial_fields_to_model(self):
        for module in (loop, loop_with_memory):
            with self.subTest(loop=module.__name__):
                runner = scripted_runner(FULL_CASE_ACTIONS[:1], "Prepared for officer review.")
                run_loop(module, "Prepare my Development Loan case.", runner)
                model_view = runner.seen_states[1]["member_record_summary"]
                self.assertEqual(model_view["savings_balance_ugx"], 1_200_000)
                self.assertEqual(model_view["share_capital_ugx"], 50_000)
                self.assertEqual(model_view["active_loan"]["loan_product"], "Development Loan")
                self.assertNotIn("full_name", model_view)


class DefectB_PolicyDirectory(unittest.TestCase):

    def test_policy_dir_name_matches_repository_exactly(self):
        # os.listdir returns the real on-disk spelling, so this fails on any
        # OS if the code and the repository disagree on capitalisation.
        self.assertIn(POLICY_DIR.name, os.listdir(REPO_ROOT))
        self.assertEqual(POLICY_DIR.name, "Knowledge")

    def test_rag_index_uses_same_directory(self):
        import embeddings
        self.assertEqual(embeddings.KNOWLEDGE_DIR, POLICY_DIR)

    def test_known_policy_file_loads(self):
        result = retrieve_policy("Development Loan requirements",
                                 loan_product="Development Loan")
        self.assertNotIn("error", result)
        self.assertEqual([r["document"] for r in result["results"]], ["development_loan.md"])
        self.assertIn("Development Loan", result["results"][0]["content"])


class DefectC_OutputSafeguard(unittest.TestCase):

    def test_decision_claims_are_flagged(self):
        for text in (
            APPROVAL_CLAIM,
            "Your loan application has been rejected.",
            "We have disbursed UGX 2,000,000 to your account.",
            "Funds have been disbursed to your mobile money wallet.",
        ):
            with self.subTest(text=text):
                self.assertFalse(validate_agent_output(text)[0])

    def test_procedure_and_human_review_wording_passes(self):
        for text in (
            "Once your application is approved, funds are released within 3 working days.",
            "If your loan is approved, the first repayment is due 30 days after disbursement.",
            "The Relationship Officer will decide whether the application is approved.",
            "Requires human verification: final credit decision and approval by the Relationship Officer.",
            "The agent has not approved, rejected, scored, disbursed, or modified the loan.",
        ):
            with self.subTest(text=text):
                self.assertTrue(validate_agent_output(text)[0])

    def test_valid_case_summary_passes_unchanged(self):
        safe = ("### Case Summary\nIllustrative installment UGX 177,697.58. "
                "Once your application is approved by the Relationship Officer, "
                "funds are released per policy.\n### Human Review Required\nOfficer decides.")
        for module in (loop, loop_with_memory):
            with self.subTest(loop=module.__name__):
                trace = run_loop(module, "Prepare my Development Loan case.",
                                 scripted_runner(FULL_CASE_ACTIONS, safe))
                self.assertEqual(trace["final_state"]["case_summary"], safe)
                self.assertNotEqual(trace["final_state"]["stop_reason"],
                                    "prohibited_action_in_output")

    def test_decision_claim_is_withheld_from_output_and_trace(self):
        for module in (loop, loop_with_memory):
            with self.subTest(loop=module.__name__):
                trace = run_loop(module, "Prepare my Development Loan case.",
                                 scripted_runner(FULL_CASE_ACTIONS, APPROVAL_CLAIM))
                final = trace["final_state"]
                self.assertEqual(final["stop_reason"], "prohibited_action_in_output")
                self.assertTrue(final["human_handoff_required"])
                self.assertTrue(final["case_summary"].startswith(OUTPUT_WITHHELD_NOTICE))
                self.assertTrue(validate_agent_output(final["case_summary"])[0])
                self.assertNotIn(APPROVAL_CLAIM, json.dumps(trace, default=str))

    def test_safety_stop_is_not_downgraded_by_missing_requirements(self):
        claim = APPROVAL_CLAIM + " Guarantor details are missing; please provide them."
        trace = run_loop(loop_with_memory, "Prepare my Development Loan case.",
                         scripted_runner(FULL_CASE_ACTIONS, claim))
        self.assertTrue(trace["final_state"]["missing_requirements"])
        self.assertEqual(trace["final_state"]["stop_reason"], "prohibited_action_in_output")

    def test_cli_never_displays_the_claim(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = cli.CliSession("member", MEMBER, persist_memory=False,
                                     trace_dir=Path(tmp), system_prompt="test prompt")
            shown = []
            _, path = cli.run_request(session, "Prepare my Development Loan case.",
                                      gemini_runner=scripted_runner(FULL_CASE_ACTIONS, APPROVAL_CLAIM),
                                      out=shown.append)
            self.assertNotIn(APPROVAL_CLAIM, "\n".join(map(str, shown)))
            self.assertIn("RESPONSE WITHHELD BY OUTPUT GUARDRAIL", "\n".join(map(str, shown)))
            self.assertNotIn(APPROVAL_CLAIM, path.read_text(encoding="utf-8"))


class DefectD_PromptVersion(unittest.TestCase):

    def test_every_prompt_file_is_identified_by_its_content(self):
        for path in sorted(PROMPTS_DIR.glob("v*.md")):
            with self.subTest(prompt=path.name):
                self.assertEqual(identify_prompt_version(load_system_prompt(path)), path.stem)
        self.assertEqual(identify_prompt_version(load_system_prompt()), DEFAULT_PROMPT_VERSION)
        self.assertIsNone(identify_prompt_version("an unregistered prompt"))

    def test_tracer_has_no_hardcoded_version(self):
        self.assertIsNone(AgentTracer().prompt_version)

    def test_trace_records_the_prompt_actually_used(self):
        for module in (loop, loop_with_memory):
            for version in ("v1.0", "v1.2"):
                with self.subTest(loop=module.__name__, version=version):
                    prompt = load_system_prompt(PROMPTS_DIR / f"{version}.md")
                    trace = run_loop(module, "Prepare my Development Loan case.",
                                     scripted_runner([], "Prepared for officer review."),
                                     system_prompt=prompt)
                    self.assertEqual(trace["prompt_version"], version)

    def test_cli_run_meta_matches_loaded_prompt(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = cli.CliSession("member", MEMBER, persist_memory=False,
                                     trace_dir=Path(tmp))   # loads the real default prompt
            trace, path = cli.run_request(
                session, "Prepare my Development Loan case.",
                gemini_runner=scripted_runner([], "Prepared for officer review."),
                out=lambda *_: None)
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["run_meta"]["prompt_version"], DEFAULT_PROMPT_VERSION)
            self.assertEqual(saved["prompt_version"], DEFAULT_PROMPT_VERSION)


if __name__ == "__main__":
    unittest.main()
