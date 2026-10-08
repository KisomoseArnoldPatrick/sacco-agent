"""
Week 4 — SACCO Tool Implementations

Approved tools for the Week 5 bounded SACCO case-preparation agent:

1. get_member_record
2. retrieve_policy
3. calculate_repayment

All authorization and deterministic validation is enforced in Python.
The model may request a tool, but the model itself never performs
authorization checks or financial calculations.

IMPORTANT:
These tools operate only on synthetic/local project data.
They do not perform real financial transactions.
"""

import json
from pathlib import Path


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

MEMBER_RECORDS_PATH = (
    REPO_ROOT / "data" / "member_records.json"
)

POLICY_DIR = (
    REPO_ROOT / "knowledge"
)


# ---------------------------------------------------------------------------
# SACCO Product Configuration
# ---------------------------------------------------------------------------

PRODUCT_TERMS = {
    "Development Loan": {
        "annual_rate_percent": 12,
        "method": "reducing_balance",
        "max_amount": 10_000_000,
        "max_term_months": 24,
        "source_document": "development_loan.md",
    },
    "Emergency Loan": {
        "annual_rate_percent": 10,
        "method": "flat",
        "max_amount": 2_000_000,
        "max_term_months": 6,
        "source_document": "emergency_loan.md",
    },
    "School Fees Loan": {
        "annual_rate_percent": 11,
        "method": "reducing_balance",
        "max_amount": 5_000_000,
        "max_term_months": 12,
        "source_document": "school_fees_loan.md",
    },
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _load_member_records() -> dict:
    """Load synthetic SACCO member records."""

    with open(MEMBER_RECORDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalise_text(value: str) -> str:
    """Normalise text for simple case-insensitive searching."""

    return " ".join(value.lower().split())


# ---------------------------------------------------------------------------
# Tool 1 — get_member_record
# ---------------------------------------------------------------------------

def get_member_record(
    membership_number: str,
    requester_role: str,
    requester_membership_number: str = None,
) -> dict:
    """
    Read-only lookup of a synthetic member record.

    Authorization:
    - member: may retrieve ONLY their own record.
    - officer: may retrieve any authorized record.
    - anything else: rejected.

    This function does not modify any data.
    """

    if not membership_number:
        return {
            "error": "invalid_parameters",
            "message": "membership_number is required.",
        }

    if requester_role not in ("member", "officer"):
        return {
            "error": "unauthorized",
            "message": f"Unknown requester role '{requester_role}'.",
        }

    if (
        requester_role == "member"
        and requester_membership_number != membership_number
    ):
        return {
            "error": "unauthorized",
            "message": (
                "A member may only retrieve their own membership record."
            ),
        }

    try:
        records = _load_member_records()

    except FileNotFoundError:
        return {
            "error": "service_unavailable",
            "message": (
                "Member records store could not be reached."
            ),
        }

    except json.JSONDecodeError:
        return {
            "error": "invalid_data",
            "message": (
                "Member records store contains invalid JSON."
            ),
        }

    record = records.get(membership_number)

    if record is None:
        return {
            "error": "not_found",
            "message": (
                f"No member record found for {membership_number}."
            ),
        }

    return {
        "membership_number": membership_number,
        **record,
    }


# ---------------------------------------------------------------------------
# Tool 2 — retrieve_policy
# ---------------------------------------------------------------------------

def retrieve_policy(
    query: str,
    loan_product: str = None,
    policy_override: str = None,
) -> dict:
    """
    Retrieve relevant SACCO policy/procedure text from the approved
    local knowledge base.

    This tool is read-only.

    Normal operation:
        - If loan_product is supplied, use its configured policy document.
        - Otherwise search all Markdown policy documents.

    Testing:
        - policy_override may be used to deliberately specify a policy
          filename, such as a nonexistent file, so missing-file behavior
          can be tested without modifying the real knowledge base.

    The tool never invents policy information.
    """

    # ------------------------------------------------------------------
    # Validate query
    # ------------------------------------------------------------------

    if not query or not str(query).strip():
        return {
            "error": "invalid_parameters",
            "message": "A policy query is required.",
        }

    # ------------------------------------------------------------------
    # Validate knowledge base directory
    # ------------------------------------------------------------------

    if not POLICY_DIR.exists():
        return {
            "error": "service_unavailable",
            "message": (
                f"Policy knowledge base was not found at: {POLICY_DIR}"
            ),
        }

    # ------------------------------------------------------------------
    # Determine candidate policy files
    # ------------------------------------------------------------------

    candidate_files = []

    # policy_override is intended for controlled testing.
    # It takes precedence over normal product selection.
    if policy_override:

        override_path = POLICY_DIR / policy_override

        # Prevent the test parameter from escaping the knowledge directory.
        try:
            override_path.resolve().relative_to(
                POLICY_DIR.resolve()
            )
        except ValueError:
            return {
                "error": "invalid_parameters",
                "message": (
                    "policy_override must refer to a file inside "
                    "the policy knowledge base."
                ),
            }

        candidate_files.append(override_path)

    elif loan_product:

        product = PRODUCT_TERMS.get(loan_product)

        if product is None:
            return {
                "error": "unknown_product",
                "message": (
                    f"'{loan_product}' is not a recognized loan product."
                ),
                "known_products": list(PRODUCT_TERMS.keys()),
            }

        candidate_files.append(
            POLICY_DIR / product["source_document"]
        )

    else:

        # Search all Markdown policy documents.
        candidate_files = sorted(
            POLICY_DIR.glob("*.md")
        )

    # ------------------------------------------------------------------
    # No candidate documents
    # ------------------------------------------------------------------

    if not candidate_files:
        return {
            "error": "not_found",
            "message": (
                "No policy documents were found in the knowledge base."
            ),
        }

    # ------------------------------------------------------------------
    # Explicitly detect a missing requested document
    # ------------------------------------------------------------------

    missing_files = [
        str(policy_file)
        for policy_file in candidate_files
        if not policy_file.exists()
    ]

    if missing_files:

        return {
            "error": "not_found",
            "message": (
                "The requested policy document was not found "
                "in the knowledge base."
            ),
            "missing_files": missing_files,
            "query": query,
            "loan_product": loan_product,
        }

    # ------------------------------------------------------------------
    # Search policy content
    # ------------------------------------------------------------------

    query_terms = _normalise_text(query).split()

    matches = []

    for policy_file in candidate_files:

        try:
            content = policy_file.read_text(
                encoding="utf-8"
            )

        except OSError as exc:

            return {
                "error": "service_unavailable",
                "message": (
                    f"Could not read policy document "
                    f"'{policy_file.name}'."
                ),
                "details": str(exc),
            }

        normalised_content = _normalise_text(content)

        # Simple deterministic keyword relevance.
        matched_terms = [
            term
            for term in query_terms
            if term and term in normalised_content
        ]

        # When a specific product/policy is explicitly requested,
        # returning that document is allowed even if no individual
        # query keyword matched.
        if matched_terms or loan_product or policy_override:

            matches.append(
                {
                    "document": policy_file.name,
                    "matched_terms": matched_terms,
                    "content": content,
                }
            )

    # ------------------------------------------------------------------
    # No relevant information
    # ------------------------------------------------------------------

    if not matches:
        return {
            "error": "not_found",
            "message": (
                "No relevant policy information was found "
                "for the request."
            ),
            "query": query,
        }

    # ------------------------------------------------------------------
    # Successful retrieval
    # ------------------------------------------------------------------

    return {
        "query": query,
        "loan_product": loan_product,
        "results": matches,
        "read_only": True,
    }


# ---------------------------------------------------------------------------
# Tool 3 — calculate_repayment
# ---------------------------------------------------------------------------

def calculate_repayment(
    loan_product: str,
    principal,
    term_months,
) -> dict:
    """
    Deterministic illustrative repayment calculation.

    The calculation uses the configured product terms and policy limits.
    It does not approve, reject, score, or commit a loan.
    """

    if loan_product not in PRODUCT_TERMS:
        return {
            "error": "unknown_product",
            "message": (
                f"'{loan_product}' is not a recognized loan product."
            ),
            "known_products": list(PRODUCT_TERMS.keys()),
        }

    if principal is None or term_months is None:
        return {
            "error": "invalid_parameters",
            "message": (
                "principal and term_months are both required."
            ),
        }

    try:
        principal = float(principal)
        term_months = int(term_months)

    except (TypeError, ValueError):
        return {
            "error": "invalid_parameters",
            "message": (
                "principal must be numeric and term_months an integer."
            ),
        }

    if principal <= 0 or term_months <= 0:
        return {
            "error": "invalid_parameters",
            "message": (
                "principal and term_months must be positive."
            ),
        }

    product = PRODUCT_TERMS[loan_product]

    # Product amount limit
    if principal > product["max_amount"]:
        return {
            "error": "exceeds_policy_limit",
            "message": (
                f"Requested principal exceeds the "
                f"{loan_product} maximum of "
                f"UGX {product['max_amount']:,}."
            ),
            "policy_basis": product["source_document"],
        }

    # Product term limit
    if term_months > product["max_term_months"]:
        return {
            "error": "exceeds_policy_limit",
            "message": (
                f"Requested term exceeds the "
                f"{loan_product} maximum of "
                f"{product['max_term_months']} months."
            ),
            "policy_basis": product["source_document"],
        }

    annual_rate = product["annual_rate_percent"]
    method = product["method"]

    if method == "reducing_balance":

        monthly_rate = annual_rate / 100 / 12

        installment = (
            principal
            * monthly_rate
            / (1 - (1 + monthly_rate) ** -term_months)
        )

        total_repayable = installment * term_months
        total_interest = total_repayable - principal

    else:
        # Flat-rate calculation
        total_interest = (
            principal
            * (annual_rate / 100)
            * (term_months / 12)
        )

        total_repayable = principal + total_interest
        installment = total_repayable / term_months

    return {
        "loan_product": loan_product,
        "principal_ugx": round(principal, 2),
        "annual_rate_percent": annual_rate,
        "method": method,
        "term_months": term_months,
        "monthly_installment_ugx": round(installment, 2),
        "total_interest_ugx": round(total_interest, 2),
        "total_repayable_ugx": round(total_repayable, 2),
        "policy_basis": product["source_document"],
        "illustrative": True,
        "decision": "calculation_only",
    }