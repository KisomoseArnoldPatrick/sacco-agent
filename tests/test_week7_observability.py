"""
Week 7 — tests for src/agent/observability.py and the model-failure handling
that feeds it.

Run from the repo root:
    python3 -m unittest tests.test_week7_observability -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from agent.loop_with_memory import _call_model_safely, run_agent_loop  # noqa: E402
from agent.observability import write_trace_events  # noqa: E402
from agent import tools  # noqa: E402

SECRET = "AQ.TEST-SECRET-KEY"


def scripted_runner():
    steps = iter([
        ("get_member_record", {"membership_number": "HS-2024-000101"}),
        ("retrieve_policy", {"query": "Development Loan requirements", "loan_product": "Development Loan"}),
        ("calculate_repayment", {"loan_product": "Development Loan", "principal": 2_000_000, "term_months": 12}),
    ])

    def runner(message, system_prompt, requester_role="member", requester_membership_number=None,
               tool_call_counts=None, max_calls_per_tool=2, agent_state=None):
        try:
            name, args = next(steps)
        except StopIteration:
            return {"final_text": "Case prepared for officer review. Illustrative only; not a loan decision.",
                    "tool_calls": []}
        if name == "get_member_record":
            result = tools.get_member_record(args["membership_number"], requester_role, requester_membership_number)
        elif name == "retrieve_policy":
            result = tools.retrieve_policy(**args)
        else:
            result = tools.calculate_repayment(**args)
        return {"final_text": "", "tool_calls": [{"name": name, "arguments": args, "result": result, "executed": True}]}

    return runner


class EventLog(unittest.TestCase):
    def setUp(self):
        self.trace = run_agent_loop(
            "My membership number is HS-2024-000101. Development Loan of UGX 2,000,000 over 12 months.",
            "test system prompt", "member", "HS-2024-000101",
            gemini_runner=scripted_runner(), persist_memory=False)

    def write(self, meta=None):
        path = Path(tempfile.mkdtemp()) / "events.jsonl"
        count = write_trace_events(self.trace, path, meta or {"scenario_id": "unit"})
        return path, count

    def test_every_line_is_valid_json(self):
        path, count = self.write()
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), count)
        for line in lines:
            json.loads(line)

    def test_run_has_start_end_and_each_tool_call(self):
        path, _ = self.write()
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        kinds = [e["event"] for e in events]
        self.assertEqual(kinds[0], "run_start")
        self.assertEqual(kinds[-1], "run_end")
        tool_events = [e for e in events if e["event"] == "tool_call"]
        self.assertEqual([e["tool"] for e in tool_events],
                         ["get_member_record", "retrieve_policy", "calculate_repayment"])

    def test_events_carry_model_prompt_retrieval_latency_and_outcome(self):
        path, _ = self.write()
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        self.assertTrue(all("prompt_sha256" in e and "model" in e for e in events))
        retrieval = next(e for e in events if e["event"] == "tool_call" and e["tool"] == "retrieve_policy")
        self.assertEqual(retrieval["retrieved_documents"], ["development_loan.md"])
        self.assertTrue(any(e.get("model_latency_ms") is not None for e in events if e["event"] == "model_call"))
        end = events[-1]
        self.assertEqual(end["stop_reason"], "case_complete")
        self.assertTrue(end["human_handoff_required"])

    def test_scenario_metadata_is_included(self):
        path, _ = self.write({"scenario_id": "N01", "label": "unit"})
        first = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(first["scenario_id"], "N01")

    def test_log_appends_rather_than_overwrites(self):
        path, first = self.write()
        write_trace_events(self.trace, path, {"scenario_id": "again"})
        self.assertEqual(len(path.read_text(encoding="utf-8").splitlines()), first * 2)


class ModelFailureHandling(unittest.TestCase):
    def test_exception_becomes_structured_error_not_a_crash(self):
        def failing(*a, **k):
            raise RuntimeError("Read timed out")
        outcome, latency, error = _call_model_safely(failing, "msg", "prompt")
        self.assertEqual(outcome["error"], "model_unavailable")
        self.assertEqual(outcome["tool_calls"], [])
        self.assertIsNotNone(error)
        self.assertGreaterEqual(latency, 0)

    def test_api_key_is_redacted_from_error_text(self):
        def failing(*a, **k):
            raise RuntimeError(f"503 Server Error for url: https://example.test/m:generate?key={SECRET}")
        outcome, _, error = _call_model_safely(failing, "msg", "prompt")
        self.assertNotIn(SECRET, outcome["final_text"])
        self.assertNotIn(SECRET, error)
        self.assertIn("key=REDACTED", error)

    def test_full_run_with_failing_model_stops_safely_and_leaks_nothing(self):
        def failing(*a, **k):
            raise RuntimeError(f"503 for url: https://example.test/x?key={SECRET}")
        trace = run_agent_loop("Prepare my Development Loan case.", "p", "member", "HS-2024-000101",
                               gemini_runner=failing, persist_memory=False)
        state = trace["final_state"]
        self.assertEqual(state["stop_reason"], "tool_failure:model_unavailable")
        self.assertTrue(state["human_handoff_required"])
        self.assertNotIn(SECRET, json.dumps(trace, default=str))


if __name__ == "__main__":
    unittest.main(verbosity=2)
