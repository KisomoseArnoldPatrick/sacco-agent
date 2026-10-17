# Week 6 — Explicit Workflow and Session State

## Lifecycle

`new → in_progress → waiting_for_member → in_progress → ready_for_officer_review → closed`

A case may also become `blocked` when a safety check, tool, or policy source fails. `closed` means the preparation workflow is closed; it does not mean the loan was approved or rejected. `ready_for_officer_review` means the preparation information is ready for a human to review.

## State fields

- `state_version`: schema version; unsupported versions are rejected.
- `case_id`, `owner_membership_number`: stable case identifier and owner key.
- `created_at`, `updated_at`: ISO-8601 timestamps.
- `status`, `requester_role`, `member_message`: lifecycle, requester type, and minimal request description.
- `workflow.current_stage`: stage such as `intake`, `collecting_policy`, or `preparation_review`.
- `workflow.iteration_count`, `max_iterations`: consumed and maximum iterations; the maximum is 6.
- `workflow.tool_call_counts`, `max_calls_per_tool`: counts for exactly `get_member_record`, `retrieve_policy`, and `calculate_repayment`; the maximum per tool is 2.
- `workflow.stop_reason`, `human_handoff_required`: stop and escalation metadata.
- `preparation`: whether member data was retrieved, policy document names, whether an illustrative repayment was calculated, missing requirements, and summary status.
- `memory_metadata`: purpose and data-minimization declarations.

## Validation invariants

1. The only approved tools are `get_member_record`, `retrieve_policy`, and `calculate_repayment`.
2. Python validates state and authorizes access; the model is not an identity provider.
3. State version, required fields, nested types, ISO timestamps, status values, approved tool names, and execution limits are validated.
4. Boolean values are not accepted as integer counters, even though Python treats `bool` as a subclass of `int`.
5. Loading a case must not reset iteration or tool-call counters. A resumed live workflow continues within the cumulative limits.
6. Persistent memory excludes raw member records, full policy text, raw repayment payloads, and decision fields.
7. Preparation status is not approval, rejection, credit scoring, or disbursement.
8. The membership-number owner check is a prototype authorization check, not production authentication.
