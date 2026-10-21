"""
Week 7 — Observability: turn an agent run trace into structured JSONL events.

One line per event. Each event carries what an engineer needs to explain a run:
which model and prompt version, what was retrieved, which tool was called with
what arguments, how long the model took, what failed, and how the run ended.

Event types:
    run_start, model_call, tool_call, guardrail, run_end

Usage:
    from agent.observability import write_trace_events
    write_trace_events(trace, "evidence/logs/agent_events.jsonl", {"label": "demo"})
"""

import json
from datetime import datetime, timezone
from pathlib import Path


def _event(kind: str, base: dict, **fields) -> dict:
    return {"ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "event": kind, **base, **fields}


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
