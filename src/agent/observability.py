"""
Week 7 — Observability, Structured Tracing, and Sensitive Data Redaction.

Features:
- Unique run ID (UUID) and scenario ID correlation.
- Microsecond/millisecond execution timing for total run and individual tool calls.
- Structured event logging (start, validation, tool calls, errors, stops, handoffs).
- PII sanitization and masking (member names, sensitive account details).
- Machine-readable JSON Lines (.jsonl) persistence and JSON report export.
"""

import copy
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def now_utc_iso() -> str:
    """Return the current UTC time in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def mask_name(name: str) -> str:
    """Mask a person's full name to protect PII while allowing debugging."""
    if not name or not isinstance(name, str):
        return "[ANONYMIZED]"
    parts = name.strip().split()
    if not parts:
        return "[ANONYMIZED]"
    masked = []
    for p in parts:
        if len(p) <= 2:
            masked.append(p[0] + "*")
        else:
            masked.append(p[0] + "*" * (len(p) - 2) + p[-1])
    return " ".join(masked)


def sanitize_member_record(record: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Return a sanitized copy of a member record with PII redacted."""
    if not record or not isinstance(record, dict):
        return None
    sanitized = copy.deepcopy(record)
    if "full_name" in sanitized:
        sanitized["full_name"] = mask_name(sanitized["full_name"])
    # Omit unnecessary raw address or phone if present
    for sensitive_key in ("phone", "email", "national_id", "nin", "address"):
        if sensitive_key in sanitized:
            sanitized[sensitive_key] = "[REDACTED_PII]"
    return sanitized


def sanitize_trace_state(state: Dict[str, Any]) -> Dict[str, Any]:
    """Create a deepcopy of state with sensitive PII safely redacted."""
    if not isinstance(state, dict):
        return state
    sanitized = copy.deepcopy(state)
    if sanitized.get("member_record"):
        sanitized["member_record"] = sanitize_member_record(sanitized["member_record"])
    return sanitized


class AgentTracer:
    """Structured observability tracer for one SACCO agent execution run."""

    def __init__(
        self,
        scenario_id: Optional[str] = None,
        run_id: Optional[str] = None,
        prompt_version: str = "v1.2",
    ):
        self.run_id = run_id or f"run-{uuid.uuid4().hex[:12]}"
        self.scenario_id = scenario_id
        self.prompt_version = prompt_version
        self.start_wall_time = now_utc_iso()
        self.start_perf = time.perf_counter()
        self.end_perf: Optional[float] = None
        self.elapsed_ms: float = 0.0

        self.events: List[Dict[str, Any]] = []
        self.steps: List[Dict[str, Any]] = []
        self.metadata: Dict[str, Any] = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "prompt_version": self.prompt_version,
            "started_at": self.start_wall_time,
            "ended_at": None,
            "elapsed_ms": None,
            "total_iterations": 0,
            "tool_calls_count": 0,
            "stop_reason": None,
            "human_handoff_required": False,
            "safety_violations_count": 0,
        }

    def record_event(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Record a milestone or lifecycle event with timestamp and duration offset."""
        offset_ms = round((time.perf_counter() - self.start_perf) * 1000, 2)
        event_record = {
            "timestamp": now_utc_iso(),
            "offset_ms": offset_ms,
            "event_type": event_type,
            "details": details or {},
        }
        self.events.append(event_record)

    def record_step(
        self,
        iteration: int,
        event_name: str,
        state_before: Optional[Dict[str, Any]],
        model_state: Optional[Dict[str, Any]],
        tool_calls: List[Dict[str, Any]],
        final_text: str,
        state_after: Optional[Dict[str, Any]],
    ) -> None:
        """Record a complete loop iteration step with sanitized state snapshots."""
        step = {
            "iteration": iteration,
            "event": event_name,
            "timestamp": now_utc_iso(),
            "state_before": sanitize_trace_state(state_before) if state_before else None,
            "model_state": copy.deepcopy(model_state) if model_state else None,
            "tool_calls": copy.deepcopy(tool_calls),
            "final_text": final_text,
            "state_after": sanitize_trace_state(state_after) if state_after else None,
        }
        self.steps.append(step)

    def end_run(
        self,
        stop_reason: str,
        human_handoff_required: bool,
        final_state: Optional[Dict[str, Any]] = None,
        final_output: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Finalize the run, compute duration, and return the complete structured trace."""
        self.end_perf = time.perf_counter()
        self.elapsed_ms = round((self.end_perf - self.start_perf) * 1000, 2)
        end_wall_time = now_utc_iso()

        self.metadata["ended_at"] = end_wall_time
        self.metadata["elapsed_ms"] = self.elapsed_ms
        self.metadata["stop_reason"] = stop_reason
        self.metadata["human_handoff_required"] = human_handoff_required

        if final_state:
            self.metadata["total_iterations"] = final_state.get("iteration_count", len(self.steps))
            self.metadata["tool_calls_count"] = len(final_state.get("tool_calls_made", []))

        self.record_event(
            "run_completed",
            {
                "stop_reason": stop_reason,
                "human_handoff_required": human_handoff_required,
                "elapsed_ms": self.elapsed_ms,
            },
        )

        trace_dict = {
            "metadata": self.metadata,
            "events": self.events,
            "steps": self.steps,
            "final_output": final_output,
            "final_state": sanitize_trace_state(final_state) if final_state else None,
        }
        return trace_dict

    def save_trace_json(self, output_path: Path) -> Path:
        """Save structured trace as formatted JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        trace_data = {
            "metadata": self.metadata,
            "events": self.events,
            "steps": self.steps,
        }
        output_path.write_text(
            json.dumps(trace_data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return output_path

    def append_to_jsonl(self, jsonl_path: Path) -> Path:
        """Append this run as a single JSON line for log streaming."""
        jsonl_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "run_id": self.run_id,
            "scenario_id": self.scenario_id,
            "prompt_version": self.prompt_version,
            "started_at": self.start_wall_time,
            "ended_at": self.metadata["ended_at"],
            "elapsed_ms": self.elapsed_ms,
            "stop_reason": self.metadata["stop_reason"],
            "human_handoff_required": self.metadata["human_handoff_required"],
            "events_count": len(self.events),
            "steps_count": len(self.steps),
        }
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return jsonl_path


def _event(kind: str, base: dict, **fields) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": kind,
        **base,
        **fields,
    }


def write_trace_events(trace: dict, log_path, meta: dict | None = None) -> int:
    """Append the events for one run to a JSONL file. Returns the number written."""
    meta = meta or {}
    run_meta = trace.get("run_meta", {})
    final = trace.get("final_state", {})
    base = {
        "case_id": final.get("case_id") or trace.get("memory", {}).get("case_id"),
        "model": run_meta.get("model"),
        "prompt_sha256": run_meta.get("prompt_sha256"),
        **{k: v for k, v in meta.items() if k != "run_latency_ms"},
    }
    events = [_event("run_start", base,
                     requester_role=final.get("requester_role"),
                     limits={"max_iterations": run_meta.get("max_iterations"),
                             "max_calls_per_tool": run_meta.get("max_calls_per_tool")})]

    for step in trace.get("steps", []):
        iteration = step.get("iteration")
        if step.get("event"):  # preflight guard blocked the run
            events.append(_event("guardrail", base, iteration=iteration, guardrail=step["event"],
                                 stop_reason=step.get("state_after", {}).get("stop_reason")))
            continue
        tool_calls = step.get("tool_calls", [])
        events.append(_event(
            "model_call", base, iteration=iteration,
            model_latency_ms=step.get("model_latency_ms"),
            action="tool_request" if tool_calls else "final_text",
            requested_tool=tool_calls[0]["name"] if tool_calls else None,
            error=("model_unavailable" if step.get("model_error") else None)))
        for call in tool_calls:
            summary = call.get("result_summary", {}) or {}
            events.append(_event(
                "tool_call", base, iteration=iteration, tool=call.get("name"),
                arguments=call.get("arguments"), executed=call.get("executed"),
                error=summary.get("error"),
                retrieved_documents=summary.get("documents"),
                result_summary={k: v for k, v in summary.items() if k not in ("documents",)}))
        if step.get("guardrail"):
            events.append(_event("guardrail", base, iteration=iteration, guardrail=step["guardrail"],
                                 stop_reason=step.get("state_after", {}).get("stop_reason")))

    events.append(_event(
        "run_end", base, stop_reason=final.get("stop_reason"),
        human_handoff_required=final.get("human_handoff_required"),
        iterations=final.get("iteration_count"),
        tool_call_counts=final.get("tool_call_counts"),
        run_latency_ms=meta.get("run_latency_ms")))

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")
    return len(events)


