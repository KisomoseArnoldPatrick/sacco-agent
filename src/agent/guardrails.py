"""
Week 7 — Deterministic guardrails for the bounded SACCO case-preparation agent.

These checks run in Python, outside the model. They are a backstop, not a
replacement for the prompt (prompts/v1.0.md) or for the tool-level
authorization in tools.py.

Layers added here:
    1. Input validation          -> preflight_input_check()
    2. Prompt-injection awareness -> detect_prompt_injection() on user input
                                    and on every tool result (retrieved policy
                                    text is untrusted data, never instructions)
    3. Tool-result validation    -> validate_tool_result()
    4. Output validation         -> validate_output()

Already enforced elsewhere (unchanged): tool allow-list and per-tool call
limits (loop_with_memory.py), iteration limit, authorization (tools.py) and
human hand-off.

Known limitation: the injection and decision-language checks are pattern
based. They catch the documented attack shapes and are tested by the
Week 7 scenarios, but a determined attacker can phrase around them.
"""

import json
import re
from typing import Optional

MAX_MESSAGE_CHARS = 2000

MEMBERSHIP_STRICT = re.compile(r"^HS-\d{4}-\d{6}$")
MEMBERSHIP_LIKE = re.compile(r"\bHS-\d+-\d+\b")
MEMBERSHIP_FIND = re.compile(r"HS-\d{4}-\d{6}")

# ---------------------------------------------------------------------------
# 1. Input validation
# ---------------------------------------------------------------------------


def validate_input(message: str, requester_membership_number: Optional[str]) -> Optional[str]:
    """Return a stop reason if the request is malformed, otherwise None."""
    if not message or not str(message).strip():
        return "invalid_input:empty_message"
    if len(message) > MAX_MESSAGE_CHARS:
        return "invalid_input:message_too_long"
    if requester_membership_number is not None and not MEMBERSHIP_STRICT.match(requester_membership_number):
        return "invalid_input:membership_number_format"
    for token in MEMBERSHIP_LIKE.findall(message):
        if not MEMBERSHIP_STRICT.match(token):
            return "invalid_input:membership_number_format"
    return None


# ---------------------------------------------------------------------------
# 2. Prompt-injection awareness
# ---------------------------------------------------------------------------

_INJECTION_PATTERNS = {
    "override_instructions": re.compile(
        r"ignore\s+(?:all\s+|any\s+|your\s+|the\s+)?(?:previous|prior|above|earlier)\s+"
        r"(?:instructions|rules|prompts?|directions)", re.I),
    "disregard_rules": re.compile(
        r"disregard\s+(?:the|your|all|any)\s+(?:rules|instructions|guidelines|polic(?:y|ies))", re.I),
    "reveal_prompt": re.compile(
        r"(?:reveal|show|print|repeat|display|leak)\s+(?:me\s+)?(?:your|the)\s+"
        r"(?:system\s+prompt|hidden\s+prompt|initial\s+prompt)"
        r"|(?:reveal|show|print|repeat|display|leak)\s+(?:me\s+)?your\s+"
        r"(?:instructions|rules|configuration)", re.I),
    "mode_switch": re.compile(r"developer\s+mode|jailbreak|\bDAN\s+mode\b", re.I),
    "system_override": re.compile(r"system\s+override", re.I),
    "new_instructions": re.compile(r"new\s+instructions\s*:", re.I),
}


def detect_prompt_injection(text: str) -> Optional[str]:
    """Return the name of the first injection pattern found, or None."""
    for name, pattern in _INJECTION_PATTERNS.items():
        if pattern.search(text or ""):
            return name
    return None


def preflight_input_check(message: str, requester_membership_number: Optional[str]) -> Optional[str]:
    """Combined preflight: malformed input first, then injection awareness."""
    reason = validate_input(message, requester_membership_number)
    if reason:
        return reason
    if detect_prompt_injection(message):
        return "prompt_injection_suspected"
    return None


def scan_untrusted_content(tool_result) -> Optional[str]:
    """Tool output (including retrieved policy text) is data, never instructions."""
    try:
        blob = json.dumps(tool_result, default=str)
    except (TypeError, ValueError):
        return None
    return detect_prompt_injection(blob)


# ---------------------------------------------------------------------------
# 3. Tool-result validation
# ---------------------------------------------------------------------------


def validate_tool_result(tool_name: str, result) -> Optional[str]:
    """Return a description of the problem if a SUCCESSFUL result is malformed."""
    if not isinstance(result, dict):
        return f"{tool_name} returned {type(result).__name__}, expected an object"
    if result.get("error"):
        return None  # error results are handled by the loop's failure path
    if tool_name == "get_member_record":
        if not isinstance(result.get("membership_number"), str):
            return "member record has no membership_number"
    elif tool_name == "retrieve_policy":
        items = result.get("results")
        if not isinstance(items, list) or not items:
            return "policy result has no results list"
        if not all(isinstance(i, dict) and i.get("document") and "content" in i for i in items):
            return "policy result entries lack document/content"
    elif tool_name == "calculate_repayment":
        for field in ("monthly_installment_ugx", "total_repayable_ugx"):
            if not isinstance(result.get(field), (int, float)):
                return f"repayment result has no numeric {field}"
        if result.get("illustrative") is not True:
            return "repayment result is not labelled illustrative"
    return None


# ---------------------------------------------------------------------------
# 4. Output validation
# ---------------------------------------------------------------------------

_DECISION_PATTERN = re.compile(
    r"\b(?:loan|application|request)\s+(?:has\s+been|is|was|will\s+be)\s+"
    r"(?:approved|rejected|declined|denied|disbursed|accepted)\b"
    r"|\bi\s+(?:hereby\s+)?(?:approve|reject|decline)\b"
    r"|\bwe\s+(?:approve|reject|decline)\b"
    r"|\bmarked\s+as\s+(?:approved|accepted|rejected)\b"
    r"|(?<!not\s)(?<!no\s)\brecommend(?:s|ed)?\s+(?:the\s+)?(?:approval|rejection|approving|rejecting)\b"
    r"|\bcredit\s*score\s+of\s+\d+",
    re.I,
)


def validate_output(text: str, requester_role: str, requester_membership_number: Optional[str],
                    member_record, user_message: str) -> list:
    """Return a list of violations in the model's final text (empty = acceptable)."""
    violations = []
    text = text or ""
    if _DECISION_PATTERN.search(text):
        violations.append("decision_language")
    if requester_role == "member":
        own = set(MEMBERSHIP_FIND.findall(json.dumps(member_record, default=str))) if isinstance(member_record, dict) else set()
        allowed = own | set(MEMBERSHIP_FIND.findall(user_message or ""))
        if requester_membership_number:
            allowed.add(requester_membership_number)
        leaked = set(MEMBERSHIP_FIND.findall(text)) - allowed
        if leaked:
            violations.append("other_member_identifier")
    return violations
