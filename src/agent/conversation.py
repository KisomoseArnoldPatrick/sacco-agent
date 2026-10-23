"""
Deterministic routing of CLI messages, and fixed replies for the ones that
need no model or tool.

route_message() sends every message to exactly one route:

- "safety_check":     the prohibited-action or prompt-injection guardrail
                      matched. The agent loop blocks it before any model or
                      tool call; a greeting or other wording around it cannot
                      change this, because the guardrails see the whole text.
- "direct":           small talk, pause/resume, out-of-scope requests, and
                      ambiguous requests that need one clarification question.
                      Answered here with fixed text: no model, no tool.
- "information":      a SACCO question that is not about the requester's own
                      case. The agent loop answers it (using policy retrieval
                      when needed) and the answer is shown as the response.
- "case_preparation": everything else, including any message with numbers
                      (amounts, terms, membership numbers). The existing
                      case-preparation workflow.

The rules are small on purpose. Direct intents must match a whole short
message; out-of-scope requires the absence of every SACCO term and of any
digit, so SACCO questions fall through to the model rather than being refused.

Fixed replies are built from configuration (approved tools, limits, product
names). They contain no policy terms, so nothing can be invented.
"""

import re

from agent.guardrails import detect_prohibited_action, detect_prompt_injection
from agent.loop_with_memory import (
    APPROVED_TOOLS,
    MAX_CALLS_PER_TOOL,
    MAX_ITERATIONS,
)
from agent.tools import PRODUCT_TERMS


AGENT_NAME = "SACCO Member-Case Preparation Agent"

# Longer messages usually carry case details and belong to the agent.
MAX_CONVERSATIONAL_WORDS = 12

BOUNDARY = (
    "I prepare cases for review by a SACCO Relationship Officer. I cannot "
    "approve or reject loans, disburse funds, or change any account."
)

SUPPORTED_TOPICS = (
    "membership, savings, loan products and policies, repayment estimates, "
    "and preparing a loan case for a Relationship Officer"
)

_GREETING = r"(?:hi|hello|hey|good (?:morning|afternoon|evening))(?: there)?"

_INTENT_PATTERNS = (
    ("greeting", _GREETING),
    ("how_are_you", r"(?:how are you(?: doing)?(?: today)?|how(?:'s| is) it going)"),
    ("thanks", r"(?:ok(?:ay)? )?(?:thanks|thank you|thank u|thx)(?: (?:so much|very much|a lot))?"),
    ("acknowledgement", r"(?:ok(?:ay)?|cool|ok cool|great|alright|all right|nice|fine)"),
    ("identity", r"(?:what(?:'s| is) your name|who are you|what are you)"),
    ("capabilities", r"(?:what can you do|what do you do|what can you help (?:me )?with|how can you help(?: me)?)"),
    ("help", r"(?:help|how do i use (?:this|this system|this app|you)|how does this work|help me get started)"),
    ("clarify_help", r"(?:i (?:need|want) (?:some )?(?:help|assistance)|(?:can you |please )?help me|i have a (?:question|problem))(?: please)?"),
    ("clarify_account", r"(?:i (?:need|want) )?help (?:me )?with my (?:account|membership|savings|shares)"),
    ("clarify_loan", r"(?:i (?:need|want|would like)|i'd like|can i (?:get|have)) (?:a |some )?(?:loan|money|credit)(?: please)?"),
    ("pause", r"(?:ok(?:ay)? )?(?:i(?:'ll| will| wil| shall)|let me|i(?:'m| am) going to) (?:g[eo]?t|come|check) back\b.*"),
    ("pause", r"(?:ok(?:ay)? )?(?:i need|give me|i will need) (?:some |more )?time\b.*"),
    ("pause", r"(?:talk (?:to you )?later|see you(?: later)?|bye|goodbye)\b.*"),
    ("resume", r"(?:please )?(?:continue|resume|pick up|go back to|return to)\b.*\b(?:application|case|request)"),
)

_COMPILED = [(intent, re.compile(pattern)) for intent, pattern in _INTENT_PATTERNS]
_GREETING_PREFIX = re.compile(rf"{_GREETING}\b\s*")

# Any one of these keeps a message in scope (sent to the model).
_SACCO_TERMS = re.compile(
    r"\b(?:saccos?|loans?|borrow\w*|lend\w*|sav(?:e|es|ing|ings)|shares?|member\w*"
    r"|accounts?|balances?|repay\w*|instal+ments?|interest|rates?|guarant\w*"
    r"|deposit\w*|withdraw\w*|dividends?|polic(?:y|ies)|documents?|fees?|credit"
    r"|collateral|applica\w*|apply\w*|cases?|officers?|ugx|shillings?|contribut\w*"
    r"|emergency|development|school|penalt\w*|default\w*|restructur\w*|eligib\w*"
    r"|join\w*|regist\w*|complain\w*|grievance\w*|committee\w*|bylaws?|money"
    r"|funds?|payments?|statements?|requirements?|products?)\b"
)
_QUESTION_START = re.compile(
    r"(?:what|whats|how|which|when|where|who|why|is|are|do|does|did|can|could"
    r"|may|should|will|would|tell me|explain|describe|define|list)\b"
)
# A question about the requester's own case needs the case workflow.
_PERSONAL_CASE = re.compile(r"\b(?:my|mine|prepare|i (?:want|need|would like|wish|plan))\b")


def normalize(message: str) -> str:
    """Lower-case, drop a byte-order mark and punctuation, collapse spaces."""
    text = (message or "").replace("﻿", "").lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return " ".join(text.split())


def _direct_intent(text: str) -> str | None:
    if not text or len(text.split()) > MAX_CONVERSATIONAL_WORDS or re.search(r"\d", text):
        return None
    for intent, pattern in _COMPILED:
        if pattern.fullmatch(text):
            return intent
    return None


def classify_message(message: str) -> str | None:
    """Return a direct-reply intent, or None if the message needs the agent."""
    route, intent = route_message(message)
    return intent if route == "direct" else None


def route_message(message: str) -> tuple[str, str | None]:
    """Return (route, intent); see the module docstring for the routes."""

    raw = (message or "").replace("﻿", "")
    if detect_prohibited_action(raw)[0] or detect_prompt_injection(raw)[0]:
        return "safety_check", None

    text = normalize(raw)
    if not text:
        return "case_preparation", None     # the loop's input validation handles it

    intent = _direct_intent(text)
    if intent:
        return "direct", intent

    # "Hello, what is the interest rate?" is routed by what follows the greeting.
    remainder = _GREETING_PREFIX.sub("", text, count=1) if _GREETING_PREFIX.match(text) else text
    if remainder != text:
        intent = _direct_intent(remainder)
        if intent:
            return "direct", intent

    has_digits = bool(re.search(r"\d", remainder))
    if not has_digits and not _SACCO_TERMS.search(remainder):
        return "direct", "out_of_scope"

    is_question = bool(_QUESTION_START.match(remainder)) or raw.rstrip().endswith("?")
    if not has_digits and is_question and not _PERSONAL_CASE.search(remainder):
        return "information", None

    return "case_preparation", None


def _case_lines(case_context: dict | None) -> list[str]:
    """Describe saved case history, labelled as history, without inventing anything."""
    if not case_context:
        return []
    lines = []
    documents = case_context.get("policy_documents_previously_retrieved") or []
    if documents:
        lines.append("Policy documents retrieved earlier: " + ", ".join(documents) + ".")
    for item in case_context.get("previous_missing_requirements") or []:
        lines.append(f"Still outstanding: {item}")
    return lines


def _active_case_hint(case_id: str, case_context: dict | None) -> list[str]:
    """Point at the active case when saved history shows one is under way."""
    if not case_context or not (
        case_context.get("policy_documents_previously_retrieved")
        or case_context.get("previous_missing_requirements")
    ):
        return []
    return [f"You also have case {case_id} in progress; say "
            "\"continue my application\" to pick it up."]


def respond(intent: str, case_id: str, case_context: dict | None = None,
            memory_enabled: bool = True) -> str:
    """Return the fixed reply for a direct intent."""

    products = ", ".join(PRODUCT_TERMS)

    if intent == "greeting":
        return (f"Hello! I'm the {AGENT_NAME}. Ask me about {SUPPORTED_TOPICS}, "
                "or ask what I can do.")

    if intent == "how_are_you":
        return (f"I'm doing well, thank you. I can help with SACCO services: "
                f"{SUPPORTED_TOPICS}. What would you like to do?")

    if intent == "thanks":
        return "You're welcome. Let me know when you'd like to continue."

    if intent == "acknowledgement":
        return "Alright. Let me know what you'd like to do next."

    if intent == "identity":
        return f"I'm the {AGENT_NAME}. {BOUNDARY}"

    if intent == "capabilities":
        return "\n".join([
            f"I'm the {AGENT_NAME}. For each request I can:",
            "- look up your own member record (get_member_record);",
            f"- retrieve SACCO policy for the {products} (retrieve_policy);",
            "- calculate an illustrative repayment schedule (calculate_repayment);",
            "- list what is still missing and draft a case summary.",
            f"Each request is limited to {MAX_ITERATIONS} steps and "
            f"{MAX_CALLS_PER_TOOL} calls per tool ({len(APPROVED_TOOLS)} approved tools only).",
            BOUNDARY,
        ])

    if intent == "help":
        return "\n".join([
            "Ask a SACCO question, or describe the loan you want in one message, for example:",
            '  "I want a Development Loan of UGX 2,000,000 over 12 months, paid monthly."',
            "For a loan, I gather your record, the relevant policy and an illustrative "
            "repayment, then list anything still missing for the Relationship Officer.",
            "Commands: /new (new case), /case, /trace, /help, /exit.",
        ])

    if intent == "out_of_scope":
        return (f"Sorry, I can only help with SACCO services: {SUPPORTED_TOPICS}. "
                "Is there something SACCO-related I can help you with?")

    if intent == "clarify_help":
        return "\n".join([
            "Sure. What do you need help with? For example: a question about SACCO "
            "policies, your own member record, a repayment estimate, or preparing a loan case.",
            *_active_case_hint(case_id, case_context),
        ])

    if intent == "clarify_account":
        return ("What would you like to know about your account: your savings or share "
                "capital, an active loan, or guarantee commitments? I can look these up "
                "for your own record, but I cannot change balances or move money.")

    if intent == "clarify_loan":
        return "\n".join([
            f"Which loan are you interested in: {products}? If you're not sure, "
            "tell me what the money is for.",
            *_active_case_hint(case_id, case_context),
        ])

    if intent == "pause":
        lines = ["No problem, you can come back any time."]
        if memory_enabled and case_context:
            lines.append(f"Your case {case_id} is saved.")
            lines.extend(_case_lines(case_context))
            lines.append(f"To continue in a new session, start the CLI with --case-id {case_id}.")
        elif not memory_enabled:
            lines.append("Memory is off in this session, so nothing will be saved.")
        return "\n".join(lines)

    if intent == "resume":
        if case_context:
            lines = [f"Continuing case {case_id} (status: {case_context.get('previous_status')})."]
            lines.extend(_case_lines(case_context))
            lines.append("Please send the details you'd like to add, such as the loan "
                         "product, amount, repayment period and payment frequency.")
            return "\n".join(lines)
        return ("I don't have a saved case to continue in this session. Please tell me "
                "the loan product, amount, repayment period and payment frequency, "
                "or restart the CLI with --case-id <your case ID>.")

    raise ValueError(f"Unknown conversational intent: {intent}")
