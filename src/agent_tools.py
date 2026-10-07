"""
Week 4 — Tool/function calling orchestration.

Declares get_member_record and calculate_repayment to Gemini as callable
tools. When the model requests a tool call, this module executes the real
Python function (enforcing authorization/validation) and sends the result
back to the model for a final answer. The model never runs the tool logic
itself and never bypasses authorization.
"""
import os
import sys
import time
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.append(str(Path(__file__).resolve().parent / "src"))

from baseline_chat import load_system_prompt
from src.agent.tools import get_member_record, calculate_repayment, PRODUCT_TERMS

load_dotenv()

TOOL_DECLARATIONS = [
    {
        "name": "get_member_record",
        "description": (
            "Retrieve a SACCO member's application-relevant record (savings, "
            "share capital, active loan, guarantee commitments) by membership "
            "number. Read-only. A member may only retrieve their own record; "
            "a SACCO Relationship Officer may retrieve any record."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "membership_number": {
                    "type": "string",
                    "description": "Format HS-YYYY-NNNNNN",
                },
            },
            "required": ["membership_number"],
        },
    },
    {
        "name": "calculate_repayment",
        "description": (
            "Deterministically calculate an illustrative repayment schedule "
            "for a named loan product, principal amount and term. Validates "
            "the amount and term against documented product policy limits."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "loan_product": {
                    "type": "string",
                    "enum": list(PRODUCT_TERMS.keys()),
                },
                "principal": {"type": "number", "description": "Loan amount in UGX"},
                "term_months": {"type": "integer", "description": "Requested repayment term in months"},
            },
            "required": ["loan_product", "principal", "term_months"],
        },
    },
]

FUNCTIONS = {
    "get_member_record": get_member_record,
    "calculate_repayment": calculate_repayment,
}


def _post(url, api_key, payload, max_retries=5):
    for attempt in range(max_retries):
        response = requests.post(url, params={"key": api_key}, json=payload, timeout=30)
        if response.status_code in (429, 503) and attempt < max_retries - 1:
            wait = (attempt + 1) * 20 if response.status_code == 429 else 2 ** attempt
            print(f"{response.status_code} error, retrying in {wait}s...")
            time.sleep(wait)
            continue
        response.raise_for_status()
        return response.json()


def call_gemini_with_tools(user_message: str, system_prompt: str,
                            requester_role: str = "member",
                            requester_membership_number: str = None) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    contents = [{"role": "user", "parts": [{"text": user_message}]}]
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": contents,
        "tools": [{"function_declarations": TOOL_DECLARATIONS}],
    }

    data = _post(url, api_key, payload)
    parts = data["candidates"][0]["content"]["parts"]
    function_call_part = next((p for p in parts if "functionCall" in p), None)

    if function_call_part is None:
        return {"final_text": parts[0].get("text", ""), "tool_calls": []}

    tool_name = function_call_part["functionCall"]["name"]
    tool_args = function_call_part["functionCall"].get("args", {}) or {}

    if tool_name not in FUNCTIONS:
        tool_result = {"error": "unknown_tool", "message": f"'{tool_name}' is not an approved tool."}
    elif tool_name == "get_member_record":
        tool_result = get_member_record(
            membership_number=tool_args.get("membership_number"),
            requester_role=requester_role,
            requester_membership_number=requester_membership_number,
        )
    else:
        tool_result = calculate_repayment(
            loan_product=tool_args.get("loan_product"),
            principal=tool_args.get("principal"),
            term_months=tool_args.get("term_months"),
        )

    contents.append({"role": "model", "parts": [function_call_part]})
    contents.append({
        "role": "user",
        "parts": [{"functionResponse": {"name": tool_name, "response": tool_result}}],
    })
    payload["contents"] = contents

    data2 = _post(url, api_key, payload)
    final_parts = data2["candidates"][0]["content"]["parts"]
    final_text = next((p.get("text", "") for p in final_parts if "text" in p), "")

    return {
        "final_text": final_text,
        "tool_calls": [{"name": tool_name, "args": tool_args, "result": tool_result}],
    }


if __name__ == "__main__":
    system_prompt = load_system_prompt()
    outcome = call_gemini_with_tools(
        "My membership number is HS-2023-000303. What is my current active loan status?",
        system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
    )
    print("Final answer:\n", outcome["final_text"])
    print("\nTool calls:\n", json.dumps(outcome["tool_calls"], indent=2))
