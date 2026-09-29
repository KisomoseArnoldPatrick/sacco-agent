# AI Boundary Matrix — SACCO Loan Application Preparation Agent

Defines what the AI/agent can do, what the system controls with deterministic code, and what
requires human involvement.

Actors: SACCO Member (primary), SACCO Relationship Officer (secondary).
Assumptions (prototype): the member enters a member ID and the system uses only that member's
synthetic record (no real authentication). All records, transactions, forms and uploaded
documents are synthetic. Supported upload formats: text-based PDF and images.

> **AI = Understands and assists**
> **System = Calculates and enforces rules**
> **Human = Reviews and makes important decisions**

| Function | AI/Agent Can Do | System Must Control | Human Must Decide or Review |
|---|---|---|---|
| **Loan preference capture** | Converse with the member and ask clarifying questions | Validate amount and period as numbers; accept only supported frequencies | — |
| **Member record lookup** | Request and summarize the record through an approved tool | Use the entered member ID only; read-only; no modification; return an error for invalid IDs | — |
| **Transaction summary** | Explain the summarized figures | Compute totals, balances, averages and repayments with deterministic logic; flag missing data | Officer verifies figures during review |
| **Policy and product information** | Find and explain relevant policies and loan products | Retrieve only from the approved corpus; show sources; state when information is not available | Staff clarify policy that is unclear |
| **Loan product matching** | Explain why a product matches the requested terms | Compare requested terms with documented product conditions by rules; show only matching products | — |
| **Repayment illustration** | Send inputs to the calculator and explain the results | Perform all calculations; label them illustrative; state when policy is insufficient | Review figures before any real use |
| **Requirements check** | Explain requirements and what is outstanding | Check the case against documented requirements by rules; trace each to a source | Staff clarify unclear requirements |
| **Form submission** | Explain what each form needs | Provide structured forms; validate fields; classify items as present, missing, unclear or needs verification | Verify accuracy of submitted information |
| **Document submission and review** | Identify document type; extract key details; flag apparent mismatches with case data | Accept only text-based PDF and images; reject other formats; associate documents with the case; compare extracted details with case data by rules; classify each item | Verify authenticity; resolve flagged mismatches and unclear items |
| **Clarification** | Ask specific questions about missing or conflicting information | Track case state; do not repeat satisfied questions; stop when items are satisfied, missing or flagged | Resolve items marked for human review |
| **Case preparation** | Write and organize the case summary | Use the required template; verify sources; separate facts, calculations and AI text | Officer reviews the case |
| **Human handover** | Nothing after handover; the agent stops | Record handover; end the autonomous workflow | Officer decides whether and how the case proceeds |
| **Tool use** | Choose an approved tool and provide parameters | Tool allow-list, input validation, iteration and stop limits | Approve higher-impact actions |
| **Logging and audit trail** | — | Automatically record agent actions, including failures and refusals; agent cannot edit logs | Officer can review the audit trail |

## Prohibited actions (agent must never do these)

| Action | Status | Who owns it |
|---|---|---|
| Credit scoring or labelling a member creditworthy or not | Not allowed | Human process outside the agent |
| Loan approval, rejection or recommending a lending decision | Not allowed | Credit committee / relationship officer |
| Judging a member's eligibility or suitability for a loan | Not allowed | Human staff |
| Disbursement, account changes, editing member records, real transactions | Not allowed | Core banking system / human-controlled process |
| Claiming a document or submitted information is authentic or verified | Not allowed | Authorized human verification |