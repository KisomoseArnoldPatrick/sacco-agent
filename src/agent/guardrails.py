"""
Week 7 — Deterministic Guardrails for SACCO Case Preparation Agent.

Enforces:
1. Input validation (request types, non-empty text, role authorization, length limits).
2. Prohibited-action detection (approval, rejection, disbursement, account modification).
3. Tool allow-list and parameter type validation.
4. Output validation (detects autonomous loan decisions, missing disclaimers).
5. Prompt-injection defense (detects system prompt override attempts in input and context).
6. Authorization boundaries for member records and saved workflow state.
"""

import re
from typing import Any, Tuple

APPROVED_TOOLS = {
    "get_member_record",
    "retrieve_policy",
    "calculate_repayment",
}

VALID_ROLES = {"member", "officer"}

# Patterns that indicate a user or model is attempting a prohibited financial or decision action.
PROHIBITED_ACTION_PATTERNS = [
    # Loan decisions
    # An optional possessive ("this member's loan", "HS-2024-000101's loan")
    # may sit between the determiner and the object.
    r"\bapprove\s+(?:the\s+|my\s+|this\s+|our\s+|his\s+|her\s+|their\s+)?(?:[\w-]+['’]s\s+)?(?:loan|application)\b",
    r"\b(?:please\s+)?approve\s+(?:immediately|my\s+request|this\s+case)\b",
    # A request addressed to the agent, with a few words before the object
    # ("approve for me a loan", "can you approve my school fees loan").
    # Third-person questions ("can an officer approve a loan?") do not match.
    r"(?:^|[.!?]\s*|\b(?:please|kindly|just|you|u)\s+)(?:approve|reject|decline|deny)\s+(?:\S+\s+){0,4}?(?:loan|application)s?\b",
    r"\b(?:reject|decline)\s+(?:the\s+|my\s+|this\s+|our\s+|his\s+|her\s+|their\s+)?(?:[\w-]+['’]s\s+)?(?:loan|application)\b",
    r"\b(?:make|render|issue)\s+(?:the\s+|a\s+)?(?:loan\s+)?decision\b",
    r"\bscore\s+(?:the\s+|my\s+|this\s+)?(?:loan|credit|application)\b",
    r"\bcredit\s+decision\b",
    # Disbursements and transactions
    r"\bdisburse\b",
    r"\bdisbursement\b",
    r"\brelease\s+(?:the\s+|my\s+)?(?:loan\s+)?funds\b",
    r"\b(?:transfer|send)\s+(?:ugx|\d+|money|funds)\b",
    r"\bpayout\s+funds\b",
    # Account or balance modifications
    r"\b(?:modify|update|change|alter|override|set)\s+(?:my\s+|the\s+)?(?:savings|balance|share\s+capital|account)\b",
    r"\b(?:wipe|clear|delete|forgive)\s+(?:my\s+|the\s+)?(?:debt|loan|balance)\b",
    # Human approval bypass
    r"\bbypass\s+(?:human|officer|review|approval)\b",
    r"\bskip\s+(?:human|officer|review|approval)\b",
    r"\bwithout\s+(?:human|officer)\s+review\b",
]

PROHIBITED_REGEX = re.compile("|".join(PROHIBITED_ACTION_PATTERNS), re.IGNORECASE)

# Patterns that indicate adversarial prompt injection or instruction override.
PROMPT_INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+(?:instructions|prompts|rules)",
    r"disregard\s+(?:all\s+)?(?:previous|prior|system)\s+(?:instructions|rules|prompts)",
    r"system\s+(?:override|prompt\s+override)",
    r"you\s+are\s+now\s+(?:a|an)\s+(?:loan\s+officer|autonomous|unrestricted|god\s+mode)",
    r"developer\s+mode\s+(?:enabled|activated|on)",
    r"\bDAN\b",
    r"override\s+tool\s+(?:permissions|allow-list|limits)",
    r"reveal\s+(?:all\s+)?(?:system\s+prompts?|instructions?|api\s+keys?)",
    r"from\s+now\s+on\s+you\s+(?:can|must)\s+approve",
]

INJECTION_REGEX = re.compile("|".join(PROMPT_INJECTION_PATTERNS), re.IGNORECASE)

# Patterns indicating an unsafe autonomous loan decision in agent/model output.
UNSAFE_OUTPUT_PATTERNS = [
    # Approval / rejection stated as done ("your loan has been approved",
    # "I have rejected your application", "I hereby approve this loan").
    r"\b(?:i|we)\s+(?:have\s+)?(?:approved|rejected|declined|denied)\b",
    r"\b(?:i|we)\s+(?:hereby\s+)?(?:approve|reject|decline)\s+(?:your|the|this)\b",
    r"\b(?:loan|application|request)\s+(?:is|has\s+been)\s+(?:hereby\s+)?(?:approved|rejected|declined|denied)\b",
    # Disbursement / transfer stated as done or authorised.
    r"\b(?:funds|money|loan|amount|ugx\s*[\d,]+)\s+(?:has|have)\s+been\s+(?:disbursed|transferred|released)\b",
    r"\b(?:i|we)\s+have\s+(?:disbursed|transferred|released)\b",
    r"\bdisbursement\s+(?:is|has\s+been)\s+(?:authori[sz]ed|approved|scheduled)\b",
    r"\bdisbursement\s+scheduled\b",
    # Account changes.
    r"\b(?:savings\s+balance\s+updated\s+to|account\s+balance\s+modified)\b",
]

UNSAFE_OUTPUT_REGEX = re.compile("|".join(UNSAFE_OUTPUT_PATTERNS), re.IGNORECASE)

# A decision phrase inside a conditional or procedural clause describes the
# process ("once your application is approved, funds are released"), not a
# decision the agent made. Checked from the start of the sentence to the match.
CONDITIONAL_CONTEXT_REGEX = re.compile(
    r"\b(?:if|once|after|when|whenever|until|before|whether|unless|upon|pending|should)\b",
    re.IGNORECASE,
)

# Shown when the pre-flight guard blocks a prohibited request.
PREFLIGHT_REFUSAL = (
    "This agent prepares cases only. A Relationship Officer must make loan "
    "decisions. I can help prepare your case for that review: tell me the "
    "loan product, amount, repayment period and payment frequency."
)

# Shown instead of a model response that presents a lending decision as made.
OUTPUT_WITHHELD_NOTICE = (
    "RESPONSE WITHHELD BY OUTPUT GUARDRAIL\n"
    "\n"
    "The drafted response presented a lending decision (approval, rejection, "
    "or disbursement) as already made, so it has not been shown. This agent "
    "only prepares cases. Any decision on this application must be made by an "
    "authorized SACCO Relationship Officer."
)


class GuardrailValidationError(ValueError):
    """Raised when request fails input validation guardrails."""


def validate_input_request(
    member_message: Any,
    requester_role: Any = "member",
    requester_membership_number: Any = None,
    max_length: int = 4000,
) -> dict:
    """
    Deterministically validate incoming request parameters.

    Returns:
        dict: {"valid": bool, "error": str | None, "sanitized_message": str}
    """
    if member_message is None:
        return {
            "valid": False,
            "error": "empty_request",
            "message": "Request message cannot be None.",
            "sanitized_message": "",
        }

    if not isinstance(member_message, str):
        return {
            "valid": False,
            "error": "invalid_type",
            "message": f"Request message must be a string, got {type(member_message).__name__}.",
            "sanitized_message": "",
        }

    stripped = member_message.strip()
    if not stripped:
        return {
            "valid": False,
            "error": "empty_request",
            "message": "Request message cannot be empty or whitespace only.",
            "sanitized_message": "",
        }

    if len(stripped) > max_length:
        return {
            "valid": False,
            "error": "request_too_long",
            "message": f"Request length ({len(stripped)}) exceeds maximum allowed ({max_length} chars).",
            "sanitized_message": stripped[:max_length],
        }

    if requester_role not in VALID_ROLES:
        return {
            "valid": False,
            "error": "invalid_role",
            "message": f"Requester role '{requester_role}' is invalid. Allowed roles: {sorted(VALID_ROLES)}.",
            "sanitized_message": stripped,
        }

    if requester_membership_number is not None:
        if not isinstance(requester_membership_number, str):
            return {
                "valid": False,
                "error": "invalid_membership_number",
                "message": "Membership number must be a string.",
                "sanitized_message": stripped,
            }
        num_clean = requester_membership_number.strip()
        if not num_clean or len(num_clean) > 64:
            return {
                "valid": False,
                "error": "invalid_membership_number",
                "message": "Membership number format is invalid.",
                "sanitized_message": stripped,
            }

    return {
        "valid": True,
        "error": None,
        "message": None,
        "sanitized_message": stripped,
    }


def detect_prohibited_action(text: str) -> Tuple[bool, str | None]:
    """
    Check if a text contains an explicit request to perform a prohibited action.

    Returns:
        (is_prohibited, matched_category)
    """
    if not text or not isinstance(text, str):
        return False, None

    normalized = " ".join(text.lower().split())
    match = PROHIBITED_REGEX.search(normalized)
    if match:
        matched_str = match.group(0).lower()
        if any(w in matched_str for w in ("approve", "reject", "decision", "score", "decline")):
            category = "prohibited_loan_decision"
        elif any(w in matched_str for w in ("disburse", "transfer", "payout", "send", "release")):
            category = "prohibited_disbursement"
        elif any(w in matched_str for w in ("modify", "update", "change", "alter", "wipe", "delete", "balance", "savings")):
            category = "prohibited_account_modification"
        elif any(w in matched_str for w in ("bypass", "skip", "without")):
            category = "prohibited_review_bypass"
        else:
            category = "prohibited_action"
        return True, category

    return False, None


def detect_prompt_injection(text: str) -> Tuple[bool, str | None]:
    """
    Scan untrusted user messages and retrieved content for adversarial prompt injection.

    Returns:
        (is_injection, matched_pattern)
    """
    if not text or not isinstance(text, str):
        return False, None

    match = INJECTION_REGEX.search(text)
    if match:
        return True, match.group(0)
    return False, None


def validate_agent_output(output_text: str) -> Tuple[bool, str | None]:
    """
    Validate that the agent's output does not claim to make an autonomous lending decision.

    Returns:
        (is_valid, violation_reason)
    """
    if not output_text or not isinstance(output_text, str):
        return True, None

    for match in UNSAFE_OUTPUT_REGEX.finditer(output_text):
        sentence_start = max(
            output_text.rfind(mark, 0, match.start()) for mark in ".!?\n"
        ) + 1
        if CONDITIONAL_CONTEXT_REGEX.search(output_text[sentence_start:match.start()]):
            continue
        return False, f"output_contains_autonomous_decision: '{match.group(0)}'"

    return True, None


def validate_tool_allowlist(tool_name: str) -> bool:
    """Check if the tool name is in the deterministic approved allow-list."""
    return tool_name in APPROVED_TOOLS


# ---------------------------------------------------------------------------
# Compatibility helpers
# ---------------------------------------------------------------------------

def validate_input(message: str, requester_membership_number: str | None = None) -> str | None:
    """Compatibility wrapper returning an error code or None."""
    res = validate_input_request(message, requester_membership_number=requester_membership_number)
    return res.get("error") if not res["valid"] else None


def preflight_input_check(message: str, requester_membership_number: str | None = None) -> str | None:
    """Combined preflight input validation and prompt-injection check."""
    err = validate_input(message, requester_membership_number)
    if err:
        return err
    is_inj, _ = detect_prompt_injection(message)
    if is_inj:
        return "prompt_injection_suspected"
    return None


def scan_untrusted_content(tool_result) -> str | None:
    """Scan tool output for embedded prompt injection."""
    if isinstance(tool_result, dict):
        for res_item in tool_result.get("results", []):
            if isinstance(res_item, dict):
                content = res_item.get("content", "")
                is_inj, _ = detect_prompt_injection(content)
                if is_inj:
                    return "prompt_injection_suspected"
    return None


def validate_output(text: str) -> str | None:
    """Compatibility output validation check."""
    valid, reason = validate_agent_output(text)
    return reason if not valid else None

