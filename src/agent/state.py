"""Explicit, versioned workflow state for the Week 6 SACCO demo."""
from datetime import datetime, timezone
import uuid

STATE_VERSION = 1
STATUSES = {
    "new", "in_progress", "waiting_for_member",
    "ready_for_officer_review", "blocked", "closed",
}
TOOLS = ("get_member_record", "retrieve_policy", "calculate_repayment")
PREPARATION_SUMMARY_STATUSES = {
    "not_started", "in_progress", "needs_clarification", "prepared_for_human_review",
}
FORBIDDEN_KEYS = {
    "loan_decision", "approval_decision", "approved", "rejected",
    "credit_score", "disbursement_status", "raw_member_record",
    "full_policy_text", "repayment_payload",
}


def now():
    return datetime.now(timezone.utc).isoformat()


def _non_empty_string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")


def _timestamp(value, field):
    _non_empty_string(value, field)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc


def new_workflow_state(owner_membership_number, requester_role, member_message, case_id=None):
    _non_empty_string(owner_membership_number, "owner_membership_number")
    if requester_role not in {"member", "officer"}:
        raise ValueError("requester_role must be 'member' or 'officer'")
    _non_empty_string(member_message, "member_message")
    if case_id is not None:
        _non_empty_string(case_id, "case_id")
    stamp = now()
    return {
        "state_version": STATE_VERSION,
        "case_id": case_id or str(uuid.uuid4()),
        "owner_membership_number": owner_membership_number,
        "created_at": stamp,
        "updated_at": stamp,
        "status": "new",
        "requester_role": requester_role,
        "member_message": member_message.strip(),
        "workflow": {
            "current_stage": "intake", "iteration_count": 0,
            "max_iterations": 6,
            "tool_call_counts": {name: 0 for name in TOOLS},
            "max_calls_per_tool": 2, "stop_reason": None,
            "human_handoff_required": False,
        },
        "preparation": {
            "member_record_retrieved": False, "policy_documents": [],
            "repayment_calculated": False, "missing_requirements": [],
            "summary_status": "not_started",
        },
        "memory_metadata": {
            "purpose": "resume and review case preparation",
            "contains_raw_member_record": False,
            "contains_full_policy_text": False,
        },
    }


def validate_workflow_state(state):
    """Validate structure, types, limits, and decision-boundary invariants."""
    if not isinstance(state, dict):
        raise ValueError("Workflow state must be an object")
    if type(state.get("state_version")) is not int or state["state_version"] != STATE_VERSION:
        raise ValueError("Invalid or unsupported workflow-state version")

    required = (
        "case_id", "owner_membership_number", "created_at", "updated_at",
        "status", "requester_role", "member_message", "workflow",
        "preparation", "memory_metadata",
    )
    for key in required:
        if key not in state:
            raise ValueError(f"Missing required state field: {key}")
    for key in ("case_id", "owner_membership_number", "member_message"):
        _non_empty_string(state[key], key)
    _timestamp(state["created_at"], "created_at")
    _timestamp(state["updated_at"], "updated_at")
    if state["status"] not in STATUSES:
        raise ValueError("Invalid workflow status")
    if state["requester_role"] not in {"member", "officer"}:
        raise ValueError("Invalid requester_role")

    workflow = state["workflow"]
    preparation = state["preparation"]
    metadata = state["memory_metadata"]
    if not isinstance(workflow, dict) or not isinstance(preparation, dict) or not isinstance(metadata, dict):
        raise ValueError("workflow, preparation, and memory_metadata must be objects")

    for key in ("current_stage",):
        _non_empty_string(workflow.get(key), f"workflow.{key}")
    count = workflow.get("iteration_count")
    maximum = workflow.get("max_iterations")
    call_limit = workflow.get("max_calls_per_tool")
    # Exact type checks are intentional: bool is a subclass of int in Python.
    if type(count) is not int or type(maximum) is not int or maximum != 6 or not 0 <= count <= maximum:
        raise ValueError("Iteration count violates configured limits (maximum must be 6)")
    if type(call_limit) is not int or call_limit != 2:
        raise ValueError("max_calls_per_tool must be 2")
    calls = workflow.get("tool_call_counts")
    if not isinstance(calls, dict) or set(calls) != set(TOOLS):
        raise ValueError("tool_call_counts must contain exactly the approved tools")
    for name, value in calls.items():
        if type(value) is not int or not 0 <= value <= call_limit:
            raise ValueError(f"Invalid or exceeded call count for {name}")
    if workflow.get("stop_reason") is not None and not isinstance(workflow.get("stop_reason"), str):
        raise ValueError("workflow.stop_reason must be a string or null")
    if type(workflow.get("human_handoff_required")) is not bool:
        raise ValueError("workflow.human_handoff_required must be boolean")

    if type(preparation.get("member_record_retrieved")) is not bool:
        raise ValueError("preparation.member_record_retrieved must be boolean")
    if type(preparation.get("repayment_calculated")) is not bool:
        raise ValueError("preparation.repayment_calculated must be boolean")
    for key in ("policy_documents", "missing_requirements"):
        values = preparation.get(key)
        if not isinstance(values, list) or any(not isinstance(item, str) or not item.strip() for item in values):
            raise ValueError(f"preparation.{key} must be a list of non-empty strings")
    if preparation.get("summary_status") not in PREPARATION_SUMMARY_STATUSES:
        raise ValueError("Invalid preparation.summary_status")
    for key in ("purpose",):
        _non_empty_string(metadata.get(key), f"memory_metadata.{key}")
    for key in ("contains_raw_member_record", "contains_full_policy_text"):
        if type(metadata.get(key)) is not bool:
            raise ValueError(f"memory_metadata.{key} must be boolean")
        if metadata[key]:
            raise ValueError(f"Persistent memory must not contain {key.removeprefix('contains_').replace('_', ' ')}")

    def check_keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).lower() in FORBIDDEN_KEYS:
                    raise ValueError(f"Forbidden field in persistent memory: {key}")
                check_keys(child)
        elif isinstance(value, list):
            for child in value:
                check_keys(child)
    check_keys(state)
    return state


def update_stage(state, stage, status="in_progress"):
    validate_workflow_state(state)
    _non_empty_string(stage, "stage")
    if status not in STATUSES:
        raise ValueError("Invalid workflow status")
    state["workflow"]["current_stage"] = stage
    state["status"] = status
    state["updated_at"] = now()
    return state


def apply_preparation_observation(state, member_record_retrieved=None,
                                  policy_documents=None, repayment_calculated=None,
                                  missing_requirements=None):
    """Record preparation progress only; never encode a loan decision."""
    validate_workflow_state(state)
    p = state["preparation"]
    if member_record_retrieved is not None:
        if type(member_record_retrieved) is not bool:
            raise ValueError("member_record_retrieved must be boolean")
        p["member_record_retrieved"] = member_record_retrieved
    if policy_documents is not None:
        if not isinstance(policy_documents, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in policy_documents):
            raise ValueError("policy_documents must contain non-empty strings")
        p["policy_documents"] = sorted(set(policy_documents))
    if repayment_calculated is not None:
        if type(repayment_calculated) is not bool:
            raise ValueError("repayment_calculated must be boolean")
        p["repayment_calculated"] = repayment_calculated
    if missing_requirements is not None:
        if not isinstance(missing_requirements, (list, tuple)) or any(not isinstance(x, str) or not x.strip() for x in missing_requirements):
            raise ValueError("missing_requirements must contain non-empty strings")
        p["missing_requirements"] = list(dict.fromkeys(missing_requirements))
    if p["missing_requirements"]:
        p["summary_status"] = "needs_clarification"
        state["status"] = "waiting_for_member"
    elif p["member_record_retrieved"] and p["policy_documents"] and p["repayment_calculated"]:
        p["summary_status"] = "prepared_for_human_review"
        state["status"] = "ready_for_officer_review"
    else:
        p["summary_status"] = "in_progress"
        state["status"] = "in_progress"
    state["updated_at"] = now()
    return state
