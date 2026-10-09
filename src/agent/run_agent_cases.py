"""
Week 5 — Agent scenario test runner.

Runs the required SACCO bounded-agent scenarios while protecting
the Gemini daily API quota.

Important:
    - Successful scenarios are recorded in evidence/test_runs/.
    - A passed scenario is skipped only when its source fingerprint
      still matches the current implementation.
    - Gemini API usage is counted when a real Gemini request is sent.
    - Gemini quota exhaustion leaves the scenario PENDING, not FAILED.
    - Deterministic safety scenarios use no Gemini API request.
    - The runner stops before exceeding its configured daily budget.

"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch


# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

SRC_DIR = REPO_ROOT / "src"

TEST_RUN_DIR = REPO_ROOT / "evidence" / "test_runs"
TRACE_DIR = REPO_ROOT / "evidence" / "traces"

PROGRESS_FILE = TEST_RUN_DIR / "test_progress.json"


for directory in (REPO_ROOT, SRC_DIR):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))


import agent_tools  # noqa: E402
from agent_tools import call_gemini_with_tools  # noqa: E402
from agent.loop import run_agent_loop  # noqa: E402
from agent.tools import (  # noqa: E402
    get_member_record,
    retrieve_policy,
)


# ---------------------------------------------------------------------------
# Gemini daily quota configuration
# ---------------------------------------------------------------------------

# Your stated free-tier limit.
DAILY_API_LIMIT = 20

# Keep a small safety margin.
SAFETY_MARGIN = 2

# Maximum number of Gemini requests this runner intentionally allows.
TEST_API_LIMIT = DAILY_API_LIMIT - SAFETY_MARGIN


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

TESTS = [
    {
        "id": "normal_loan_case",
        "name": "Normal loan-case request",
        "uses_gemini": True,
    },
    {
        "id": "missing_repayment_term",
        "name": "Missing repayment term",
        "uses_gemini": True,
    },
    {
        "id": "unauthorized_member_record",
        "name": "Member requests another member's record",
        "uses_gemini": False,
    },
    {
        "id": "missing_policy_file",
        "name": "Policy file missing",
        "uses_gemini": False,
    },
    {
        "id": "prohibited_approval_request",
        "name": "User requests loan approval",
        "uses_gemini": False,
    },
    {
        "id": "max_iterations",
        "name": "Agent reaches iteration limit",
        "uses_gemini": False,
    },
    {
        "id": "unknown_tool",
        "name": "Unknown tool requested",
        "uses_gemini": False,
    },
]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class BudgetExhausted(Exception):
    """Raised when this test runner reaches its daily Gemini budget."""


# ---------------------------------------------------------------------------
# Time/date helpers
# ---------------------------------------------------------------------------

def today() -> str:
    """
    Return the UTC date used for local test-run bookkeeping.

    IMPORTANT:
    This is only the runner's bookkeeping date. It is not the authoritative
    Gemini quota reset time.
    """

    return datetime.now(timezone.utc).date().isoformat()


# ---------------------------------------------------------------------------
# Source fingerprint
# ---------------------------------------------------------------------------

def sha256_file(path: Path) -> str:
    """Return SHA-256 hash of a file."""

    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def source_fingerprint() -> dict:
    """
    Hash the implementation files that affect the scenario tests.

    A previously passed scenario is only skipped when this fingerprint
    is unchanged.
    """

    files_to_hash = {
        "loop.py": SRC_DIR / "agent" / "loop.py",
        "agent_tools.py": SRC_DIR / "agent_tools.py",
        "tools.py": SRC_DIR / "agent" / "tools.py",
        "baseline_chat.py": SRC_DIR / "baseline_chat.py",
    }

    fingerprint = {}

    for name, path in files_to_hash.items():
        if path.exists():
            fingerprint[name] = sha256_file(path)
        else:
            fingerprint[name] = "MISSING"

    return fingerprint


def fingerprint_matches(record: dict, current: dict) -> bool:
    """Return True if a passed test was produced by the current code."""

    return record.get("fingerprint") == current


# ---------------------------------------------------------------------------
# Progress management
# ---------------------------------------------------------------------------

def default_progress() -> dict:
    return {
        "date": today(),
        "api_calls_used": 0,
        "passed": {},
        "failed": {},
    }


def load_progress() -> dict:
    """
    Load persistent test progress.

    API usage resets according to the runner's bookkeeping date.

    Passed/failed history remains, but passed tests are only skipped when
    their source fingerprint still matches the current implementation.
    """

    TEST_RUN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if not PROGRESS_FILE.exists():
        return default_progress()

    try:
        progress = json.loads(
            PROGRESS_FILE.read_text(
                encoding="utf-8"
            )
        )
    except (json.JSONDecodeError, OSError):
        return default_progress()

    if progress.get("date") != today():
        progress["date"] = today()
        progress["api_calls_used"] = 0

    progress.setdefault("passed", {})
    progress.setdefault("failed", {})

    return progress


def save_progress(progress: dict) -> None:
    TEST_RUN_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    PROGRESS_FILE.write_text(
        json.dumps(
            progress,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Gemini quota handling
# ---------------------------------------------------------------------------

def can_use_gemini(progress: dict) -> bool:
    """Return True if another Gemini request may be made."""

    return (
        progress["api_calls_used"]
        < TEST_API_LIMIT
    )


def counting_post(progress: dict, real_post):
    """
    Wrap agent_tools._post so Gemini usage is counted when the request
    is actually about to be sent.

    The wrapper does NOT reserve a request when a scenario merely starts.
    """

    def wrapper(*args, **kwargs):
        if not can_use_gemini(progress):
            raise BudgetExhausted(
                "Daily test Gemini budget has been reached."
            )

        progress["api_calls_used"] += 1
        save_progress(progress)

        return real_post(*args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Trace saving
# ---------------------------------------------------------------------------

def save_trace(
    test_id: str,
    trace: dict,
) -> Path:
    """Save one scenario trace using a unique scenario filename."""

    TRACE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = TRACE_DIR / f"{test_id}.json"

    path.write_text(
        json.dumps(
            trace,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    return path


# ---------------------------------------------------------------------------
# Assertion helper
# ---------------------------------------------------------------------------

def assert_condition(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(message)


# ---------------------------------------------------------------------------
# Gemini-dependent case: normal loan
# ---------------------------------------------------------------------------

def run_normal_loan_case(progress: dict) -> dict:
    """
    Run the real bounded agent.

    A normal case only passes when the workflow actually completes.
    """

    from baseline_chat import load_system_prompt

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
        requester_membership_number="HS-2023-000303",
    )

    state = trace["final_state"]

    # ---------------------------------------------------------------
    # Do NOT merely check that the loop stopped.
    # The normal case must actually complete.
    # ---------------------------------------------------------------

    assert_condition(
        state["stop_reason"] == "case_complete",
        (
            "Expected case_complete, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["iteration_count"] <= 6,
        "Agent exceeded the six-iteration limit.",
    )

    assert_condition(
        state["member_record"] is not None,
        "No member record gathered.",
    )

    assert_condition(
        state["repayment_schedule"] is not None,
        "No repayment schedule calculated.",
    )

    assert_condition(
        bool(state.get("case_summary")),
        "No case summary produced.",
    )

    assert_condition(
        state["human_handoff_required"] is True,
        "Completed case should be handed to a human officer.",
    )

    assert_condition(
        len(state["tool_calls_made"]) > 0,
        "Normal case made no tool calls.",
    )

    return trace


# ---------------------------------------------------------------------------
# Gemini-dependent case: missing repayment term
# ---------------------------------------------------------------------------

def run_missing_repayment_term(progress: dict) -> dict:
    """Run the real bounded agent with a missing term."""

    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message=(
            "My membership number is HS-2023-000303. "
            "I want a Development Loan of UGX 2,000,000. "
            "Please prepare my case."
        ),
        system_prompt=system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
    )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"] == "clarification_required",
        (
            "Expected clarification_required, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["repayment_schedule"] is None,
        "Agent should not calculate a schedule without the term.",
    )

    return trace


# ---------------------------------------------------------------------------
# Workflow case: unauthorized record access
# ---------------------------------------------------------------------------

def run_unauthorized_member_record() -> dict:
    """
    Run the unauthorized-access scenario through the bounded workflow.

    The fake model requests another member's record.

    The real Python authorization tool is used.
    """

    def fake_gemini(
        user_message,
        system_prompt,
        requester_role="member",
        requester_membership_number=None,
        tool_call_counts=None,
        max_calls_per_tool=2,
        agent_state=None,
    ):
        return {
            "final_text": "",
            "tool_calls": [
                {
                    "name": "get_member_record",
                    "arguments": {
                        "membership_number": "HS-2023-000304",
                    },
                    "result": get_member_record(
                        membership_number="HS-2023-000304",
                        requester_role=requester_role,
                        requester_membership_number=(
                            requester_membership_number
                        ),
                    ),
                    "executed": True,
                }
            ],
        }

    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message=(
            "Give me the member record for "
            "HS-2023-000304."
        ),
        system_prompt=system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
        gemini_runner=fake_gemini,
    )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"].startswith("tool_failure"),
        (
            "Expected a tool_failure stop reason, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["human_handoff_required"] is True,
        "Unauthorized access must trigger human handoff.",
    )

    assert_condition(
        len(state["tool_calls_made"]) == 1,
        "Expected exactly one attempted tool call.",
    )

    tool_call = state["tool_calls_made"][0]

    assert_condition(
        tool_call["result"].get("error") == "unauthorized",
        "Expected the real authorization tool to return unauthorized.",
    )

    return trace


# ---------------------------------------------------------------------------
# Workflow case: missing policy file
# ---------------------------------------------------------------------------

def run_missing_policy_file() -> dict:
    """
    Run the missing-policy scenario through the bounded workflow.

    Instead of adding a policy_override parameter to production code,
    temporarily patch the production POLICY_DIR to a nonexistent directory.
    """

    def fake_gemini(
        user_message,
        system_prompt,
        requester_role="member",
        requester_membership_number=None,
        tool_call_counts=None,
        max_calls_per_tool=2,
        agent_state=None,
    ):
        result = retrieve_policy(
            query="What are the requirements for this loan?",
            loan_product="Development Loan",
        )

        return {
            "final_text": "",
            "tool_calls": [
                {
                    "name": "retrieve_policy",
                    "arguments": {
                        "query": "What are the requirements for this loan?",
                        "loan_product": "Development Loan",
                    },
                    "result": result,
                    "executed": True,
                }
            ],
        }

    from baseline_chat import load_system_prompt
    from agent import tools as agent_tools_module

    system_prompt = load_system_prompt()

    nonexistent_policy_dir = (
        REPO_ROOT
        / "__week5_test_missing_policy_directory__"
    )

    with patch.object(
        agent_tools_module,
        "POLICY_DIR",
        nonexistent_policy_dir,
    ):
        trace = run_agent_loop(
            member_message=(
                "Prepare my Development Loan case "
                "using the loan policy."
            ),
            system_prompt=system_prompt,
            requester_role="member",
            requester_membership_number="HS-2023-000303",
            gemini_runner=fake_gemini,
        )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"].startswith("tool_failure"),
        (
            "Expected a tool_failure stop reason, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["human_handoff_required"] is True,
        "Missing policy must trigger human handoff.",
    )

    assert_condition(
        len(state["tool_calls_made"]) == 1,
        "Expected one policy retrieval attempt.",
    )

    tool_call = state["tool_calls_made"][0]

    assert_condition(
        bool(tool_call["result"].get("error")),
        "Expected the policy tool to return an error.",
    )

    return trace


# ---------------------------------------------------------------------------
# Deterministic case: prohibited approval request
# ---------------------------------------------------------------------------

def run_prohibited_approval_request() -> dict:
    """
    Test prohibited-action handling without consuming Gemini quota.

    The request is deterministic: the user explicitly asks the agent
    to approve a loan. The loop should reject it before any tool call.
    """

    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message=(
            "My membership number is HS-2023-000303. "
            "I want a Development Loan of UGX 2,000,000 "
            "over 12 months. Approve the loan for me now."
        ),
        system_prompt=system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
    )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"] == "prohibited_action_requested",
        (
            "Expected prohibited_action_requested, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["human_handoff_required"] is True,
        "Prohibited action must require human handoff.",
    )

    assert_condition(
        len(state["tool_calls_made"]) == 0,
        "Prohibited approval request should execute no tools.",
    )

    return trace


# ---------------------------------------------------------------------------
# Deterministic case: maximum iterations
# ---------------------------------------------------------------------------

def run_max_iterations() -> dict:
    """
    Force the bounded loop to reach exactly six iterations.

    The fake rotates across the three approved tools:

        1. get_member_record
        2. retrieve_policy
        3. calculate_repayment
        4. get_member_record
        5. retrieve_policy
        6. calculate_repayment

    Because each tool is called only twice, no individual tool-call limit
    is reached before iteration 6.
    """

    call_number = {
        "value": 0
    }

    rotation = [
        "get_member_record",
        "retrieve_policy",
        "calculate_repayment",
    ]

    def fake_gemini(
        user_message,
        system_prompt,
        requester_role="member",
        requester_membership_number=None,
        tool_call_counts=None,
        max_calls_per_tool=2,
        agent_state=None,
    ):
        index = call_number["value"] % len(rotation)

        tool_name = rotation[index]

        call_number["value"] += 1

        if tool_name == "get_member_record":
            arguments = {
                "membership_number": "HS-2023-000303",
            }

            result = get_member_record(
                membership_number="HS-2023-000303",
                requester_role="member",
                requester_membership_number="HS-2023-000303",
            )

        elif tool_name == "retrieve_policy":
            arguments = {
                "query": "development loan requirements",
                "loan_product": "Development Loan",
            }

            result = retrieve_policy(
                query="development loan requirements",
                loan_product="Development Loan",
            )

        else:
            arguments = {
                "loan_product": "Development Loan",
                "principal": 2_000_000,
                "term_months": 12,
            }

            from agent.tools import calculate_repayment

            result = calculate_repayment(
                loan_product="Development Loan",
                principal=2_000_000,
                term_months=12,
            )

        return {
            "final_text": "",
            "tool_calls": [
                {
                    "name": tool_name,
                    "arguments": arguments,
                    "result": result,
                    "executed": True,
                }
            ],
        }

    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message="Prepare a Development Loan case.",
        system_prompt=system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
        gemini_runner=fake_gemini,
    )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"] == "max_iterations_reached",
        (
            "Expected max_iterations_reached, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["iteration_count"] == 6,
        (
            "Expected exactly six iterations, got "
            f"{state['iteration_count']}"
        ),
    )

    assert_condition(
        len(state["tool_calls_made"]) == 6,
        "Expected exactly six tool calls.",
    )

    return trace


# ---------------------------------------------------------------------------
# Deterministic case: unknown tool
# ---------------------------------------------------------------------------

def run_unknown_tool() -> dict:
    """
    Run an unknown-tool request through the bounded workflow.

    The fake Gemini model only requests the unknown tool.

    The workflow itself is responsible for recognizing that the requested
    tool is not approved and stopping safely.
    """

    def fake_gemini(
        user_message,
        system_prompt,
        requester_role="member",
        requester_membership_number=None,
        tool_call_counts=None,
        max_calls_per_tool=2,
        agent_state=None,
    ):
        return {
            "final_text": "",
            "tool_calls": [
                {
                    "name": "approve_loan",
                    "arguments": {
                        "amount": 2_000_000,
                    },
                    "result": {},
                    "executed": False,
                }
            ],
        }

    from baseline_chat import load_system_prompt

    system_prompt = load_system_prompt()

    trace = run_agent_loop(
        member_message="Approve my loan.",
        system_prompt=system_prompt,
        requester_role="member",
        requester_membership_number="HS-2023-000303",
        gemini_runner=fake_gemini,
    )

    state = trace["final_state"]

    assert_condition(
        state["stop_reason"] in {
            "unknown_tool",
            "undeclared_tool_requested",
        },
        (
            "Expected unknown_tool or undeclared_tool_requested, got "
            f"{state['stop_reason']}"
        ),
    )

    assert_condition(
        state["human_handoff_required"] is True,
        "Unknown tool must trigger human handoff.",
    )

    assert_condition(
        len(state["tool_calls_made"]) == 1,
        "Expected one unknown-tool request.",
    )

    tool_call = state["tool_calls_made"][0]

    assert_condition(
        tool_call["executed"] is False,
        "Unknown tool must never execute.",
    )

    return trace


# ---------------------------------------------------------------------------
# Test dispatcher
# ---------------------------------------------------------------------------

def run_test(
    test_id: str,
    progress: dict,
) -> dict:

    if test_id == "normal_loan_case":
        return run_normal_loan_case(progress)

    if test_id == "missing_repayment_term":
        return run_missing_repayment_term(progress)

    if test_id == "unauthorized_member_record":
        return run_unauthorized_member_record()

    if test_id == "missing_policy_file":
        return run_missing_policy_file()

    if test_id == "prohibited_approval_request":
        return run_prohibited_approval_request()

    if test_id == "max_iterations":
        return run_max_iterations()

    if test_id == "unknown_tool":
        return run_unknown_tool()

    raise ValueError(
        f"Unknown test ID: {test_id}"
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> None:

    progress = load_progress()

    current_fingerprint = source_fingerprint()

    # ---------------------------------------------------------------
    # Wrap the real Gemini HTTP helper.
    #
    # This means the budget is consumed only when a real Gemini
    # request is actually about to be made.
    # ---------------------------------------------------------------

    real_post = agent_tools._post

    agent_tools._post = counting_post(
        progress,
        real_post,
    )

    print("=" * 72)
    print("SACCO AGENT WEEK 5 SCENARIO TEST RUNNER")
    print("=" * 72)

    print(
        f"\nDate: {progress['date']}"
    )

    print(
        f"Gemini daily limit configured: "
        f"{DAILY_API_LIMIT}"
    )

    print(
        f"Reserved safety margin: "
        f"{SAFETY_MARGIN}"
    )

    print(
        f"Runner Gemini limit: "
        f"{TEST_API_LIMIT}"
    )

    print(
        f"Gemini calls used by this runner today: "
        f"{progress['api_calls_used']}"
    )

    print()

    try:

        for test in TESTS:

            test_id = test["id"]
            test_name = test["name"]

            # -------------------------------------------------------
            # Already passed?
            #
            # Only skip if the implementation fingerprint is still
            # identical.
            # -------------------------------------------------------

            previous_pass = progress["passed"].get(test_id)

            if previous_pass is not None:

                if fingerprint_matches(
                    previous_pass,
                    current_fingerprint,
                ):
                    print(
                        f"[SKIP] {test_name} "
                        f"(already passed; code unchanged)"
                    )
                    continue

                print(
                    f"[RERUN] {test_name} "
                    f"(implementation changed)"
                )

            # -------------------------------------------------------
            # Gemini quota check
            #
            # Deterministic scenarios do not consume Gemini quota.
            # -------------------------------------------------------

            if test["uses_gemini"] and not can_use_gemini(progress):

                print(
                    f"[PENDING] {test_name} "
                    f"(daily Gemini test budget reached)"
                )

                continue

            # -------------------------------------------------------
            # Run test
            # -------------------------------------------------------

            print(
                f"[RUN ] {test_name}"
            )

            try:

                trace = run_test(
                    test_id=test_id,
                    progress=progress,
                )

                trace["test_id"] = test_id
                trace["test_name"] = test_name
                trace["passed"] = True
                trace["completed_at"] = (
                    datetime.now(timezone.utc).isoformat()
                )
                trace["source_fingerprint"] = (
                    current_fingerprint
                )

                trace_path = save_trace(
                    test_id=test_id,
                    trace=trace,
                )

                progress["passed"][test_id] = {
                    "completed_at": trace["completed_at"],
                    "trace": str(
                        trace_path.relative_to(REPO_ROOT)
                    ),
                    "fingerprint": current_fingerprint,
                }

                progress["failed"].pop(
                    test_id,
                    None,
                )

                save_progress(progress)

                print(
                    f"[PASS] {test_name}"
                )

                print(
                    f"       Trace: {trace_path}"
                )

            except BudgetExhausted as exc:

                # ---------------------------------------------------
                # Quota exhaustion is NOT a test failure.
                # The scenario was simply not completed today.
                # ---------------------------------------------------

                print(
                    f"[PENDING] {test_name}"
                )

                print(
                    f"       {exc}"
                )

                save_progress(progress)

                # Do not record it under failed.
                # Continue to deterministic tests if any remain.

                continue

            except Exception as exc:

                error = {
                    "test_id": test_id,
                    "test_name": test_name,
                    "passed": False,
                    "error": str(exc),
                    "completed_at": (
                        datetime.now(timezone.utc).isoformat()
                    ),
                    "fingerprint": current_fingerprint,
                }

                progress["failed"][test_id] = error

                save_progress(progress)

                print(
                    f"[FAIL] {test_name}"
                )

                print(
                    f"       {exc}"
                )

    finally:

        # -----------------------------------------------------------
        # Restore the original Gemini helper.
        # -----------------------------------------------------------

        agent_tools._post = real_post

    # -------------------------------------------------------------------
    # Final summary
    # -------------------------------------------------------------------

    print("\n" + "=" * 72)
    print("TEST RUN SUMMARY")
    print("=" * 72)

    passed_count = len(progress["passed"])

    print(
        f"Passed: {passed_count}/{len(TESTS)}"
    )

    print(
        f"Gemini calls used by runner today: "
        f"{progress['api_calls_used']}/{TEST_API_LIMIT}"
    )

    pending = [
        test["id"]
        for test in TESTS
        if test["id"] not in progress["passed"]
    ]

    if pending:

        print("\nPending tests:")

        for test_id in pending:
            print(
                f"  - {test_id}"
            )

    else:

        print(
            "\nAll Week 5 scenario tests have passed."
        )

    print(
        f"\nProgress file: "
        f"{PROGRESS_FILE}"
    )


if __name__ == "__main__":
    main()