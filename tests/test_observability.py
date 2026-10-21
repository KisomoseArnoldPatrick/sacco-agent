"""
Unit and integration tests for Week 7 Observability and Tracing.

Covers:
- Unique run ID and scenario ID assignment.
- Structured event recording and timestamps.
- Execution latency tracking (microsecond/millisecond precision).
- Sensitive PII redaction (name masking, data minimization).
- JSON and JSON Lines (.jsonl) trace output generation.
- Trace generation on successful, failed, and blocked execution paths.
- Fault-tolerant model invocation and secret redaction (_call_model_safely).
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

from agent.observability import (
    AgentTracer,
    mask_name,
    sanitize_member_record,
    sanitize_trace_state,
    now_utc_iso,
)
from agent.loop_with_memory import run_agent_loop, _call_model_safely


SECRET = "AQ.TEST-SECRET-KEY"


class TestObservability(unittest.TestCase):

    def test_01_run_id_and_scenario_id_assignment(self):
        tracer = AgentTracer(scenario_id="TEST-001", run_id="custom-run-123")
        self.assertEqual(tracer.scenario_id, "TEST-001")
        self.assertEqual(tracer.run_id, "custom-run-123")
        self.assertIsNotNone(tracer.start_wall_time)

        # Default run_id should be auto-generated
        tracer_auto = AgentTracer(scenario_id="TEST-002")
        self.assertTrue(tracer_auto.run_id.startswith("run-"))

    def test_02_structured_event_recording(self):
        tracer = AgentTracer(scenario_id="TEST-002")
        tracer.record_event("test_event", {"metric": 42, "status": "active"})
        self.assertEqual(len(tracer.events), 1)
        ev = tracer.events[0]
        self.assertEqual(ev["event_type"], "test_event")
        self.assertEqual(ev["details"]["metric"], 42)
        self.assertIn("offset_ms", ev)
        self.assertIn("timestamp", ev)

    def test_03_latency_and_duration_measurement(self):
        tracer = AgentTracer(scenario_id="TEST-003")
        trace_dict = tracer.end_run(stop_reason="case_complete", human_handoff_required=True)
        self.assertGreaterEqual(tracer.elapsed_ms, 0.0)
        self.assertEqual(trace_dict["metadata"]["elapsed_ms"], tracer.elapsed_ms)
        self.assertEqual(trace_dict["metadata"]["stop_reason"], "case_complete")

    def test_04_pii_masking_name(self):
        self.assertEqual(mask_name("Alice Namuli"), "A***e N****i")
        self.assertEqual(mask_name("Carol Atim"), "C***l A**m")
        self.assertEqual(mask_name("Brian Okello"), "B***n O****o")
        self.assertEqual(mask_name("Jo"), "J*")
        self.assertEqual(mask_name(""), "[ANONYMIZED]")

    def test_05_pii_sanitization_in_member_record(self):
        raw_record = {
            "full_name": "David Ssekandi",
            "savings_balance_ugx": 3000000,
            "phone": "+256700000000",
            "national_id": "CM123456789",
            "share_capital_ugx": 80000,
        }
        sanitized = sanitize_member_record(raw_record)
        self.assertEqual(sanitized["full_name"], "D***d S******i")
        self.assertEqual(sanitized["phone"], "[REDACTED_PII]")
        self.assertEqual(sanitized["national_id"], "[REDACTED_PII]")
        self.assertEqual(sanitized["savings_balance_ugx"], 3000000)

    def test_06_state_snapshot_redacts_pii(self):
        state = {
            "member_message": "Hello",
            "member_record": {
                "full_name": "Grace Nabirye",
                "savings_balance_ugx": 900000,
            },
        }
        sanitized_state = sanitize_trace_state(state)
        self.assertEqual(sanitized_state["member_record"]["full_name"], "G***e N*****e")
        # Ensure deep copy: modifying sanitized does not mutate original
        sanitized_state["member_record"]["full_name"] = "MODIFIED"
        self.assertEqual(state["member_record"]["full_name"], "Grace Nabirye")

    def test_07_jsonl_log_streaming_export(self):
        tracer = AgentTracer(scenario_id="JSONL-01")
        tracer.end_run(stop_reason="test_stop", human_handoff_required=False)
        with tempfile.TemporaryDirectory() as tmp_dir:
            jsonl_file = Path(tmp_dir) / "test_stream.jsonl"
            tracer.append_to_jsonl(jsonl_file)
            self.assertTrue(jsonl_file.exists())
            lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
            self.assertEqual(len(lines), 1)
            entry = json.loads(lines[0])
            self.assertEqual(entry["scenario_id"], "JSONL-01")
            self.assertEqual(entry["stop_reason"], "test_stop")

    def test_08_trace_generation_on_blocked_request(self):
        trace = run_agent_loop(
            member_message="Please approve this loan.",
            system_prompt="prompt",
            requester_role="member",
            requester_membership_number="HS-2023-000303",
            persist_memory=False,
            scenario_id="TRACE-BLOCKED-01",
        )
        self.assertIn("run_id", trace)
        self.assertEqual(trace["scenario_id"], "TRACE-BLOCKED-01")
        self.assertIn("events", trace)
        self.assertIn("elapsed_ms", trace)
        self.assertEqual(trace["final_state"]["stop_reason"], "prohibited_action_requested")

    def test_09_trace_generation_on_validation_failure(self):
        trace = run_agent_loop(
            member_message="",
            system_prompt="prompt",
            requester_role="member",
            requester_membership_number="HS-2023-000303",
            persist_memory=False,
            scenario_id="TRACE-VAL-01",
        )
        self.assertIn("run_id", trace)
        self.assertEqual(trace["scenario_id"], "TRACE-VAL-01")
        self.assertEqual(trace["final_state"]["stop_reason"], "validation_error:empty_request")
        self.assertIn("events", trace)
        self.assertTrue(any(e["event_type"] == "validation_failed" for e in trace["events"]))

    def test_10_safe_model_call_catches_exception_and_redacts_api_key(self):
        def failing(*a, **k):
            raise RuntimeError(f"503 Server Error for url: https://example.test/m:generate?key={SECRET}")
        outcome, latency, error = _call_model_safely(failing, "msg", "prompt")
        self.assertEqual(outcome["error"], "model_unavailable")
        self.assertEqual(outcome["tool_calls"], [])
        self.assertGreaterEqual(latency, 0.0)
        self.assertNotIn(SECRET, outcome["final_text"])
        self.assertNotIn(SECRET, error)
        self.assertIn("key=REDACTED", error)

    def test_11_failing_model_stops_safely_and_leaks_no_secrets(self):
        def failing(*a, **k):
            raise RuntimeError(f"503 Server Error: connection failure for url: https://example.test/x?key={SECRET}")
        trace = run_agent_loop(
            "Prepare my Development Loan case.",
            "test system prompt",
            "member",
            "HS-2024-000101",
            gemini_runner=failing,
            persist_memory=False,
        )
        state = trace["final_state"]
        self.assertEqual(state["stop_reason"], "tool_failure:model_unavailable")
        self.assertTrue(state["human_handoff_required"])
        self.assertNotIn(SECRET, json.dumps(trace, default=str))

    def test_12_successful_model_call_measures_latency_and_returns_clean_result(self):
        def successful(*a, **k):
            return {"final_text": "Case summary for officer.", "tool_calls": []}
        outcome, latency, error = _call_model_safely(successful, "msg", "prompt")
        self.assertEqual(outcome["final_text"], "Case summary for officer.")
        self.assertEqual(outcome["tool_calls"], [])
        self.assertIsNone(error)
        self.assertGreaterEqual(latency, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
