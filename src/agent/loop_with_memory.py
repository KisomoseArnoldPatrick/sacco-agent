"""
Week 5/6 — Bounded SACCO case-preparation agent with persistent memory.

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
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple


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
from agent.memory import CaseMemoryStore, MemoryAccessError  # noqa: E402
from agent.state import (  # noqa: E402
    new_workflow_state,
    validate_workflow_state,
    apply_preparation_observation,
    update_stage,
    now as workflow_now,
)
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

REQUEST_TYPES = {"case_preparation", "information"}

INFORMATION_UNANSWERED = (
    "I could not complete an answer to this question (stop reason: {stop_reason}). "
    "Nothing has been submitted, decided or changed. Please try again later, "
    "or ask a SACCO Relationship Officer."
)


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
    Create runtime state for one request. When resuming a saved case, the
    caller restores the cumulative workflow counters before execution.
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
        "case_id": state.get("case_id"),

        "requester_role": state["requester_role"],

        # Persistent history is context only. It contains preparation
        # progress, not an approval/rejection or other loan decision.
        "previous_case_history": copy.deepcopy(
            state.get("previous_case_history")
        ),

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
        and not state.get("missing_requirements")
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
        "Information gathered in this request:",
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
        "Policy documents retrieved in this request:"
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

    # Saved history is reported separately and labelled as such; it is not
    # copied into this request's gathered information.
    history = state.get("previous_case_history")
    if history:
        lines.append(
            "Earlier in this case (saved history, not re-checked in this request):"
        )
        for document in history.get("policy_documents_previously_retrieved", []):
            lines.append(f"- Policy document previously retrieved: {document}")
        for item in history.get("previous_missing_requirements", []):
            lines.append(f"- Previously outstanding: {item}")
        lines.append(f"- Previous status: {history.get('previous_status')}")
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
# Week 6 persistent-memory integration
# ---------------------------------------------------------------------------

def _policy_document_names(state: dict) -> list[str]:
    """Return unique policy filenames without retaining policy text in memory."""
    names = []
    for item in state.get("policy_excerpts", []):
        if isinstance(item, dict):
            document = item.get("document")
            if document and document not in names:
                names.append(document)
    return names


def _memory_context(memory_state: dict) -> dict:
    """Return the minimal prior history that may be supplied to the agent."""
    preparation = memory_state.get("preparation", {})
    workflow = memory_state.get("workflow", {})
    return {
        "case_id": memory_state.get("case_id"),
        "previous_status": memory_state.get("status"),
        "previous_stage": workflow.get("current_stage"),
        "policy_documents_previously_retrieved": list(
            preparation.get("policy_documents", [])
        ),
        "previous_missing_requirements": list(
            preparation.get("missing_requirements", [])
        ),
        "previous_summary_status": preparation.get("summary_status"),
        "updated_at": memory_state.get("updated_at"),
        "important_boundary": (
            "This is historical preparation context only. Re-check current "
            "requirements and policy. It is not a loan approval or rejection."
        ),
    }


def _build_officer_history_packet(memory_state: dict) -> str:
    """Format saved preparation metadata for an officer, without a model call."""
    context = _memory_context(memory_state)
    lines = [
        "SACCO CASE HISTORY — READ ONLY",
        "",
        f"Case ID: {context['case_id']}",
        f"Previous status: {context['previous_status']}",
        f"Previous stage: {context['previous_stage']}",
        f"Last updated: {context['updated_at']}",
        "",
        "Previously retrieved policy documents:",
    ]
    documents = context["policy_documents_previously_retrieved"]
    lines.extend(f"- {item}" for item in documents) if documents else lines.append("- No policy documents recorded.")
    lines.extend(["", "Previously identified missing requirements:"])
    missing = context["previous_missing_requirements"]
    lines.extend(f"- {item}" for item in missing) if missing else lines.append("- None recorded in the saved history.")
    lines.extend([
        "",
        f"Previous summary status: {context['previous_summary_status']}",
        "",
        "Important: This is historical case-preparation information only.",
        "It is not a loan approval, rejection, or credit decision.",
        "Verify current member information and policy before acting.",
        "The Relationship Officer remains responsible for any decision.",
    ])
    return "\n".join(lines)


def _extract_unresolved_requirements(text: str) -> list[str]:
    """Extract common unresolved SACCO requirements from the final case text.

    The agent's final response is prose, while persistent memory uses a
    structured list. This conservative mapper records only known requirement
    categories when the response indicates they are missing or need checking.
    It does not infer whether a loan should be approved or rejected.
    """
    lowered = (text or "").lower()
    unresolved: list[str] = []

    if "savings" in lowered and any(term in lowered for term in (
        "not provided", "missing", "requires human verification",
        "requires verification", "verify member savings", "needs verification",
    )):
        unresolved.append(
            "Verify the member's savings balance against the 3x savings ceiling."
        )

    if "guarantor" in lowered and any(term in lowered for term in (
        "missing", "not provided", "requires human verification",
        "requires verification", "please provide", "needs to provide",
        "provide details", "required guarantors",
    )):
        unresolved.append(
            "Provide and verify the details and eligibility of the 2 required guarantors."
        )

    if any(term in lowered for term in (
        "purpose statement", "written statement", "written purpose",
        "statement describing the business", "loan purpose",
    )) and any(term in lowered for term in (
        "missing", "not provided", "please submit", "submit a short",
        "needs to provide", "requires human verification", "review submitted",
    )):
        unresolved.append(
            "Submit and review the written statement explaining the loan purpose."
        )

    if "supporting document" in lowered and any(term in lowered for term in (
        "missing", "not provided", "requires human verification",
        "requires verification", "outstanding",
    )):
        unresolved.append("Identify and provide any required supporting documents.")

    # Keep order stable and remove duplicates.
    return list(dict.fromkeys(unresolved))


def _sync_persistent_memory(
    store: CaseMemoryStore,
    memory_state: dict,
    runtime_state: dict,
    owner_membership_number: str,
) -> dict:
    """Copy only minimal workflow metadata into persistent JSON memory."""
    previous_preparation = memory_state.get("preparation", {})
    workflow = memory_state["workflow"]

    # Preserve earlier progress if this run is resuming a case but has not
    # re-fetched a particular item yet. The model still receives the prior
    # history as history, and the completion check requires live runtime data.
    policy_documents = sorted(set(
        previous_preparation.get("policy_documents", [])
        + _policy_document_names(runtime_state)
    ))
    missing_requirements = runtime_state.get("missing_requirements", [])
    if not missing_requirements:
        if runtime_state.get("case_summary"):
            # A final summary is fresh evidence: if it no longer lists known
            # unresolved items, allow those items to be cleared. During an
            # intermediate tool observation there is no fresh summary, so
            # retain previously unresolved requirements until re-assessed.
            missing_requirements = _extract_unresolved_requirements(
                runtime_state["case_summary"]
            )
        else:
            missing_requirements = previous_preparation.get(
                "missing_requirements", []
            )

    apply_preparation_observation(
        memory_state,
        member_record_retrieved=(
            runtime_state.get("member_record") is not None
            or previous_preparation.get("member_record_retrieved", False)
        ),
        policy_documents=policy_documents,
        repayment_calculated=(
            runtime_state.get("repayment_schedule") is not None
            or previous_preparation.get("repayment_calculated", False)
        ),
        missing_requirements=missing_requirements,
    )

    # Copy bounded execution metadata. Never store the raw member record,
    # complete policy text, repayment payload, or an approval/rejection.
    workflow["iteration_count"] = min(
        int(runtime_state.get("iteration_count", 0)),
        int(workflow.get("max_iterations", MAX_ITERATIONS)),
    )
    counts = runtime_state.get("tool_call_counts", {})
    workflow["tool_call_counts"] = {
        name: min(max(int(counts.get(name, 0)), 0), MAX_CALLS_PER_TOOL)
        for name in (
            "get_member_record",
            "retrieve_policy",
            "calculate_repayment",
        )
    }
    workflow["max_iterations"] = MAX_ITERATIONS
    workflow["max_calls_per_tool"] = MAX_CALLS_PER_TOOL
    workflow["stop_reason"] = runtime_state.get("stop_reason")
    workflow["human_handoff_required"] = bool(
        runtime_state.get("human_handoff_required")
    )

    stage = "case_preparation"
    if runtime_state.get("stop_reason"):
        stage = "stopped"
    elif runtime_state.get("repayment_schedule") is not None:
        stage = "preparation_review"
    elif runtime_state.get("policy_excerpts"):
        stage = "collecting_requirements"
    elif runtime_state.get("member_record") is not None:
        stage = "collecting_policy"

    # update_stage sets a valid status and refreshes updated_at. The
    # preparation observation above may already have selected a more useful
    # status, so preserve that status while updating the stage.
    current_status = memory_state["status"]
    update_stage(memory_state, stage, status=current_status)
    memory_state["updated_at"] = workflow_now()
    validate_workflow_state(memory_state)
    store.save(memory_state, owner_membership_number)
    return memory_state


def _initialize_persistent_memory(
    *,
    member_message: str,
    requester_role: str,
    requester_membership_number: str | None,
    case_owner_membership_number: str | None,
    case_id: str | None,
    memory_store_path: str | Path,
    resume_saved_case: bool,
    authorized_member_numbers: set[str] | None,
    persist_memory: bool,
) -> dict:
    """Initialize memory for a run; officers receive read-only access."""
    resolved_case_id = case_id or f"case-{uuid.uuid4().hex}"
    owner = case_owner_membership_number or requester_membership_number
    result = {
        "enabled": False,
        "status": "disabled_missing_owner_membership_number",
        "case_id": resolved_case_id,
        "owner_membership_number": owner,
        "store": None,
        "memory_state": None,
        "can_write": False,
        "previous_case_history": None,
    }

    if not persist_memory:
        result["status"] = "disabled_by_request"
        return result
    if not owner:
        return result

    store = CaseMemoryStore(memory_store_path)
    result["store"] = store
    result["enabled"] = True
    result["case_id"] = resolved_case_id

    # Member-owned cases can be updated by the owner. Officer access is
    # read-only here and requires an explicit trusted authorization list.
    actor_is_owner = requester_membership_number == owner
    result["can_write"] = requester_role == "member" and actor_is_owner

    if resume_saved_case:
        try:
            restored = store.load(
                resolved_case_id,
                requester_membership_number or "",
                actor_role=requester_role,
                authorized_member_numbers=authorized_member_numbers,
            )
        except MemoryAccessError:
            # Return a generic denial to the caller. Do not reveal whether a
            # particular case exists to an unauthorized requester.
            result["status"] = "access_denied"
            result["memory_state"] = None
            result["previous_case_history"] = None
            return result

        if restored is not None:
            result["memory_state"] = restored
            result["previous_case_history"] = _memory_context(restored)
            result["status"] = "restored_existing_case"
            # Do not allow an officer or non-owner to write the case.
            result["can_write"] = bool(
                result["can_write"]
                and restored.get("owner_membership_number") == owner
            )
            return result

    # A new persistent record is created only for the member acting as owner.
    if result["can_write"]:
        memory_state = new_workflow_state(
            owner,
            requester_role,
            member_message,
            resolved_case_id,
        )
        store.save(memory_state, owner)
        result["memory_state"] = memory_state
        result["status"] = "created_new_case"
    else:
        if resume_saved_case and requester_role == "officer":
            result["status"] = "saved_case_not_found"
        else:
            result["status"] = "read_only_or_not_authorized_to_create"

    return result


# ---------------------------------------------------------------------------
# Safe model invocation helper
# ---------------------------------------------------------------------------

def _call_model_safely(
    runner: Callable,
    *args: Any,
    **kwargs: Any,
) -> tuple[dict[str, Any], float, str | None]:
    """
    Safely invoke the external model runner, measuring latency and sanitizing errors.

    Catches all runtime exceptions (network timeouts, 503 errors, HTTP failures),
    calculates duration in milliseconds, redacts any sensitive API keys or credentials
    from error strings, and returns a structured failure dictionary.

    Returns:
        (outcome, latency_ms, error_message)
        where:
        - outcome: Dict with model response ('final_text', 'tool_calls', optional 'error')
        - latency_ms: Float duration in milliseconds
        - error_message: Sanitized error string with sensitive secrets redacted, or None
    """
    start_time = time.perf_counter()
    try:
        outcome = runner(*args, **kwargs)
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        if not isinstance(outcome, dict):
            outcome = {
                "final_text": "",
                "tool_calls": [],
                "error": "invalid_model_response",
            }
        return outcome, latency_ms, None
    except Exception as exc:
        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        raw_error = f"{type(exc).__name__}: {exc}"
        sanitized_error = re.sub(r"(key=)[^&\s'\"]+", r"\1REDACTED", raw_error, flags=re.IGNORECASE)
        sanitized_error = re.sub(r"(AIza[0-9A-Za-z-_]{35})", "[REDACTED_API_KEY]", sanitized_error)
        outcome = {
            "final_text": "",
            "tool_calls": [],
            "error": "model_unavailable",
        }
        return outcome, latency_ms, sanitized_error


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent_loop(
    member_message: str,
    system_prompt: str,
    requester_role: str = "member",
    requester_membership_number: str | None = None,
    gemini_runner: Callable | None = None,
    case_id: str | None = None,
    case_owner_membership_number: str | None = None,
    memory_store_path: str | Path | None = None,
    resume_saved_case: bool = False,
    authorized_member_numbers: set[str] | None = None,
    persist_memory: bool = True,
    scenario_id: str | None = None,
    run_id: str | None = None,
    per_request_budget: bool = False,
    request_type: str = "case_preparation",
) -> dict:
    """
    Run one bounded SACCO case-preparation request.

    gemini_runner:
        Optional dependency injection used by tests.

        Normal operation:
            call_gemini_with_tools()

        Deterministic tests:
            a fake function can be supplied so no Gemini API call occurs.

    Week 6 memory options:
        case_id: existing case ID to resume, or a new ID to use.
        case_owner_membership_number: owner ID when an officer is reading.
        memory_store_path: optional override; defaults to evidence/memory.
        resume_saved_case: load existing history when case_id is supplied.
        authorized_member_numbers: trusted authorization results for officers.
        persist_memory: set False to disable persistence for a test/run.
        per_request_budget: by default a resumed case continues within the
            case's cumulative iteration/tool limits (an interrupted workflow
            must not get a fresh budget). Set True when each call is a new,
            independent user request in a continuing conversation (the CLI):
            the saved history is still loaded as context, but this request
            gets its own MAX_ITERATIONS and MAX_CALLS_PER_TOOL.
        request_type: "case_preparation" (default) prepares a member's case:
            a final answer counts as complete only when the record, policy
            and repayment were gathered, otherwise an incomplete case packet
            is shown. "information" answers a SACCO question: the model's
            final answer (after output validation) is the response, with stop
            reason "information_provided", and a failure is reported as an
            unanswered question rather than as an incomplete case.

    Week 7 observability options:
        scenario_id: stable evaluation scenario ID.
        run_id: unique run execution identifier.
    """

    if request_type not in REQUEST_TYPES:
        raise ValueError(f"request_type must be one of {sorted(REQUEST_TYPES)}")

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
            "request_type": request_type,
            "started_at": tracer.start_wall_time,
            "ended_at": now_utc_iso(),
            "elapsed_ms": tracer.elapsed_ms,
            "steps": [step_rec],
            "events": tracer.events,
            "memory": {"enabled": False, "status": "validation_failed"},
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
            "request_type": request_type,
            "started_at": tracer.start_wall_time,
            "ended_at": now_utc_iso(),
            "elapsed_ms": tracer.elapsed_ms,
            "steps": [step_rec],
            "events": tracer.events,
            "memory": {"enabled": False, "status": "adversarial_prompt_rejected"},
            "final_state": _make_trace_state_snapshot(state),
        }

    if requester_role == "officer" and resume_saved_case and not case_owner_membership_number:
        raise ValueError(
            "An officer must specify case_owner_membership_number when retrieving saved case history."
        )

    state = new_state(
        member_message=member_message,
        requester_role=requester_role,
        requester_membership_number=requester_membership_number,
    )

    if memory_store_path is None:
        memory_store_path = REPO_ROOT / "evidence" / "memory" / "case_history.json"

    memory = _initialize_persistent_memory(
        member_message=member_message,
        requester_role=requester_role,
        requester_membership_number=requester_membership_number,
        case_owner_membership_number=case_owner_membership_number,
        case_id=case_id,
        memory_store_path=memory_store_path,
        resume_saved_case=resume_saved_case,
        authorized_member_numbers=authorized_member_numbers,
        persist_memory=persist_memory,
    )
    state["case_id"] = memory["case_id"]
    state["previous_case_history"] = memory.get("previous_case_history")

    # A resumed owner workflow must retain cumulative limits. Do not reset the
    # iteration/tool counters merely because this is a new Python process.
    restored_state = memory.get("memory_state")
    if (
        resume_saved_case
        and not per_request_budget
        and requester_role == "member"
        and memory.get("can_write")
        and isinstance(restored_state, dict)
    ):
        saved_workflow = restored_state.get("workflow", {})
        state["iteration_count"] = int(saved_workflow.get("iteration_count", 0))
        saved_counts = saved_workflow.get("tool_call_counts", {})
        state["tool_call_counts"] = {
            name: int(saved_counts.get(name, 0))
            for name in APPROVED_TOOLS
        }

    trace = {
        "started_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "prompt_version": tracer.prompt_version,
        "request_type": request_type,

        "steps": [],
        "memory": {
            "enabled": memory["enabled"],
            "status": memory["status"],
            "case_id": memory["case_id"],
            "store_path": str(memory_store_path) if memory["enabled"] else None,
            "resumed_previous_case": memory.get("previous_case_history") is not None,
        },
    }

    # Normal production behavior. Tests can inject a deterministic fake.
    if gemini_runner is None:
        gemini_runner = call_gemini_with_tools

    # Officers retrieving saved history take a strictly read-only path.
    # This branch returns before Gemini or any approved tool can run.
    if requester_role == "officer" and resume_saved_case:
        restored = memory.get("memory_state")
        memory_status = memory.get("status")
        if memory_status == "access_denied":
            state["stop_reason"] = "unauthorized_case_history_access"
            state["human_handoff_required"] = True
            state["case_summary"] = (
                "Access denied. You are not authorized to retrieve this case history. "
                "Contact the SACCO administrator to verify access."
            )
            trace["memory"]["status"] = "access_denied"
            event = "officer_history_access_denied"
        elif restored is None:
            state["stop_reason"] = "case_history_not_found"
            state["human_handoff_required"] = True
            state["case_summary"] = (
                "No saved case history was found for the requested case. "
                "Verify the case ID and case-owner details."
            )
            trace["memory"]["status"] = "history_not_found"
            event = "officer_history_not_found"
        else:
            state["stop_reason"] = "history_retrieved_read_only"
            state["human_handoff_required"] = False
            state["case_summary"] = _build_officer_history_packet(restored)
            state["previous_case_history"] = _memory_context(restored)
            trace["memory"]["status"] = "history_retrieved_read_only"
            event = "officer_read_only_history_retrieval"

        trace["steps"].append({
            "iteration": 0,
            "event": event,
            "state_before": _make_trace_state_snapshot(state),
            "model_state": None,
            "tool_calls": [],
            "final_text": state["case_summary"],
            "state_after": _make_trace_state_snapshot(state),
        })
        trace["ended_at"] = datetime.now(timezone.utc).isoformat()
        trace["final_state"] = _make_trace_state_snapshot(state)
        return trace

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

        outcome, model_latency_ms, model_error = _call_model_safely(
            gemini_runner,
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

            "model_latency_ms": model_latency_ms,

            "model_error": model_error,

            "tool_calls": [],

            "final_text": outcome.get(
                "final_text",
                "",
            ),
        }

        # ---------------------------------------------------------------
        # Model/API returned an explicit top-level error or invocation failed.
        # ---------------------------------------------------------------

        if (outcome.get("error") or model_error) and not tool_calls:
            err_code = outcome.get("error") or "model_unavailable"
            error = str(err_code)
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

            # Convert unresolved requirements in the prose summary into
            # structured state before the case is classified and persisted.
            # This prevents memory from saying "no missing requirements"
            # when the officer-facing summary still lists outstanding items.
            extracted_requirements = _extract_unresolved_requirements(final_text)
            state["missing_requirements"] = list(dict.fromkeys(
                list(state.get("missing_requirements", []))
                + extracted_requirements
            ))

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

            # An answer to a SACCO question is the response itself; the
            # case-completeness rules below apply only to case preparation.
            if request_type == "information" and state["stop_reason"] == "case_complete":
                state["stop_reason"] = "information_provided"
                state["human_handoff_required"] = False

            # A response can be finished while the case still has outstanding
            # requirements. Do not label that as case_complete or leave the
            # human handoff flag false. Safety stop reasons are never downgraded.
            if state["missing_requirements"] and state["stop_reason"] not in {
                "information_provided",
                "prohibited_action_requested",
                "prohibited_action_in_output",
                "tool_failure",
            } and not str(state["stop_reason"]).startswith("tool_failure:"):
                state["stop_reason"] = "clarification_required"
                state["human_handoff_required"] = True

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

        # Persist progress after each successful tool observation so a later
        # interruption does not lose all progress from this run.
        if memory.get("enabled") and memory.get("can_write") and memory.get("memory_state"):
            try:
                _sync_persistent_memory(
                    store=memory["store"],
                    memory_state=memory["memory_state"],
                    runtime_state=state,
                    owner_membership_number=memory["owner_membership_number"],
                )
                trace["memory"]["status"] = "saved_after_observation"
            except (OSError, ValueError, MemoryAccessError) as exc:
                trace["memory"]["status"] = "save_failed"
                trace["memory"]["error"] = str(exc)

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

    # A question that could not be answered (model or tool failure, limits)
    # is reported as unanswered, not as an incomplete loan case. The stop
    # reason and handoff flag set by the failure path are kept.
    if (
        request_type == "information"
        and str(state.get("case_summary") or "").startswith(
            "INCOMPLETE SACCO CASE PREPARATION PACKET"
        )
    ):
        state["case_summary"] = INFORMATION_UNANSWERED.format(
            stop_reason=state.get("stop_reason")
        )

    trace["ended_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    # Persist final preparation metadata. The store deliberately excludes
    # raw member records, full policy text, repayment payloads, and decisions.
    if memory.get("enabled") and memory.get("can_write") and memory.get("memory_state"):
        try:
            _sync_persistent_memory(
                store=memory["store"],
                memory_state=memory["memory_state"],
                runtime_state=state,
                owner_membership_number=memory["owner_membership_number"],
            )
            trace["memory"]["status"] = "saved"
        except (OSError, ValueError, MemoryAccessError) as exc:
            # Do not claim persistence succeeded. Keep the agent result and
            # surface the memory failure in its trace for troubleshooting.
            trace["memory"]["status"] = "save_failed"
            trace["memory"]["error"] = str(exc)

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
        # Reuse this ID with resume_saved_case=True to continue this case.
        case_id="manual-development-loan-demo",
        resume_saved_case=True,
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
        / "memory_agent_run.json"
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