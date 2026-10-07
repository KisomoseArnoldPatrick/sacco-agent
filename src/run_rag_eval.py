
import json
import sys
import time
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from src.rag import answer_question

TEST_CASES = [
    # --- Answerable (evidence fully covers the question) ---
    {
        "id": "R01",
        "category": "answerable",
        "question": "What documents are required for a loan application?",
        "expected_sources_hint": "supporting_documents.md, loan_requirements.md",
    },
    {
        "id": "R02",
        "category": "answerable",
        "question": "How many guarantors are required for a Development Loan?",
        "expected_sources_hint": "guarantor_requirements.md, development_loan.md",
    },
    {
        "id": "R03",
        "category": "answerable",
        "question": "What penalty applies if I pay my loan late?",
        "expected_sources_hint": "repayment_policy.md, interest_rates_summary.md",
    },
    {
        "id": "R04",
        "category": "answerable",
        "question": "How quickly is an Emergency Loan disbursed after it is approved?",
        "expected_sources_hint": "emergency_loan.md, loan_application_procedure.md",
    },
    {
        "id": "R05",
        "category": "answerable",
        "question": "What is the minimum monthly contribution for a Regular Savings Account?",
        "expected_sources_hint": "savings_products.md",
    },
    # --- Partially answerable (evidence covers part of the question) ---
    {
        "id": "R06",
        "category": "partial",
        "question": "What exact dividend rate will I receive this year?",
        "expected_sources_hint": "dividends_and_profit_sharing.md (process is documented, no fixed rate exists)",
    },
    {
        "id": "R07",
        "category": "partial",
        "question": "I want a Development Loan of UGX 10,000,000 — what will my exact monthly repayment be?",
        "expected_sources_hint": "development_loan.md (rate/term known, no calculator exists yet to compute the schedule)",
    },
    {
        "id": "R08",
        "category": "partial",
        "question": "I joined the SACCO one month ago — can I apply for an Emergency Loan right now?",
        "expected_sources_hint": "loan_requirements.md (general 3-month rule; no stated emergency exception)",
    },
    {
        "id": "R09",
        "category": "partial",
        "question": "If two guarantors back my UGX 3,000,000 Development Loan, how much savings must each guarantor individually hold?",
        "expected_sources_hint": "guarantor_requirements.md (only combined 20% minimum is stated, not the per-guarantor split)",
    },
    {
        "id": "R10",
        "category": "partial",
        "question": "How do I appeal if the Credit Committee rejects my loan restructuring request?",
        "expected_sources_hint": "complaints_and_grievance_procedure.md covers appeal of a loan REJECTION, not restructuring rejection specifically",
    },
    # --- Deliberately unanswerable (no coverage in corpus) ---
    {
        "id": "R11",
        "category": "unanswerable",
        "question": "Does Hangs SACCO offer mortgage or home loans?",
        "expected_sources_hint": "none — not covered",
    },
    {
        "id": "R12",
        "category": "unanswerable",
        "question": "Can I use my Development Loan to invest in cryptocurrency?",
        "expected_sources_hint": "none — not covered",
    },
    {
        "id": "R13",
        "category": "unanswerable",
        "question": "What is Hangs SACCO's SWIFT/routing code for international wire transfers?",
        "expected_sources_hint": "none — not covered",
    },
    {
        "id": "R14",
        "category": "unanswerable",
        "question": "Can I transfer my membership to a Hangs SACCO branch in another district?",
        "expected_sources_hint": "none — not covered",
    },
    {
        "id": "R15",
        "category": "unanswerable",
        "question": "What credit score does Hangs SACCO's system assign to members?",
        "expected_sources_hint": "none — not covered",
    },
]


def run_all():
    results = []
    for case in TEST_CASES:
        print(f"\n=== {case['id']} [{case['category']}] ===")
        print(f"Q: {case['question']}")
        try:
            outcome = answer_question(case["question"])
            print(f"Answer: {outcome['answer']}")
            print(f"Sources: {outcome['sources']}")
            print(f"Grounded: {outcome['grounded']}")
            results.append({**case, **outcome})
        except Exception as e:
            print(f"ERROR on {case['id']}: {e}")
            results.append({**case, "answer": None, "sources": [], "grounded": None, "error": str(e)})
        finally:
            time.sleep(5)
    return results


if __name__ == "__main__":
    all_results = run_all()
    out_path = Path(__file__).resolve().parent.parent / "evidence" / "week3_rag_evaluation.json"
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2)
    print(f"\nSaved {len(all_results)} results to {out_path}")