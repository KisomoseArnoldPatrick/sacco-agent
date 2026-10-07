# Tool Catalogue — Week 4

Both tools below are deterministic Python functions. The model may request
that a tool be called, but the model never performs authorization checks,
validation, or calculations itself — those are enforced entirely in code.
This preserves the AI Boundary Matrix: AI understands/assists, deterministic
software calculates/enforces, humans decide.

---

## Tool 1: `get_member_record`

**Purpose:** Retrieve a SACCO member's current application-relevant record
(savings balance, share capital, active loan status, guarantee
commitments) by membership number, so the agent can reference verified
data instead of assuming it. Satisfies the Week 4 requirement that at
least one tool retrieve current application data.

**Input schema**

| Field               | Type   | Required | Notes                                 |
|----------------------|--------|----------|------------------------------------------|
| `membership_number`   | string | Yes      | Format `HS-YYYY-NNNNNN`                    |

**Output schema (success)**

| Field                     | Type          |
|----------------------------|----------------|
| `membership_number`         | string         |
| `full_name`                  | string         |
| `membership_start_date`       | string (date)  |
| `savings_balance_ugx`          | number         |
| `share_capital_ugx`             | number         |
| `active_loan`                    | object or null |
| `guarantee_commitments`           | array          |

**Output schema (failure)** — `{"error": "<code>", "message": "<detail>"}`

**Authorization**

- `requester_role = "officer"` may retrieve **any** member's record.
- `requester_role = "member"` may retrieve **only their own** record
  (`requester_membership_number` must equal the requested
  `membership_number`).
- Any other role, or a mismatch, is rejected.

**Failure behaviour**

| Condition                          | Error code            |
|--------------------------------------|-------------------------|
| Missing `membership_number`            | `invalid_parameters`     |
| Unknown `requester_role`                | `unauthorized`           |
| Member requesting another member's record | `unauthorized`         |
| Membership number not found              | `not_found`              |
| Records store unreachable                 | `service_unavailable`    |

**Human approval:** Not required — this is a read-only retrieval with no
side effect. Access itself is gated by the authorization check above.

---

## Tool 2: `calculate_repayment`

**Purpose:** Deterministically calculate an illustrative repayment
schedule for a named loan product, principal and term, validated against
the documented policy limits for that product (from Week 3's corpus).
This is the "deterministic calculator" the AI Boundary Matrix and
`prompts/v1.0.md` require the model to defer to rather than computing
figures itself.

**Input schema**

| Field           | Type    | Required | Notes                                                              |
|------------------|---------|----------|------------------------------------------------------------------------|
| `loan_product`     | string   | Yes      | One of: `Development Loan`, `Emergency Loan`, `School Fees Loan`         |
| `principal`         | number   | Yes      | Requested amount in UGX                                                |
| `term_months`         | integer  | Yes      | Requested repayment term in months                                     |

**Output schema (success)**

| Field                     | Type    |
|----------------------------|----------|
| `loan_product`               | string   |
| `principal_ugx`                | number   |
| `annual_rate_percent`            | number   |
| `method`                          | string ("reducing_balance" or "flat") |
| `term_months`                       | integer  |
| `monthly_installment_ugx`             | number   |
| `total_interest_ugx`                    | number   |
| `total_repayable_ugx`                     | number   |
| `policy_basis`                              | string (source document) |
| `illustrative`                                | boolean (always `true`)  |

**Output schema (failure)** — `{"error": "<code>", "message": "<detail>"}`

**Authorization:** Available to both members and officers. It performs no
personal-data lookup and takes no action against a real account, so no
role restriction applies.

**Failure behaviour**

| Condition                                 | Error code             |
|----------------------------------------------|--------------------------|
| Unrecognized `loan_product`                     | `unknown_product`         |
| Missing `principal` or `term_months`               | `invalid_parameters`      |
| Non-numeric `principal` or non-integer `term_months`  | `invalid_parameters`   |
| `principal` or `term_months` ≤ 0                        | `invalid_parameters`    |
| `principal` exceeds the product's documented maximum       | `exceeds_policy_limit`  |
| `term_months` exceeds the product's documented maximum       | `exceeds_policy_limit`|

**Human approval:** Not required — the output is always explicitly labelled
`illustrative: true` and is not a loan approval, disbursement or account
change. Consistent with `prompts/v1.0.md`, the agent must present this
figure as illustrative and never as a decision.

---

## Why no tool here needs a pre-action approval gate

Both tools are read-only or purely computational; neither disburses funds,
modifies an account, nor makes an approval/rejection decision. The
project's higher-impact actions (loan approval, disbursement, default
recovery) remain entirely with the Credit Committee and Board, as
documented in `sacco_governance_and_committees.md`, and are intentionally
**not** implemented as callable tools in this project — they are outside
the AI's permitted scope, not merely gated behind approval.
