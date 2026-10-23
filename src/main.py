"""
SACCO Member-Case Preparation Agent — interactive command-line entry point.

Usage:
    python src/main.py
    python src/main.py --role member --membership-number HS-2023-000303

This module is a thin shell around the existing bounded agent in
agent/loop_with_memory.py. It does not retrieve policy, call tools, check
guardrails, or update memory itself; run_agent_loop() already does all of
that. The CLI only:

- collects the requester identity once per session;
- forwards each request to run_agent_loop();
- displays each model/tool round as it happens (via the loop's existing
  gemini_runner injection hook) and the final outcome from the returned trace;
- saves each run's trace as JSON and appends its events to a JSONL log.

The agent is advisory only. It never approves, rejects, scores, or disburses
loans, and never modifies member accounts.
"""

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

SRC_DIR = Path(__file__).resolve().parent
REPO_ROOT = SRC_DIR.parent

for directory in (REPO_ROOT, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


from baseline_chat import load_system_prompt  # noqa: E402
from agent_tools import call_gemini_with_tools  # noqa: E402
from agent.loop_with_memory import (  # noqa: E402
    APPROVED_TOOLS,
    MAX_CALLS_PER_TOOL,
    MAX_ITERATIONS,
    _memory_context,
    _summarize_tool_result,
    run_agent_loop,
)
from agent.conversation import respond, route_message  # noqa: E402
from agent.memory import CaseMemoryStore, MemoryAccessError  # noqa: E402
from agent.observability import now_utc_iso, write_trace_events  # noqa: E402


DEFAULT_TRACE_DIR = REPO_ROOT / "evidence" / "traces" / "cli_runs"
DEFAULT_MEMORY_PATH = REPO_ROOT / "evidence" / "memory" / "case_history.json"
EVENTS_LOG_NAME = "cli_events.jsonl"

HELP_TEXT = """Commands:
  /new    start a new case
  /case   show the current case ID
  /trace  show the path of the last saved trace
  /help   show this help
  /exit   end the session (also /quit, Ctrl+C, Ctrl+Z/Ctrl+D)"""


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------

def new_case_id() -> str:
    """Return a unique case ID for a CLI-created case."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"cli-{stamp}-{uuid.uuid4().hex[:6]}"


class CliSession:
    """Requester identity and settings shared by every request in one session."""

    def __init__(
        self,
        requester_role: str,
        membership_number: str | None,
        case_id: str | None = None,
        persist_memory: bool = True,
        memory_path: Path = DEFAULT_MEMORY_PATH,
        trace_dir: Path = DEFAULT_TRACE_DIR,
        system_prompt: str | None = None,
    ):
        self.requester_role = requester_role
        self.membership_number = membership_number or None
        self.case_id = case_id or new_case_id()
        self.persist_memory = persist_memory
        self.memory_path = Path(memory_path)
        self.trace_dir = Path(trace_dir)
        self.system_prompt = (
            system_prompt if system_prompt is not None else load_system_prompt()
        )
        self.prompt_sha256 = hashlib.sha256(
            self.system_prompt.encode("utf-8")
        ).hexdigest()
        self.last_trace_path: Path | None = None
        self.case_totals = self._empty_totals()

    @staticmethod
    def _empty_totals() -> dict:
        # Statistics for the current case in this session. Each request still
        # has its own MAX_ITERATIONS / MAX_CALLS_PER_TOOL budget.
        return {
            "requests": 0,
            "iterations": 0,
            "tool_calls": {name: 0 for name in sorted(APPROVED_TOOLS)},
        }

    def start_new_case(self) -> None:
        self.case_id = new_case_id()
        self.case_totals = self._empty_totals()

    @property
    def resumes_case(self) -> bool:
        # Members continue their own saved case across requests. For officers,
        # resume_saved_case selects the loop's read-only history path, which
        # requires a trusted authorization list this CLI does not have.
        return self.requester_role == "member"

    def case_context(self) -> dict | None:
        """
        Saved history for the current case, read through the owner-only
        memory API. None when memory is off, the requester is not the owner,
        or nothing has been saved yet.
        """
        if not (self.persist_memory and self.resumes_case and self.membership_number):
            return None
        try:
            saved = CaseMemoryStore(self.memory_path).load(
                self.case_id, self.membership_number, actor_role="member"
            )
        except (MemoryAccessError, ValueError, OSError):
            return None
        return _memory_context(saved) if saved else None


# ---------------------------------------------------------------------------
# Live display
# ---------------------------------------------------------------------------

def _format_summary(summary: dict) -> str:
    return ", ".join(
        f"{key}={value}" for key, value in summary.items() if value is not None
    )


def live_runner(base_runner: Callable, out: Callable = print) -> Callable:
    """
    Wrap the model runner so each round is shown while the loop runs.

    The wrapper passes arguments and results through unchanged. "executed"
    is the flag set by agent_tools after the tool actually ran (or was
    blocked before running); it is never inferred from the model's request.
    Exceptions are re-raised so the loop's existing safe-failure handling
    still applies.
    """

    def runner(*args, **kwargs):
        iteration = (kwargs.get("agent_state") or {}).get("iteration_count")
        prefix = f"  [iteration {iteration}/{MAX_ITERATIONS}]"
        out(f"{prefix} consulting model...")

        try:
            outcome = base_runner(*args, **kwargs)
        except Exception as exc:
            out(f"{prefix} model call FAILED ({type(exc).__name__}); "
                "the loop will stop and hand off to a human.")
            raise

        if not isinstance(outcome, dict):
            out(f"{prefix} model returned an invalid response.")
            return outcome

        if outcome.get("error"):
            out(f"{prefix} model returned error: {outcome['error']}")

        tool_calls = outcome.get("tool_calls") or []
        if not tool_calls:
            out(f"{prefix} model returned its final response (no tool call).")
            return outcome

        for call in tool_calls:
            name = call.get("name", "")
            result = call.get("result", {})
            summary = _summarize_tool_result(name, result)
            if not call.get("executed"):
                status = "BLOCKED (not executed)"
            elif isinstance(result, dict) and result.get("error"):
                status = "EXECUTED -> returned error"
            else:
                status = "EXECUTED"
            out(f"{prefix} tool {name}: {status}")
            if summary:
                out(f"      result: {_format_summary(summary)}")

        return outcome

    return runner


def display_outcome(
    trace: dict, out: Callable = print, case_totals: dict | None = None
) -> None:
    """Show guardrail events, policy evidence, and the final outcome of a run."""

    final = trace.get("final_state") or {}

    # Guardrail steps (iteration 0) never reach the model, so the live
    # runner cannot show them; report them from the trace.
    for step in trace.get("steps", []):
        if step.get("event"):
            out(f"  [guardrail] {step['event']}: blocked before any model "
                "or tool call.")
            if step.get("final_text"):
                out(f"  [guardrail] {step['final_text']}")
        if step.get("model_error"):
            out(f"  [iteration {step.get('iteration')}] model error: "
                f"{step['model_error']}")

    excerpts = [
        item for item in final.get("policy_excerpts", [])
        if isinstance(item, dict)
    ]
    if excerpts:
        out("\nPolicy evidence retrieved (RAG):")
        seen = set()
        for item in excerpts:
            document = item.get("document")
            if document in seen:
                continue
            seen.add(document)
            terms = ", ".join(item.get("matched_terms", [])[:8])
            out(f"  - {document}" + (f" (matched: {terms})" if terms else ""))

    memory = trace.get("memory") or {}
    counts = final.get("tool_call_counts", {})

    out("\nOutcome:")
    out(f"  Stop reason:     {final.get('stop_reason')}")
    out(f"  Human handoff:   "
        f"{'REQUIRED' if final.get('human_handoff_required') else 'not required'}")
    out(f"  This request:    {final.get('iteration_count', 0)}/{MAX_ITERATIONS} iterations; "
        "tool calls " + ", ".join(
            f"{name}={count}/{MAX_CALLS_PER_TOOL}" for name, count in sorted(counts.items())
        ))
    if case_totals:
        out(f"  Case so far:     {case_totals['requests']} request(s), "
            f"{case_totals['iterations']} iterations, tool calls "
            + ", ".join(f"{n}={c}" for n, c in case_totals["tool_calls"].items()))
    memory_status = memory.get("status")
    if trace.get("route") in ("information", "safety_check"):
        memory_status = "not used (not a case-preparation request)"
    out(f"  Memory:          {memory_status}")
    if memory.get("error"):
        out(f"  Memory error:    {memory['error']}")

    heading = {
        "information": "Answer",
        "safety_check": "Response",
    }.get(trace.get("route"), "Case-preparation response")
    out(f"\n{heading}:")
    out("-" * 72)
    out(final.get("case_summary") or "(no response)")
    out("-" * 72)


# ---------------------------------------------------------------------------
# Trace persistence
# ---------------------------------------------------------------------------

def save_trace(session: CliSession, trace: dict) -> Path:
    """
    Save one run's trace (the dict returned by run_agent_loop) as JSON and
    append its events to the JSONL event log.

    Filenames include a UTC timestamp and the run ID, and are opened in
    exclusive-create mode, so earlier evidence is never overwritten.
    """

    trace["run_meta"] = {
        "interface": "cli",
        "model": os.environ.get("GEMINI_MODEL", "gemini-3.6-flash"),
        # Identified by the loop from the prompt text actually sent.
        "prompt_version": trace.get("prompt_version"),
        "prompt_sha256": session.prompt_sha256,
        "max_iterations": MAX_ITERATIONS,
        "max_calls_per_tool": MAX_CALLS_PER_TOOL,
        "requester_role": session.requester_role,
        "case_id": session.case_id,
        # "agent_loop" or "direct_response" (no model or tool call).
        "handling": trace.get("handling", "agent_loop"),
        "route": trace.get("route", "case_preparation"),
        "request_type": trace.get("request_type"),
        "budget_scope": "per_request",
        "case_totals_after_request": json.loads(json.dumps(session.case_totals)),
    }

    run_id = trace.get("run_id") or f"run-{uuid.uuid4().hex[:12]}"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")

    session.trace_dir.mkdir(parents=True, exist_ok=True)
    path = session.trace_dir / f"{stamp}_{run_id}.json"

    with path.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(trace, indent=2, ensure_ascii=False, default=str))
        handle.write("\n")

    write_trace_events(
        trace,
        session.trace_dir / EVENTS_LOG_NAME,
        meta={"run_id": run_id, "run_latency_ms": trace.get("elapsed_ms")},
    )

    session.last_trace_path = path
    return path


# ---------------------------------------------------------------------------
# One request
# ---------------------------------------------------------------------------

def run_request(
    session: CliSession,
    message: str,
    gemini_runner: Callable | None = None,
    out: Callable = print,
    route: str = "case_preparation",
) -> tuple[dict, Path]:
    """
    Run one request through the bounded agent, display it, and save its trace.

    route is "case_preparation", "information" or "safety_check" (see
    agent.conversation.route_message). Only case preparation reads and writes
    the case memory, so a question or a blocked request cannot alter the
    active case's saved progress or outstanding requirements.

    gemini_runner defaults to the real Gemini tool-calling runner. Tests may
    inject a deterministic runner, exactly as with run_agent_loop().
    """

    runner = live_runner(gemini_runner or call_gemini_with_tools, out)
    is_case_work = route == "case_preparation"

    trace = run_agent_loop(
        member_message=message,
        system_prompt=session.system_prompt,
        requester_role=session.requester_role,
        requester_membership_number=session.membership_number,
        gemini_runner=runner,
        case_id=session.case_id,
        memory_store_path=session.memory_path,
        resume_saved_case=session.resumes_case and is_case_work,
        persist_memory=session.persist_memory and is_case_work,
        scenario_id="cli_session",
        # Each message is a new request: saved history is loaded as context,
        # but the request gets its own iteration and tool-call budget.
        per_request_budget=True,
        request_type="information" if route == "information" else "case_preparation",
    )
    trace["route"] = route

    totals = None
    if is_case_work:
        final = trace.get("final_state") or {}
        totals = session.case_totals
        totals["requests"] += 1
        totals["iterations"] += int(final.get("iteration_count", 0))
        for name, count in (final.get("tool_call_counts") or {}).items():
            totals["tool_calls"][name] = totals["tool_calls"].get(name, 0) + int(count)

    display_outcome(trace, out, totals)
    path = save_trace(session, trace)
    out(f"\nTrace saved: {path}")
    return trace, path


def run_direct_response(
    session: CliSession,
    message: str,
    intent: str,
    out: Callable = print,
) -> tuple[dict, Path]:
    """
    Answer a conversational message without the model or any tool, and save
    a trace that records exactly that: no iterations, no tool calls, and
    saved case history read (never written).
    """

    context = session.case_context()
    reply = respond(intent, session.case_id, context, session.persist_memory)
    stamp = now_utc_iso()

    trace = {
        "run_id": f"run-{uuid.uuid4().hex[:12]}",
        "scenario_id": "cli_session",
        "handling": "direct_response",
        "route": "direct",
        "intent": intent,
        "prompt_version": None,
        "started_at": stamp,
        "ended_at": stamp,
        "elapsed_ms": 0.0,
        "steps": [],
        "events": [],
        "memory": {
            "enabled": session.persist_memory,
            "status": "history_read" if context else "not_used",
            "case_id": session.case_id,
        },
        "final_state": {
            "member_message": message,
            "case_id": session.case_id,
            "requester_role": session.requester_role,
            "requester_membership_number": session.membership_number,
            "iteration_count": 0,
            "tool_call_counts": {name: 0 for name in sorted(APPROVED_TOOLS)},
            "tool_calls_made": [],
            "policy_excerpts": [],
            "stop_reason": f"direct_response:{intent}",
            "human_handoff_required": False,
            "case_summary": reply,
        },
    }

    out(f"  [direct response: {intent}] answered without the model or any tool.")
    out("")
    out(reply)
    path = save_trace(session, trace)
    out(f"\nTrace saved: {path}")
    return trace, path


def handle_message(
    session: CliSession,
    message: str,
    gemini_runner: Callable | None = None,
    out: Callable = print,
) -> tuple[dict, Path]:
    """
    Route one user message (see agent.conversation.route_message):
    direct replies need no model or tool; information questions and case
    requests go to the bounded agent loop; anything the prohibited-action or
    prompt-injection guardrails flag goes to the loop, which blocks it before
    any model or tool call.
    """

    message = message.replace("﻿", "").strip()
    route, intent = route_message(message)

    if route == "direct":
        return run_direct_response(session, message, intent, out)
    return run_request(session, message, gemini_runner=gemini_runner, out=out,
                       route=route)


# ---------------------------------------------------------------------------
# Interactive loop
# ---------------------------------------------------------------------------

def _prompt_identity(args: argparse.Namespace) -> tuple[str, str | None]:
    role = args.role
    while role not in ("member", "officer"):
        role = input("Requester role [member/officer] (default member): ").strip().lower() or "member"

    number = args.membership_number
    if number is None:
        label = "Your membership number" if role == "member" else "Your staff/membership number (optional)"
        number = input(f"{label}: ").strip() or None
    return role, number


def interactive(session: CliSession) -> None:
    out = print
    out("=" * 72)
    out("SACCO MEMBER-CASE PREPARATION AGENT")
    out("Advisory only: prepares cases for a Relationship Officer. It does not")
    out("approve, reject, or disburse loans, or change any account.")
    out("=" * 72)
    out(f"Role: {session.requester_role}   "
        f"Membership number: {session.membership_number or '(none)'}")
    out(f"Case ID: {session.case_id}   "
        f"Memory: {'on' if session.persist_memory else 'off'}")
    out(f"Traces: {session.trace_dir}")
    if not os.environ.get("GEMINI_API_KEY"):
        out("WARNING: GEMINI_API_KEY is not set; model calls will fail and "
            "requests will be handed off to a human.")
    out("Type /help for commands.\n")

    while True:
        try:
            # Piped input from PowerShell can start with a byte-order mark.
            message = input("request> ").replace("﻿", "").strip()
        except (EOFError, KeyboardInterrupt):
            out("\nSession ended.")
            return

        if not message:
            continue

        command = message.lower()
        if command in ("/exit", "/quit"):
            out("Session ended.")
            return
        if command == "/help":
            out(HELP_TEXT)
            continue
        if command == "/case":
            out(f"Case ID: {session.case_id}")
            continue
        if command == "/trace":
            out(f"Last trace: {session.last_trace_path or '(none yet)'}")
            continue
        if command == "/new":
            session.start_new_case()
            out(f"Started new case: {session.case_id}")
            continue

        out("")
        try:
            handle_message(session, message, out=out)
        except KeyboardInterrupt:
            out("\nRequest interrupted; no trace was saved for it.")
        out("")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive CLI for the SACCO member-case preparation agent.",
    )
    parser.add_argument("--role", choices=["member", "officer"],
                        help="Requester role (prompted if omitted).")
    parser.add_argument("--membership-number",
                        help="Requester's membership number (prompted if omitted).")
    parser.add_argument("--case-id",
                        help="Resume an existing saved case instead of starting a new one.")
    parser.add_argument("--no-memory", action="store_true",
                        help="Do not read or write persistent case memory.")
    parser.add_argument("--memory-path", type=Path, default=DEFAULT_MEMORY_PATH,
                        help="Persistent case-memory JSON file.")
    parser.add_argument("--trace-dir", type=Path, default=DEFAULT_TRACE_DIR,
                        help="Directory for per-run JSON traces.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # Policy text and model output may contain characters the console code
    # page cannot encode; never crash the session over that.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = parse_args(argv)
    try:
        role, number = _prompt_identity(args)
    except (EOFError, KeyboardInterrupt):
        print("\nSession ended.")
        return 0

    session = CliSession(
        requester_role=role,
        membership_number=number,
        case_id=args.case_id,
        persist_memory=not args.no_memory,
        memory_path=args.memory_path,
        trace_dir=args.trace_dir,
    )
    interactive(session)
    return 0


if __name__ == "__main__":
    sys.exit(main())
