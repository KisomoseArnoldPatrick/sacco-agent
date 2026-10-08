"""
Week 4 — Gemini tool/function-calling orchestration.

Declares the three approved SACCO tools and executes at most one tool
per model round. Week 5's loop.py controls re-planning and stopping.

Approved tools:
    - get_member_record
    - retrieve_policy
    - calculate_repayment

No loan approval, rejection, credit scoring, disbursement, account changes,
or real financial transactions are available through this module.
"""

import json
import os
import sys
import time
from pathlib import Path

import requests
from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
AGENT_DIR = SRC_DIR / "agent"

for directory in (REPO_ROOT, SRC_DIR, AGENT_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


from tools import (  # noqa: E402
    PRODUCT_TERMS,
    calculate_repayment,
    get_member_record,
    retrieve_policy,
)


load_dotenv(REPO_ROOT / ".env")


# ---------------------------------------------------------------------------
# Week 5 safety limits
# ---------------------------------------------------------------------------

DEFAULT_MAX_CALLS_PER_TOOL = 2


# ---------------------------------------------------------------------------
# Tool declarations
# ---------------------------------------------------------------------------

TOOL_DECLARATIONS = [
    {
        "name": "get_member_record",
        "description": (
            "Read-only lookup of a synthetic SACCO member record, including "
            "savings, share capital, active loans and guarantee commitments. "
            "A member may access only their own record. An authorized "
            "Relationship Officer may access another member's record."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "membership_number": {
                    "type": "STRING",
                    "description": "Membership number, e.g. HS-2023-000303.",
                }
            },
            "required": ["membership_number"],
        },
    },
    {
        "name": "retrieve_policy",
        "description": (
            "Retrieve relevant SACCO policy or procedure text from the "
            "approved local policy knowledge base. This tool is read-only. "
            "Use a specific loan_product when it is known."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "The policy information being requested.",
                },
                "loan_product": {
                    "type": "STRING",
                    "enum": list(PRODUCT_TERMS.keys()),
                    "description": "Optional known SACCO loan product.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "calculate_repayment",
        "description": (
            "Calculate an illustrative repayment schedule for a recognized "
            "loan product, principal and repayment term. This is a "
            "deterministic calculation, not a loan decision."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "loan_product": {
                    "type": "STRING",
                    "enum": list(PRODUCT_TERMS.keys()),
                },
                "principal": {
                    "type": "NUMBER",
                    "description": "Requested principal in UGX.",
                },
                "term_months": {
                    "type": "INTEGER",
                    "description": "Repayment term in months.",
                },
            },
            "required": ["loan_product", "principal", "term_months"],
        },
    },
]


# ---------------------------------------------------------------------------
# Python tool registry
# ---------------------------------------------------------------------------

FUNCTIONS = {
    "get_member_record": get_member_record,
    "retrieve_policy": retrieve_policy,
    "calculate_repayment": calculate_repayment,
}


# ---------------------------------------------------------------------------
# HTTP/API helpers
# ---------------------------------------------------------------------------

def _post(
    url: str,
    api_key: str,
    payload: dict,
    max_retries: int = 3,
) -> dict:
    """Call Gemini with bounded retries for transient failures."""

    headers = {"x-goog-api-key": api_key}

    for attempt in range(max_retries):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=30,
            )
        except requests.RequestException as exc:
            if attempt == max_retries - 1:
                raise RuntimeError(
                    f"Gemini network request failed: {exc}"
                ) from exc

            time.sleep(2 ** attempt)
            continue

        # A daily quota error will not be fixed by retrying.
        if response.status_code == 429 and "PerDay" in response.text:
            raise RuntimeError(
                f"Gemini daily quota exhausted: {response.text[:600]}"
            )

        if response.status_code in (429, 500, 503):
            if attempt < max_retries - 1:
                wait = 60 if response.status_code == 429 else 2 ** attempt
                time.sleep(wait)
                continue

        if not response.ok:
            raise RuntimeError(
                f"Gemini API error {response.status_code}: "
                f"{response.text[:1500]}"
            )

        try:
            return response.json()
        except ValueError as exc:
            raise RuntimeError(
                "Gemini returned an invalid JSON response."
            ) from exc

    raise RuntimeError("Gemini request failed after retries.")


def _extract_candidate_parts(data: dict) -> list:
    """Extract response parts or raise a useful error."""

    candidates = data.get("candidates") or []

    if not candidates:
        feedback = data.get("promptFeedback", {})
        raise RuntimeError(
            f"Gemini returned no candidates. Feedback: {feedback}"
        )

    content = candidates[0].get("content") or {}
    parts = content.get("parts") or []

    finish_reason = candidates[0].get("finishReason")

    if not parts:
        raise RuntimeError(
            "Gemini returned no response parts. "
            f"finishReason={finish_reason}"
        )

    return parts


# ---------------------------------------------------------------------------
# Execute one approved tool
# ---------------------------------------------------------------------------

def _execute_tool(
    tool_name: str,
    tool_args: dict,
    requester_role: str,
    requester_membership_number: str | None,
) -> dict:
    """
    Execute exactly one registered tool.

    Authorization for member records is enforced by the Python tool.
    The model cannot supply or override the trusted requester identity.
    """

    if tool_name not in FUNCTIONS:
        return {
            "error": "unknown_tool",
            "message": f"'{tool_name}' is not an approved tool.",
        }

    if not isinstance(tool_args, dict):
        return {
            "error": "invalid_parameters",
            "message": "Tool arguments must be an object.",
        }

    if tool_name == "get_member_record":
        return get_member_record(
            membership_number=tool_args.get("membership_number"),
            requester_role=requester_role,
            requester_membership_number=requester_membership_number,
        )

    if tool_name == "retrieve_policy":
        return retrieve_policy(
            query=tool_args.get("query"),
            loan_product=tool_args.get("loan_product"),
        )

    if tool_name == "calculate_repayment":
        return calculate_repayment(
            loan_product=tool_args.get("loan_product"),
            principal=tool_args.get("principal"),
            term_months=tool_args.get("term_months"),
        )

    return {
        "error": "tool_dispatch_error",
        "message": f"No execution handler exists for '{tool_name}'.",
    }


# ---------------------------------------------------------------------------
# Tool-call limit enforcement
# ---------------------------------------------------------------------------

def _check_tool_call_limit(
    tool_name: str,
    tool_call_counts: dict,
    max_calls_per_tool: int,
) -> dict | None:
    """
    Check whether a tool may execute.

    This check happens BEFORE _execute_tool().

    Returns:
        None if execution is allowed.

        Error dictionary if the limit has already been reached.
    """

    current_count = tool_call_counts.get(tool_name, 0)

    if current_count >= max_calls_per_tool:
        return {
            "error": "tool_call_limit_exceeded",
            "message": (
                f"Tool '{tool_name}' has already been called "
                f"{current_count} time(s), which is the maximum allowed "
                f"of {max_calls_per_tool} per session."
            ),
            "tool_name": tool_name,
            "calls_made": current_count,
            "maximum_allowed": max_calls_per_tool,
            "executed": False,
        }

    return None


# ---------------------------------------------------------------------------
# One Gemini round: choose a tool OR return text
# ---------------------------------------------------------------------------

def call_gemini_with_tools(
    user_message: str,
    system_prompt: str,
    requester_role: str = "member",
    requester_membership_number: str | None = None,
    tool_call_counts: dict | None = None,
    max_calls_per_tool: int = DEFAULT_MAX_CALLS_PER_TOOL,
    agent_state: dict | None = None,
) -> dict:
    """
    Ask Gemini to choose a next action.

    The Python layer enforces the per-tool call limit BEFORE executing
    the requested tool.

    agent_state contains state accumulated by Week 5's bounded loop.
    It is provided to Gemini so the model can continue from the current
    state rather than repeatedly asking for information it already has.

    Returns one of:

        {
            "final_text": "...",
            "tool_calls": []
        }

    or:

        {
            "final_text": "",
            "tool_calls": [{
                "name": "...",
                "arguments": {...},
                "result": {...},
                "executed": True
            }]
        }

    or, when a tool has reached its limit:

        {
            "final_text": "",
            "tool_calls": [{
                "name": "...",
                "arguments": {...},
                "result": {
                    "error": "tool_call_limit_exceeded",
                    ...
                },
                "executed": False
            }]
        }

    It executes no more than one tool per call.
    """

    if tool_call_counts is None:
        tool_call_counts = {}

    if max_calls_per_tool < 1:
        raise ValueError("max_calls_per_tool must be at least 1.")

    api_key = os.environ.get("GEMINI_API_KEY")

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing. Check your .env file."
        )

    model = os.environ.get(
        "GEMINI_MODEL",
        "gemini-3.6-flash",
    )

    url = (
        "https://generativelanguage.googleapis.com/"
        f"v1beta/models/{model}:generateContent"
    )

    # ---------------------------------------------------------------
    # Week 5 agent state
    #
    # The bounded loop owns the state. This function only provides
    # the current state to Gemini as context for the next decision.
    # ---------------------------------------------------------------

    state_context = ""

    if agent_state:
        state_context = (
            "\n\nCURRENT AGENT STATE:\n"
            "The following state has been accumulated by previous "
            "iterations of the bounded agent loop. Use it when deciding "
            "what information is still required. Do not repeat a tool "
            "call merely to obtain information that is already available "
            "in this state.\n\n"
            f"{json.dumps(agent_state, indent=2, ensure_ascii=False)}"
        )

    user_content = user_message + state_context

    payload = {
        "system_instruction": {
            "parts": [{"text": system_prompt}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [{"text": user_content}],
            }
        ],
        "tools": [
            {
                "functionDeclarations": TOOL_DECLARATIONS
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
        },
    }

    data = _post(url, api_key, payload)
    parts = _extract_candidate_parts(data)

    # ---------------------------------------------------------------
    # Gemini returned normal text instead of a tool call.
    # ---------------------------------------------------------------

    function_call_part = next(
        (
            part
            for part in parts
            if isinstance(part, dict)
            and "functionCall" in part
        ),
        None,
    )

    if function_call_part is None:
        final_text = "".join(
            part.get("text", "")
            for part in parts
            if isinstance(part, dict)
            and "text" in part
        ).strip()

        return {
            "final_text": final_text,
            "tool_calls": [],
        }

    # ---------------------------------------------------------------
    # Gemini requested a tool.
    # ---------------------------------------------------------------

    function_call = function_call_part["functionCall"]

    tool_name = function_call.get("name", "")
    tool_args = function_call.get("args") or {}

    if not isinstance(tool_args, dict):
        tool_args = {}

    # ---------------------------------------------------------------
    # IMPORTANT:
    #
    # Check the limit BEFORE executing the tool.
    #
    # This is Python enforcement. Gemini cannot bypass it.
    # ---------------------------------------------------------------

    limit_error = _check_tool_call_limit(
        tool_name=tool_name,
        tool_call_counts=tool_call_counts,
        max_calls_per_tool=max_calls_per_tool,
    )

    if limit_error is not None:
        return {
            "final_text": "",
            "tool_calls": [
                {
                    "name": tool_name,
                    "arguments": tool_args,
                    "result": limit_error,
                    "executed": False,
                }
            ],
        }

    # ---------------------------------------------------------------
    # The call is within the limit, so execution is allowed.
    # ---------------------------------------------------------------

    tool_result = _execute_tool(
        tool_name=tool_name,
        tool_args=tool_args,
        requester_role=requester_role,
        requester_membership_number=requester_membership_number,
    )

    return {
        "final_text": "",
        "tool_calls": [
            {
                "name": tool_name,
                "arguments": tool_args,
                "result": tool_result,
                "executed": True,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Direct test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    counts = {
        "get_member_record": 0,
        "retrieve_policy": 0,
        "calculate_repayment": 0,
    }

    outcome = call_gemini_with_tools(
        (
            "My membership number is HS-2023-000303. "
            "What is my current active loan status?"
        ),
        system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
        tool_call_counts=counts,
        max_calls_per_tool=2,
        agent_state={},
    )

    print("Final text:")
    print(outcome["final_text"] or "(No final text; tool was called.)")

    print("\nTool calls:")
    print(
        json.dumps(
            outcome["tool_calls"],
            indent=2,
            ensure_ascii=False,
        )
    )