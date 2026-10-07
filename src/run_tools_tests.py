"""
Week 4 — Deliberate failure and authorization tests.

Each case tries to break a tool on purpose (missing parameters,
unauthorized access, unknown inputs, policy-limit violations) and records
the actual tool response for evidence. These call the tools directly
(not through Gemini) so we test the deterministic enforcement itself,
independent of whether the model happens to phrase a request a certain
way.
"""
import json
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from tools import get_member_record, calculate_repayment

TEST_CASES = [
    {
        "id": "T01",
        "description": "Valid request: member retrieves their own record",
        "call": lambda: get_member_record("HS-2023-000303", "member", "HS-2023-000303"),
        "expected": "success",
    },
    {
        "id": "T02",
        "description": "Unauthorized: member tries to retrieve a different member's record",
        "call": lambda: get_member_record("HS-2024-000101", "member", "HS-2023-000303"),
        "expected": "unauthorized",
    },
    {
        "id": "T03",
        "description": "Authorized: officer retrieves any member's record",
        "call": lambda: get_member_record("HS-2024-000101", "officer", None),
        "expected": "success",
    },
    {
        "id": "T04",
        "description": "Missing parameter: no membership_number supplied",
        "call": lambda: get_member_record("", "officer", None),
        "expected": "invalid_parameters",
    },
    {
        "id": "T05",
        "description": "Unknown role supplied",
        "call": lambda: get_member_record("HS-2023-000303", "guest", None),
        "expected": "unauthorized",
    },
    {
        "id": "T06",
        "description": "Not found: well-formed but non-existent membership number",
        "call": lambda: get_member_record("HS-2099-999999", "officer", None),
        "expected": "not_found",
    },
    {
        "id": "T07",
        "description": "Valid calculation: Development Loan within policy limits",
        "call": lambda: calculate_repayment("Development Loan", 5_000_000, 12),
        "expected": "success",
    },
    {
        "id": "T08",
        "description": "Policy violation: principal exceeds Development Loan maximum",
        "call": lambda: calculate_repayment("Development Loan", 50_000_000, 12),
        "expected": "exceeds_policy_limit",
    },
    {
        "id": "T09",
        "description": "Policy violation: term exceeds Emergency Loan maximum",
        "call": lambda: calculate_repayment("Emergency Loan", 500_000, 24),
        "expected": "exceeds_policy_limit",
    },
    {
        "id": "T10",
        "description": "Unknown product supplied",
        "call": lambda: calculate_repayment("Mortgage Loan", 1_000_000, 12),
        "expected": "unknown_product",
    },
    {
        "id": "T11",
        "description": "Missing parameters: no principal or term supplied",
        "call": lambda: calculate_repayment("Development Loan", None, None),
        "expected": "invalid_parameters",
    },
    {
        "id": "T12",
        "description": "Invalid parameters: negative principal",
        "call": lambda: calculate_repayment("Development Loan", -500_000, 12),
        "expected": "invalid_parameters",
    },
    {
        "id": "T13",
        "description": "Invalid parameters: non-numeric principal",
        "call": lambda: calculate_repayment("Development Loan", "a lot of money", 12),
        "expected": "invalid_parameters",
    },
]


def run_all():
    results = []
    for case in TEST_CASES:
        print(f"\n=== {case['id']} ===")
        print(case["description"])
        try:
            result = case["call"]()
        except Exception as e:
            result = {"error": "unhandled_exception", "message": str(e)}
        print(json.dumps(result, indent=2))

        actual = "success" if "error" not in result else result["error"]
        passed = (actual == case["expected"])
        print(f"Expected: {case['expected']} | Actual: {actual} | {'PASS' if passed else 'FAIL'}")

        results.append({**case, "call": None, "result": result, "actual": actual, "passed": passed})
    return results


if __name__ == "__main__":
    all_results = run_all()
    out_path = Path(__file__).resolve().parent.parent / "evidence" / "week4_tool_tests.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)

    passed_count = sum(1 for r in all_results if r["passed"])
    print(f"\n{passed_count}/{len(all_results)} tests passed. Saved results to {out_path}")