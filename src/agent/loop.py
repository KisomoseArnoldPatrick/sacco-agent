"""
Week 5 — Bounded SACCO case-preparation agent.

Implements:

    Sense/Context
        ↓
    Plan/Decide
        ↓
    Act/Tool
        ↓
    Observe
        ↓
    Stop/Re-plan

The workflow is bounded by:
- maximum iterations;
- maximum calls per tool;
- approved tools only;
- explicit stop conditions;
- human handoff.

Gemini chooses the next approved action, but Python enforces
the safety limits and executes the actual tools.
"""

import copy
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"

for directory in (REPO_ROOT, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


from baseline_chat import identify_prompt_version, load_system_prompt  # noqa: E402
from agent_tools import call_gemini_with_tools  # noqa: E402
from agent.tools import summarize_member_record_for_model  # noqa: E402
from agent.guardrails import (  # noqa: E402
    validate_input_request,
    detect_prohibited_action,
    detect_prompt_injection,
    validate_agent_output,
    validate_tool_allowlist,
    OUTPUT_WITHHELD_NOTICE,
    PREFLIGHT_REFUSAL,
)
from agent.observability import (  # noqa: E402
    AgentTracer,
    sanitize_member_record,
    sanitize_trace_state,
    now_utc_iso,
)


# ---------------------------------------------------------------------------
# Week 5 limits
# ---------------------------------------------------------------------------

MAX_ITERATIONS = 6
MAX_CALLS_PER_TOOL = 2


APPROVED_TOOLS = {
    "get_member_record",
    "retrieve_policy",
    "calculate_repayment",
}


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def new_state(
    member_message: str,
    requester_role: str,
    requester_membership_number: str | None,
) -> dict:
    """
    Create fresh state for ONE agent request.

    Tool-call counts reset for every new request.
    """

    return {
        "member_message": member_message,
        "requester_role": requester_role,
        "requester_membership_number": requester_membership_number,

        "member_record": None,
        "policy_excerpts": [],
        "repayment_schedule": None,
        "missing_requirements": [],
        "case_summary": None,

        # Detailed execution evidence.
        "tool_calls_made": [],

        # Per-request tool limits.
        "tool_call_counts": {
            "get_member_record": 0,
            "retrieve_policy": 0,
            "calculate_repayment": 0,
        },

        "iteration_count": 0,
        "stop_reason": None,
        "human_handoff_required": False,
    }


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def _update_state_from_tool_result(
    state: dict,
    tool_name: str,
    tool_result: dict,
) -> None:
    """
    Store the useful result of a successful tool execution.

    The complete tool result is retained in state because it is useful
    for constructing the final case packet and evidence.

    The complete policy content is stored here, but only a compact
    representation is sent to Gemini on subsequent iterations.
    """

    if tool_name == "get_member_record":
        state["member_record"] = tool_result

    elif tool_name == "retrieve_policy":
        results = tool_result.get("results", [])

        if isinstance(results, list):
            state["policy_excerpts"].extend(results)

    elif tool_name == "calculate_repayment":
        state["repayment_schedule"] = tool_result


def _state_for_model(state: dict) -> dict:
    """
    Create a compact representation of state for Gemini.

    Important:
    - Do NOT repeatedly send unrelated full tool history.
    - Give Gemini enough policy content to make the next decision.
    - Give Gemini enough repayment information to prepare the case.
    """

    member_record = state.get("member_record")
    repayment = state.get("repayment_schedule")

    policy_documents = []

    for item in state.get("policy_excerpts", []):
        if not isinstance(item, dict):
            continue

        document = item.get("document")

        if document and document not in policy_documents:
            policy_documents.append(document)

    return {
        "member_message": state["member_message"],

        "requester_role": state["requester_role"],

        "requester_membership_number": (
            state["requester_membership_number"]
        ),

        # ---------------------------------------------------------------
        # Member information
        # ---------------------------------------------------------------

        "member_record_available": member_record is not None,

        "member_record_summary": (
            _summarize_member_record(member_record)
            if member_record
            else None
        ),

        # ---------------------------------------------------------------
        # Policy information
        # ---------------------------------------------------------------

        "policy_documents_retrieved": policy_documents,

        "policy_documents_count": len(policy_documents),

        "policy_excerpts": _summarize_policy_excerpts(
            state.get("policy_excerpts", [])
        ),

        # ---------------------------------------------------------------
        # Repayment information
        # ---------------------------------------------------------------

        "repayment_schedule_available": repayment is not None,

        "repayment_summary": (
            _summarize_repayment(repayment)
            if repayment
            else None
        ),

        # ---------------------------------------------------------------
        # Other state
        # ---------------------------------------------------------------

        "missing_requirements": list(
            state.get("missing_requirements", [])
        ),

        "case_summary_available": (
            state.get("case_summary") is not None
        ),

        "tool_call_counts": dict(
            state.get("tool_call_counts", {})
        ),

        "iteration_count": state["iteration_count"],

        "limits": {
            "max_iterations": MAX_ITERATIONS,
            "max_calls_per_tool": MAX_CALLS_PER_TOOL,
        },

        "human_handoff_required": (
            state["human_handoff_required"]
        ),
    }


def _summarize_member_record(member_record: dict) -> dict:
    """
    Return only the member-record fields useful for planning.

    This prevents the entire raw record from being repeatedly sent
    to Gemini. The field mapping lives with the tool that defines the
    record schema (agent.tools).
    """

    return summarize_member_record_for_model(member_record)


def _summarize_policy_excerpts(
    policy_excerpts: list,
) -> list:
    """
    Return compact policy information for Gemini.

    retrieve_policy() returns entries containing:

        document
        matched_terms
        content

    The actual policy content is included because merely telling
    Gemini that 'development_loan.md' was retrieved is not enough
    for the model to determine whether the policy requirements have
    been gathered.

    The content is truncated per excerpt to avoid repeatedly sending
    unnecessarily large documents.
    """

    summaries = []

    # Maximum characters of one policy document sent to Gemini.
    MAX_POLICY_CONTENT_CHARS = 6000

    for item in policy_excerpts:

        if not isinstance(item, dict):
            continue

        document = item.get("document")

        content = item.get("content", "")

        matched_terms = item.get(
            "matched_terms",
            [],
        )

        if not isinstance(content, str):
            content = str(content)

        if len(content) > MAX_POLICY_CONTENT_CHARS:
            content = (
                content[:MAX_POLICY_CONTENT_CHARS]
                + "\n[policy content truncated]"
            )

        summaries.append(
            {
                "document": document,
                "matched_terms": matched_terms,
                "content": content,
            }
        )

    return summaries


def _summarize_repayment(repayment: dict) -> dict:
    """
    Return a compact repayment summary instead of repeatedly sending
    the entire repayment result.

    Field names match calculate_repayment() in tools.py.
    """

    if not isinstance(repayment, dict):
        return {}

    summary = {}

    useful_fields = [
        "loan_product",
        "principal_ugx",
        "term_months",
        "monthly_installment_ugx",
        "total_interest_ugx",
        "total_repayable_ugx",
        "annual_rate_percent",
        "method",
        "policy_basis",
        "illustrative",
        "decision",
    ]

    for field in useful_fields:
        if field in repayment:
            summary[field] = repayment[field]

    return summary


def _make_trace_state_snapshot(state: dict) -> dict:
    """
    Create an immutable-at-that-time evidence snapshot with PII safely redacted.

    deepcopy is important because lists such as policy_excerpts and
    tool_calls_made continue changing as the agent runs.
    """
    snapshot = copy.deepcopy(state)
    if snapshot.get("member_record"):
        snapshot["member_record"] = sanitize_member_record(snapshot["member_record"])
    return snapshot


def _record_tool_call_for_evidence(
    state: dict,
    call: dict,
) -> None:
    """
    Store compact tool-call evidence.

    Full policy results can be large. Keep the metadata needed to
    understand what happened without duplicating the complete result
    in every trace entry.
    """

    tool_name = call.get("name", "")

    tool_result = call.get("result", {})

    if isinstance(tool_result, dict):

        result_summary = {
            "error": tool_result.get("error"),
        }

        if tool_name == "retrieve_policy":

            results = tool_result.get(
                "results",
                [],
            )

            if isinstance(results, list):

                result_summary["documents"] = [
                    item.get("document")
                    for item in results
                    if isinstance(item, dict)
                    and item.get("document")
                ]

                result_summary["result_count"] = len(
                    results
                )

        elif tool_name == "calculate_repayment":

            result_summary.update(
                _summarize_repayment(tool_result)
            )

        elif tool_name == "get_member_record":

            result_summary["record_available"] = (
                not bool(tool_result.get("error"))
            )

    else:

        result_summary = {
            "result_type": type(tool_result).__name__
        }

    state["tool_calls_made"].append(
        {
            "name": tool_name,

            "arguments": copy.deepcopy(
                call.get("arguments", {})
            ),

            "executed": call.get(
                "executed",
                False,
            ),

            # "result" remains a compact summary for compatibility with
            # scenario tests; it deliberately does not duplicate full
            # member records or policy-document contents.
            "result": copy.deepcopy(result_summary),
            "result_summary": copy.deepcopy(result_summary),
        }
    )


# ---------------------------------------------------------------------------
# Preflight safety guard
# ---------------------------------------------------------------------------

def _is_prohibited_action_request(message: str) -> bool:
    """
    Detect explicit requests for the agent to make or execute a loan decision.

    The guard is intentionally narrow: ordinary requests to prepare a loan
    case are allowed, while direct requests to approve, reject, score, or
    disburse a loan are routed to a human officer before Gemini is called.
    """
    is_prohibited, _ = detect_prohibited_action(message)
    if is_prohibited:
        return True

    text = " ".join((message or "").lower().split())

    prohibited_phrases = (
        "approve my loan",
        "approve the loan",
        "approve this loan",
        "approve the application",
        "approve my application",
        "reject my loan",
        "reject the loan",
        "reject this loan",
        "reject the application",
        "score my loan",
        "score the loan",
        "score this loan",
        "disburse my loan",
        "disburse the loan",
        "disburse this loan",
        "release the loan funds",
        "release my loan funds",
        "make the loan decision",
        "decide on my loan",
    )

    return any(phrase in text for phrase in prohibited_phrases)


# ---------------------------------------------------------------------------
# Case completion checks
# ---------------------------------------------------------------------------

def _case_preparation_is_complete(
    state: dict,
) -> bool:
    """
    Check whether the minimum information required for a completed
    SACCO case-preparation packet is available.

    This does NOT approve, reject, score, or disburse a loan.

    It only verifies that the agent has gathered:
    - the member record;
    - relevant policy information;
    - an illustrative repayment calculation.
    """

    return (
        state.get("member_record") is not None
        and bool(state.get("policy_excerpts"))
        and state.get("repayment_schedule") is not None
    )


def _classify_final_response(
    text: str,
) -> tuple[str, bool]:
    """
    Classify a model response that does not contain a tool call.

    Returns:
        (stop_reason, human_handoff_required)
    """

    text_lower = text.lower()

    prohibited_phrases = [
        "i can't approve",
        "i cannot approve",
        "cannot approve",
        "can't approve",

        "i can't reject",
        "i cannot reject",
        "cannot reject",
        "can't reject",

        "i can't disburse",
        "i cannot disburse",
        "cannot disburse",
        "can't disburse",

        "i can't modify",
        "i cannot modify",
        "cannot modify",
        "can't modify",
    ]

    # Output guardrail: check for autonomous decision claims in output text
    is_valid_output, output_violation = validate_agent_output(text)
    if not is_valid_output:
        return "prohibited_action_in_output", True

    if any(
        phrase in text_lower
        for phrase in prohibited_phrases
    ):
        return "prohibited_action_requested", True

    clarification_phrases = [
        "please provide",
        "please specify",
        "i need the",
        "missing information",
        "need more information",
        "what is the",
    ]

    if any(
        phrase in text_lower
        for phrase in clarification_phrases
    ):
        return "clarification_required", False

    if text.strip():
        return "case_complete", True

    return "empty_response", True


# ---------------------------------------------------------------------------
# Incomplete case packet
# ---------------------------------------------------------------------------

def _build_incomplete_case_packet(
    state: dict,
) -> str:
    """
    Build a useful officer-facing case packet when the agent cannot
    complete the workflow.

    The packet deliberately does NOT make a loan decision.
    """

    member_record = state.get("member_record")
    repayment = state.get("repayment_schedule")

    policy_documents = []

    for item in state.get("policy_excerpts", []):

        if not isinstance(item, dict):
            continue

        document = item.get("document")

        if document and document not in policy_documents:
            policy_documents.append(document)

    lines = [
        "INCOMPLETE SACCO CASE PREPARATION PACKET",
        "",
        "Status: Incomplete — Relationship Officer review required.",
        f"Stop reason: {state.get('stop_reason')}",
        "",
        "Member request:",
        state.get("member_message", ""),
        "",
        "Information gathered:",
    ]

    if member_record:

        member_summary = _summarize_member_record(
            member_record
        )

        for key, value in member_summary.items():
            lines.append(
                f"- {key}: {value}"
            )

    else:
        lines.append(
            "- Member record: Not retrieved."
        )

    lines.append("")

    lines.append(
        "Policy documents retrieved:"
    )

    if policy_documents:

        for document in policy_documents:
            lines.append(
                f"- {document}"
            )

    else:
        lines.append(
            "- No policy document retrieved."
        )

    lines.append("")

    lines.append(
        "Illustrative repayment:"
    )

    if repayment:

        repayment_summary = _summarize_repayment(
            repayment
        )

        for key, value in repayment_summary.items():
            lines.append(
                f"- {key}: {value}"
            )

    else:

        lines.append(
            "- Repayment schedule was not calculated."
        )

    lines.append("")

    lines.append(
        "Missing / unresolved information:"
    )

    missing_requirements = state.get(
        "missing_requirements",
        [],
    )

    if missing_requirements:

        for item in missing_requirements:
            lines.append(
                f"- {item}"
            )

    else:

        lines.append(
            "- No explicit missing requirement was recorded."
        )

    lines.append("")

    lines.append(
        "Workflow status:"
    )

    lines.append(
        f"- Iterations used: "
        f"{state.get('iteration_count', 0)} / "
        f"{MAX_ITERATIONS}"
    )

    lines.append(
        "- Tool calls: "
        + json.dumps(
            state.get(
                "tool_call_counts",
                {},
            ),
            ensure_ascii=False,
        )
    )

    lines.append("")

    lines.append(
        "Human action required: "
        "Relationship Officer should review the gathered "
        "information and complete any required assessment. "
        "The agent has not approved, rejected, scored, "
        "disbursed, or modified the loan/member account."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent_loop(
    member_message: str,
    system_prompt: str,
    requester_role: str = "member",
    requester_membership_number: str | None = None,
    gemini_runner: Callable | None = None,
    scenario_id: str | None = None,
    run_id: str | None = None,
) -> dict:
    """
    Run one bounded SACCO case-preparation request.

    gemini_runner:
        Optional dependency injection used by tests.

        Normal operation:
            call_gemini_with_tools()

        Deterministic tests:
            a fake function can be supplied so no Gemini API
            call occurs.
    """

    # Record the version of the prompt actually supplied, not a fixed label.
    tracer = AgentTracer(
        scenario_id=scenario_id,
        run_id=run_id,
        prompt_version=identify_prompt_version(system_prompt),
    )

    # Week 7 Guardrail: Deterministic Input Validation (Defect F-01 remediation)
    val_res = validate_input_request(
        member_message=member_message,
        requester_role=requester_role,
        requester_membership_number=requester_membership_number,
    )
    if not val_res["valid"]:
        state = new_state(
            member_message=str(member_message or ""),
            requester_role=str(requester_role),
            requester_membership_number=requester_membership_number,
        )
        state["stop_reason"] = f"validation_error:{val_res['error']}"
        state["human_handoff_required"] = True
        state["case_summary"] = (
            f"Input validation rejected: {val_res['message']} "
            "Please review the request parameters with a Relationship Officer."
        )
        tracer.record_event("validation_failed", {"error": val_res["error"], "message": val_res["message"]})
        step_rec = {
            "iteration": 0,
            "event": "input_validation_guardrail",
            "state_before": _make_trace_state_snapshot(state),
            "model_state": None,
            "tool_calls": [],
            "final_text": state["case_summary"],
            "state_after": _make_trace_state_snapshot(state),
        }
        tracer.end_run(
            stop_reason=state["stop_reason"],
            human_handoff_required=True,
            final_state=state,
            final_output=state["case_summary"],
        )
        return {
            "run_id": tracer.run_id,
            "scenario_id": scenario_id,
            "prompt_version": tracer.prompt_version,
            "started_at": tracer.start_wall_time,
            "ended_at": now_utc_iso(),
            "elapsed_ms": tracer.elapsed_ms,
            "steps": [step_rec],
            "events": tracer.events,
            "final_state": _make_trace_state_snapshot(state),
        }

    # Week 7 Guardrail: Prompt Injection Detection in Input Request
    is_inj, inj_pat = detect_prompt_injection(member_message)
    if is_inj:
        state = new_state(
            member_message=member_message,
            requester_role=requester_role,
            requester_membership_number=requester_membership_number,
        )
        state["stop_reason"] = "adversarial_prompt_rejected"
        state["human_handoff_required"] = True
        state["case_summary"] = (
            f"Security Alert: Disallowed instruction override pattern detected ('{inj_pat}'). "
            "Autonomous execution blocked. The request has been flagged for Relationship Officer review."
        )
        tracer.record_event("prompt_injection_blocked", {"pattern": inj_pat})
        step_rec = {
            "iteration": 0,
            "event": "prompt_injection_guardrail",
            "state_before": _make_trace_state_snapshot(state),
            "model_state": None,
            "tool_calls": [],
            "final_text": state["case_summary"],
            "state_after": _make_trace_state_snapshot(state),
        }
        tracer.end_run(
            stop_reason=state["stop_reason"],
            human_handoff_required=True,
            final_state=state,
            final_output=state["case_summary"],
        )
        return {
            "run_id": tracer.run_id,
            "scenario_id": scenario_id,
            "prompt_version": tracer.prompt_version,
            "started_at": tracer.start_wall_time,
            "ended_at": now_utc_iso(),
            "elapsed_ms": tracer.elapsed_ms,
            "steps": [step_rec],
            "events": tracer.events,
            "final_state": _make_trace_state_snapshot(state),
        }

    state = new_state(
        member_message=member_message,
        requester_role=requester_role,
        requester_membership_number=requester_membership_number,
    )

    trace = {
        "started_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "prompt_version": tracer.prompt_version,

        "steps": [],
    }

    # Normal production behavior. Tests can inject a deterministic fake.
    if gemini_runner is None:
        gemini_runner = call_gemini_with_tools

    # Reject explicit requests for prohibited loan decisions before calling
    # Gemini or executing any tool. This is deterministic and quota-free.
    if _is_prohibited_action_request(member_message):
        state["stop_reason"] = "prohibited_action_requested"
        state["human_handoff_required"] = True
        # The refusal is the response. Nothing was gathered, so an empty
        # case packet would only hide it.
        state["case_summary"] = PREFLIGHT_REFUSAL

        trace["steps"].append(
            {
                "iteration": 0,
                "event": "preflight_safety_guard",
                "state_before": _make_trace_state_snapshot(state),
                "model_state": None,
                "tool_calls": [],
                "final_text": PREFLIGHT_REFUSAL,
                "state_after": _make_trace_state_snapshot(state),
            }
        )

    while (
        state["iteration_count"] < MAX_ITERATIONS
        and state["stop_reason"] is None
    ):

        state["iteration_count"] += 1

        # ---------------------------------------------------------------
        # Snapshot BEFORE Gemini sees this iteration.
        # ---------------------------------------------------------------

        state_before = _make_trace_state_snapshot(
            state
        )

        model_state = _state_for_model(
            state
        )

        # ---------------------------------------------------------------
        # Sense / Plan / Decide
        # ---------------------------------------------------------------

        outcome = gemini_runner(
            member_message,
            system_prompt,

            requester_role=state[
                "requester_role"
            ],

            requester_membership_number=state[
                "requester_membership_number"
            ],

            tool_call_counts=state[
                "tool_call_counts"
            ],

            max_calls_per_tool=MAX_CALLS_PER_TOOL,

            # Compact state for Gemini.
            agent_state=model_state,
        )

        if not isinstance(outcome, dict):
            outcome = {
                "final_text": "",
                "tool_calls": [],
                "error": "invalid_model_response",
            }

        tool_calls = outcome.get(
            "tool_calls",
            [],
        )

        # ---------------------------------------------------------------
        # We will populate state_after after processing the action.
        # ---------------------------------------------------------------

        step_record = {
            "iteration": state[
                "iteration_count"
            ],

            "state_before": state_before,

            "model_state": copy.deepcopy(
                model_state
            ),

            "tool_calls": [],

            "final_text": outcome.get(
                "final_text",
                "",
            ),
        }

        # ---------------------------------------------------------------
        # Model/API returned an explicit top-level error.
        # ---------------------------------------------------------------

        if outcome.get("error") and not tool_calls:
            error = str(outcome["error"])
            state["stop_reason"] = (
                error if error.startswith("tool_failure:")
                else f"tool_failure:{error}"
            )
            state["human_handoff_required"] = True
            state["case_summary"] = _build_incomplete_case_packet(state)
            step_record["state_after"] = _make_trace_state_snapshot(state)
            trace["steps"].append(step_record)
            break

        # ---------------------------------------------------------------
        # Gemini returned final text instead of a tool call.
        # ---------------------------------------------------------------

        if not tool_calls:

            final_text = outcome.get(
                "final_text",
                "",
            ).strip()

            state["case_summary"] = final_text

            (
                state["stop_reason"],
                state["human_handoff_required"],
            ) = _classify_final_response(
                final_text
            )

            # Output guardrail: a response presenting a lending decision as
            # made is never shown. Replace it with a notice plus the gathered
            # facts for the officer, and keep the unsafe text out of the trace.
            if state["stop_reason"] == "prohibited_action_in_output":
                _, violation = validate_agent_output(final_text)
                state["case_summary"] = (
                    OUTPUT_WITHHELD_NOTICE
                    + "\n\n"
                    + _build_incomplete_case_packet(state)
                )
                step_record["final_text"] = "[withheld by output guardrail]"
                step_record["guardrail"] = "output_decision_claim_withheld"
                tracer.record_event(
                    "output_guardrail_withheld", {"violation": violation}
                )

            # -----------------------------------------------------------
            # A case is only complete if the required preparation
            # information has actually been gathered.
            # -----------------------------------------------------------

            if state["stop_reason"] == "case_complete":

                if not _case_preparation_is_complete(
                    state
                ):

                    state["stop_reason"] = (
                        "incomplete_case"
                    )

                    state[
                        "human_handoff_required"
                    ] = True

                    state["case_summary"] = (
                        _build_incomplete_case_packet(
                            state
                        )
                    )

            step_record["state_after"] = (
                _make_trace_state_snapshot(
                    state
                )
            )

            trace["steps"].append(
                step_record
            )

            break

        # ---------------------------------------------------------------
        # One tool call per Gemini round.
        # ---------------------------------------------------------------

        call = tool_calls[0]

        tool_name = call.get(
            "name",
            "",
        )

        tool_result = call.get(
            "result",
            {},
        )

        executed = call.get(
            "executed",
            False,
        )

        # Keep trace compact.
        step_record["tool_calls"].append(
            {
                "name": tool_name,

                "arguments": copy.deepcopy(
                    call.get(
                        "arguments",
                        {},
                    )
                ),

                "executed": executed,

                "result_summary": (
                    _summarize_tool_result(
                        tool_name,
                        tool_result,
                    )
                ),
            }
        )

        # ---------------------------------------------------------------
        # Unknown tool
        # ---------------------------------------------------------------

        if tool_name not in APPROVED_TOOLS:

            _record_tool_call_for_evidence(
                state,
                call,
            )

            state["stop_reason"] = (
                "unknown_tool"
            )

            state[
                "human_handoff_required"
            ] = True

            state["case_summary"] = (
                _build_incomplete_case_packet(
                    state
                )
            )

            step_record["state_after"] = (
                _make_trace_state_snapshot(
                    state
                )
            )

            trace["steps"].append(
                step_record
            )

            break

        # ---------------------------------------------------------------
        # Tool execution was blocked before execution.
        #
        # Example:
        # tool_call_limit_exceeded
        # ---------------------------------------------------------------

        if not executed:

            _record_tool_call_for_evidence(
                state,
                call,
            )

            if isinstance(
                tool_result,
                dict,
            ):

                error_type = tool_result.get(
                    "error",
                    "tool_execution_blocked",
                )

            else:

                error_type = (
                    "tool_execution_blocked"
                )

            state["stop_reason"] = error_type

            state[
                "human_handoff_required"
            ] = True

            state["case_summary"] = (
                _build_incomplete_case_packet(
                    state
                )
            )

            step_record["state_after"] = (
                _make_trace_state_snapshot(
                    state
                )
            )

            trace["steps"].append(
                step_record
            )

            break

        # ---------------------------------------------------------------
        # Record successful tool execution.
        # ---------------------------------------------------------------

        _record_tool_call_for_evidence(
            state,
            call,
        )

        # Increment ONLY after execution occurred.
        state["tool_call_counts"][
            tool_name
        ] += 1

        # ---------------------------------------------------------------
        # Tool returned an error.
        # ---------------------------------------------------------------

        if (
            isinstance(
                tool_result,
                dict,
            )
            and tool_result.get("error")
        ):

            state["stop_reason"] = (
                f"tool_failure:"
                f"{tool_result['error']}"
            )

            state[
                "human_handoff_required"
            ] = True

            state["case_summary"] = (
                _build_incomplete_case_packet(
                    state
                )
            )

            step_record["state_after"] = (
                _make_trace_state_snapshot(
                    state
                )
            )

            trace["steps"].append(
                step_record
            )

            break

        # ---------------------------------------------------------------
        # Observe successful result and update state.
        # ---------------------------------------------------------------

        _update_state_from_tool_result(
            state=state,
            tool_name=tool_name,
            tool_result=tool_result,
        )

        # Week 7 Guardrail: Detect prompt injection embedded within retrieved documents
        if tool_name == "retrieve_policy" and isinstance(tool_result, dict):
            for res_item in tool_result.get("results", []):
                if isinstance(res_item, dict):
                    content = res_item.get("content", "")
                    doc_name = res_item.get("document", "unknown")
                    has_inj, inj_pat = detect_prompt_injection(content)
                    if has_inj:
                        state["stop_reason"] = "policy_injection_detected"
                        state["human_handoff_required"] = True
                        state["case_summary"] = (
                            f"Security Notice: Retrieved policy document '{doc_name}' contains "
                            f"untrusted instruction override markers ('{inj_pat}'). "
                            "Workflow safely halted. Escalation to SACCO Relationship Officer required."
                        )
                        tracer.record_event("policy_injection_blocked", {"document": doc_name, "pattern": inj_pat})
                        step_record["state_after"] = _make_trace_state_snapshot(state)
                        trace["steps"].append(step_record)
                        break
            if state["stop_reason"] == "policy_injection_detected":
                break

        # ---------------------------------------------------------------
        # Record state after the observation.
        # ---------------------------------------------------------------

        step_record["state_after"] = (
            _make_trace_state_snapshot(
                state
            )
        )

        trace["steps"].append(
            step_record
        )

        # ---------------------------------------------------------------
        # Re-plan.
        #
        # The next Gemini call receives compact state containing:
        # - member information;
        # - retrieved policy content;
        # - repayment information;
        # - missing requirements;
        # - tool counts;
        # - iteration count.
        # ---------------------------------------------------------------

    else:

        # The while condition became false without a break. This can happen
        # because the iteration limit was reached, but it can also happen
        # when a preflight guard already set a stop reason before the loop.
        # Only label this as max_iterations_reached when the limit really
        # caused the loop to finish; never overwrite an existing stop reason.
        if (
            state["stop_reason"] is None
            and state["iteration_count"] >= MAX_ITERATIONS
        ):
            state["stop_reason"] = "max_iterations_reached"
            state["human_handoff_required"] = True
            state["case_summary"] = _build_incomplete_case_packet(state)

    # -------------------------------------------------------------------
    # Safety fallback.
    #
    # If something caused the loop to stop without a useful case summary,
    # construct one from the state.
    # -------------------------------------------------------------------

    if (
        not state.get("case_summary")
        and state.get("stop_reason")
        != "case_complete"
    ):

        state["case_summary"] = (
            _build_incomplete_case_packet(
                state
            )
        )

    trace["ended_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    trace["final_state"] = (
        _make_trace_state_snapshot(
            state
        )
    )

    tracer.end_run(
        stop_reason=str(state.get("stop_reason")),
        human_handoff_required=bool(state.get("human_handoff_required")),
        final_state=state,
        final_output=state.get("case_summary"),
    )
    trace["run_id"] = tracer.run_id
    trace["scenario_id"] = scenario_id
    trace["events"] = tracer.events
    trace["elapsed_ms"] = tracer.elapsed_ms

    return trace


# ---------------------------------------------------------------------------
# Tool-result evidence helper
# ---------------------------------------------------------------------------

def _summarize_tool_result(
    tool_name: str,
    tool_result: dict,
) -> dict:
    """
    Return compact evidence for a tool result.

    Prevents policy text from being duplicated throughout the trace.
    """

    if not isinstance(
        tool_result,
        dict,
    ):

        return {
            "type": type(
                tool_result
            ).__name__,
        }

    summary = {}

    if tool_result.get("error"):
        summary["error"] = (
            tool_result["error"]
        )

    if tool_name == "retrieve_policy":

        results = tool_result.get(
            "results",
            [],
        )

        if isinstance(
            results,
            list,
        ):

            summary["documents"] = [
                item.get("document")
                for item in results
                if isinstance(
                    item,
                    dict,
                )
                and item.get("document")
            ]

            summary["result_count"] = len(
                results
            )

    elif tool_name == "calculate_repayment":

        summary.update(
            _summarize_repayment(
                tool_result
            )
        )

    elif tool_name == "get_member_record":

        summary["record_available"] = (
            not bool(
                tool_result.get(
                    "error"
                )
            )
        )

        if not tool_result.get(
            "error"
        ):

            summary[
                "membership_number"
            ] = tool_result.get(
                "membership_number"
            )

    return summary


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message=(
            "My membership number is HS-2023-000303. "
            "I want a Development Loan of UGX 2,000,000 "
            "over 12 months, paid monthly. "
            "Please prepare my case."
        ),

        system_prompt=system_prompt,

        requester_role="member",

        requester_membership_number=(
            "HS-2023-000303"
        ),
    )

    final_state = trace[
        "final_state"
    ]

    print("=" * 72)

    print(
        "SACCO CASE PREPARATION AGENT — "
        "EXECUTION EVIDENCE"
    )

    print("=" * 72)

    print(
        f"\nIterations: "
        f"{final_state['iteration_count']}"
    )

    print(
        f"Stop reason: "
        f"{final_state['stop_reason']}"
    )

    print(
        f"Human handoff: "
        f"{final_state['human_handoff_required']}"
    )

    print("\nTool calls:")

    for call in final_state[
        "tool_calls_made"
    ]:

        print(
            f"  - {call.get('name')} "
            f"(executed="
            f"{call.get('executed', False)})"
        )

    print("\nTool call counts:")

    print(
        json.dumps(
            final_state[
                "tool_call_counts"
            ],
            indent=2,
        )
    )

    print("\nFinal output:")

    print(
        final_state[
            "case_summary"
        ]
        or "(none)"
    )

    evidence_dir = (
        REPO_ROOT
        / "evidence"
        / "traces"
    )

    evidence_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = (
        evidence_dir
        / "manual_agent_run.json"
    )

    output_path.write_text(
        json.dumps(
            trace,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"\nTrace saved to: "
        f"{output_path}"
    )