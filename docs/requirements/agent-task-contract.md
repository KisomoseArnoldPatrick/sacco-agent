# Agent Task Contract — SACCO Case Preparation Agent

## 1. Goal

Given a member's loan request and, where available, their member record and relevant SACCO policy information, the agent gathers the required information, checks documented requirements, calculates an illustrative repayment schedule, and prepares a policy-grounded case summary for a SACCO Relationship Officer to review.

The agent does **not** approve, reject, score, disburse, or modify any loan or member account. Its purpose is to prepare information for human review.

---

## 2. Approved Tools

The agent may use only the following tools:

| Tool | Purpose | Authorization |
|---|---|---|
| `get_member_record` | Read-only lookup of the member's synthetic member information, such as savings, share capital, active loans and guarantee commitments | Member: own record only. Officer: any authorized record. |
| `retrieve_policy` | Retrieves relevant SACCO policy and procedure information from the approved knowledge base | Read-only |
| `calculate_repayment` | Calculates an illustrative repayment schedule using the requested loan amount, term and applicable product information | Computation only; does not approve or commit a loan |

No other tools may be called.

Requests to perform prohibited actions such as approving a loan, disbursing funds, changing an account or performing a real financial transaction must not be executed.

---

## 3. Agent Workflow

The agent follows a bounded decision loop:

**Sense/Context → Plan/Decide → Act/Tool → Observe → Stop or Re-plan**

### Step 1 — Sense/Context

The agent examines the member's request and available information.

It identifies information such as:

- member identification;
- requested loan amount;
- requested repayment term;
- purpose of the request;
- available member record;
- relevant SACCO policy information.

### Step 2 — Plan/Decide

The agent determines the next approved action required to prepare the case.

For example:

1. Retrieve the member record if required.
2. Retrieve the relevant SACCO policy.
3. Identify documented requirements.
4. Calculate an illustrative repayment schedule when sufficient information is available.
5. Prepare the case summary.

The agent may change the next step based on the result of the previous tool call.

### Step 3 — Act/Tool

The agent calls one of the approved tools using the required inputs and authorization rules.

### Step 4 — Observe

The agent examines the tool result and updates its workflow state.

For example:

- If the member record is found, continue.
- If required information is missing, request clarification.
- If relevant policy is found, use it to identify documented requirements.
- If a calculation is successful, include the result in the case.
- If a tool fails or access is unauthorized, stop safely.

### Step 5 — Stop or Re-plan

After observing the result, the agent either:

- selects the next approved action;
- asks the member for missing information; or
- stops and hands the case to a human.

The agent does not continue indefinitely.

---

## 4. State Tracked Across the Workflow

```json
{
  "member_message": "string",
  "requester_role": "member | officer",
  "requester_membership_number": "string | null",
  "member_record": "object | null",
  "policy_excerpts": "list",
  "repayment_schedule": "object | null",
  "missing_requirements": "list",
  "case_summary": "string | null",
  "tool_calls_made": "list",
  "iteration_count": "integer",
  "stop_reason": "string | null"
}