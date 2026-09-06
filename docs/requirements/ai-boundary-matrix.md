# AI Boundary Matrix — SACCO Member-Case Preparation Agent

Defines what the AI/agent can do, what the system must control using deterministic code, and what requires human involvement.

> **AI = Understands and assists**  
> **System = Calculates and enforces rules**  
> **Human = Reviews and makes important decisions**

| Function | AI/Agent Can Do | System Must Control | Human Must Decide |
|---|---|---|---|
| **Policy & procedures** | Find and explain relevant policies | Retrieve from approved documents and show sources | — |
| **Repayment calculations** | Send inputs to the calculator and explain results | Perform all calculations | Review figures before they are used in a real decision |
| **Member/loan lookup** | Request and summarize a record | Read-only access and authorization | — |
| **Eligibility checks** | Explain possible eligibility issues | Apply the defined eligibility rules | Review before communicating the issue |
| **Case preparation** | Write and organize the case summary | Use required template and verify sources | Approve the case before action is taken |
| **Credit scoring** |  Not allowed |  Out of scope | Human process outside the agent |
| **Loan approval** |  Not allowed | Out of scope | Credit committee |
| **Disbursement/account changes** |  Not allowed | Real transactions stay in the core banking system | Human-controlled process |
| **Tool use** | Choose an approved tool and provide parameters | Allow-list, input validation, and stop limits | Approve higher-impact actions |
| **Logging & audit trail** | — | Automatically record agent actions | Can review the audit trail |