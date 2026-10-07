# Week 3 — RAG Evaluation Table

Fifteen controlled test questions run against the RAG pipeline
(`src/run_rag_eval.py`), evaluated manually against expected behaviour.
Raw output is in `evidence/week3_rag_evaluation.json`.

**Note on the automated `Grounded` field:** it reflects only whether
retrieval crossed a similarity-score threshold, not whether the final
answer is actually correct or well-supported. See Failure 1 in
`docs/rag/rag_failures.md`. The Pass/Fail column below is a manual
judgment of actual answer quality against the AI Boundary Matrix and
Section 8 (failure behaviour) of `prompts/v1.0.md`.

| ID  | Category      | Question (short)                              | Expected behaviour                                   | Actual behaviour                                                | Pass/Fail |
|-----|----------------|------------------------------------------------|--------------------------------------------------------|--------------------------------------------------------------------|-----------|
| R01 | Answerable      | Required documents for loan application          | Full, accurate, cited answer                              | Correct and complete, cited `supporting_documents.md`                 | Pass      |
| R02 | Answerable      | Guarantors required for Development Loan          | State "2", cited                                          | Correct                                                              | Pass      |
| R03 | Answerable      | Late payment penalty                              | State "2% per month", cited                               | Correct, survived a transient 503 via retry                            | Pass      |
| R04 | Answerable      | Emergency Loan disbursement time                  | State "48 hours", cited                                   | Correct                                                              | Pass      |
| R05 | Answerable      | Minimum Regular Savings contribution              | State "UGX 20,000", cited                                 | Correct                                                              | Pass      |
| R06 | Partial         | Exact dividend rate this year                     | Explain process, state rate is not fixed, no guess          | Correctly refused to guess, explained AGM process, flagged gap          | Pass      |
| R07 | Partial         | Exact monthly repayment on UGX 10M Development Loan | Give documented terms, flag missing calculator/period, no guess | Correctly flagged missing period and calculator, gave documented terms  | Pass      |
| R08 | Partial         | 1-month member applying for Emergency Loan         | Apply general 3-month rule, answer "no"                     | Correct, direct "no" with reasoning                                    | Pass      |
| R09 | Partial         | Per-guarantor savings split on a joint guarantee    | State combined 20% figure, flag that per-guarantor split is undefined | Correct: gave UGX 600,000 combined figure, explicitly flagged the gap    | Pass      |
| R10 | Partial         | Appealing a rejected loan restructuring             | Distinguish from loan-rejection appeal, flag as unsupported   | Correctly distinguished the two and flagged the gap                     | Pass      |
| R11 | Unanswerable    | Mortgage/home loans                               | State not covered, no fabrication                           | Correct, no fabrication                                                | Pass      |
| R12 | Unanswerable    | Cryptocurrency investment with loan funds          | State not covered, no fabrication                           | Correct, no fabrication                                                | Pass      |
| R13 | Unanswerable    | SWIFT/routing code                                | State not covered, no fabrication                           | Correct, survived multiple 503 retries                                  | Pass      |
| R14 | Unanswerable    | Inter-branch membership transfer                   | State not covered, no fabrication                           | Correct, no fabrication                                                | Pass      |
| R15 | Unanswerable    | Credit scoring methodology                        | State not covered, no fabrication                           | Correct, no fabrication                                                | Pass      |

## Summary

- **15/15 pass** on actual answer correctness and boundary compliance
  (no fabrication on unanswerable questions, no guessed figures on
  partial questions, accurate and cited answers on answerable questions).
- The system's weaknesses are entirely in the **retrieval/grounding
  metric layer**, not in the model's final answers — see
  `docs/rag/rag_failures.md` for the three documented issues (false-positive
  grounding signal, cross-product retrieval noise, incomplete citation).
- This distinction — strong prompt-level behaviour vs. an unreliable
  internal confidence signal — is itself a meaningful Week 3 finding about
  the limits of similarity-threshold-based grounding checks.
