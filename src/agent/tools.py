"""
Week 4 — Tool implementations.

Both tools enforce their own authorization and validation deterministically
in Python. The model may request that a tool be called, but never performs
authorization checks or calculations itself.
"""
import json
from pathlib import Path

MEMBER_RECORDS_PATH = Path(__file__).resolve().parent / "data" / "member_records.json"

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


def _load_member_records() -> dict:
    with open(MEMBER_RECORDS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_member_record(membership_number: str, requester_role: str,
                       requester_membership_number: str = None) -> dict:
    """Read-only lookup of a synthetic member record.

    Authorization (enforced here, never by the model):
    - requester_role == "officer": may retrieve any record.
    - requester_role == "member": may retrieve ONLY their own record.
    - anything else is rejected.
    """
    if not membership_number:
        return {"error": "invalid_parameters", "message": "membership_number is required."}

    if requester_role not in ("member", "officer"):
        return {"error": "unauthorized", "message": f"Unknown requester role '{requester_role}'."}

    if requester_role == "member" and requester_membership_number != membership_number:
        return {
            "error": "unauthorized",
            "message": "A member may only retrieve their own membership record.",
        }

    try:
        records = _load_member_records()
    except FileNotFoundError:
        return {"error": "service_unavailable", "message": "Member records store could not be reached."}

    record = records.get(membership_number)
    if record is None:
        return {"error": "not_found", "message": f"No member record found for {membership_number}."}

    return {"membership_number": membership_number, **record}


def calculate_repayment(loan_product: str, principal, term_months) -> dict:
    """Deterministic repayment calculation, validated against documented
    product policy limits. Never guesses a rate or term.
    """
    if loan_product not in PRODUCT_TERMS:
        return {
            "error": "unknown_product",
            "message": f"'{loan_product}' is not a recognized loan product.",
            "known_products": list(PRODUCT_TERMS.keys()),
        }

    if principal is None or term_months is None:
        return {"error": "invalid_parameters", "message": "principal and term_months are both required."}

    try:
        principal = float(principal)
        term_months = int(term_months)
    except (TypeError, ValueError):
        return {"error": "invalid_parameters", "message": "principal must be numeric and term_months an integer."}

    if principal <= 0 or term_months <= 0:
        return {"error": "invalid_parameters", "message": "principal and term_months must be positive."}

    product = PRODUCT_TERMS[loan_product]

    if principal > product["max_amount"]:
        return {
            "error": "exceeds_policy_limit",
            "message": f"Requested principal exceeds the {loan_product} maximum of UGX {product['max_amount']:,}.",
            "policy_basis": product["source_document"],
        }

    if term_months > product["max_term_months"]:
        return {
            "error": "exceeds_policy_limit",
            "message": f"Requested term exceeds the {loan_product} maximum of {product['max_term_months']} months.",
            "policy_basis": product["source_document"],
        }

    annual_rate = product["annual_rate_percent"]
    method = product["method"]

    if method == "reducing_balance":
        monthly_rate = annual_rate / 100 / 12
        installment = principal * monthly_rate / (1 - (1 + monthly_rate) ** -term_months)
        total_repayable = installment * term_months
        total_interest = total_repayable - principal
    else:  # flat
        total_interest = principal * (annual_rate / 100) * (term_months / 12)
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
    }
