# Memory Use Case: Case History Per Member

**Status:** Definition for the Week 6 memory use case; this is not an implementation or a retention policy.

## 1. What it is

Case history per member is a persistent, read-only record of earlier loan-application preparation runs, linked to the member whose case was prepared. Unlike the current workflow state, it remains available after a run ends and may be retrieved in a later run after authorization. It is preparation history, not an official member record or a lending decision.

The current `new_state()` and trace can produce the following fields. The proposed history should use only these existing fields, and should not imply every field is populated for every run:

- Member/run context: `requester_membership_number`, `requester_role`, `member_message`, `started_at`, and `ended_at`.
- Preparation result: `repayment_schedule`, `missing_requirements`, `case_summary`, `stop_reason`, and `human_handoff_required`.
- Run evidence: `tool_calls_made`, `tool_call_counts`, and `iteration_count`.

These are fields in the current state/trace, not a separate persistent memory schema ([`loop.py`](../../src/agent/loop.py#L81), [`loop.py`](../../src/agent/loop.py#L104), [`loop.py`](../../src/agent/loop.py#L768), [`loop.py`](../../src/agent/loop.py#L1213), [`agent-task-contract.md`](../requirements/agent-task-contract.md#L92)). `repayment_schedule`, when present, carries structured calculator output such as `loan_product`, `principal_ugx`, and `term_months` ([`loop.py`](../../src/agent/loop.py#L320)). Requested terms otherwise appear in `member_message`; there are no separate state fields for requested amount, requested term, payment frequency, or product.

Important schema limits:

- There is no generated case ID. `requester_membership_number` and trace `started_at` exist, but treating their combination as a unique history key is **proposed**.
- `missing_requirements` is not a structured list of clarification questions and answers. The loop has no separate clarification transcript field.
- `human_handoff_required` records that human handover is required; it does not establish that an officer received or reviewed the case. There is no handover-completed timestamp or officer receipt field.
- There is no officer-decision field. The agent state cannot record an officer decision, and this definition does not treat a model-generated value as one.
- The proposed history is a minimal projection of the fields above. It does not copy `member_record`, full `policy_excerpts`, or uploaded files into a second store; those are not needed as memory to identify prior requests, results, and unresolved requirements. Current run traces may already contain member-record snapshots.

## 2. What it is for (the justification)

The justified use case is continuity of application preparation across separate runs:

- Avoid asking a member again for information already provided and satisfactorily resolved. This extends the explicit rule that the system must not repeatedly request information already satisfactorily provided ([`user-stories.md`](../requirements/user-stories.md#L195)) and addresses the charter's repeated-communication pain point ([`charter.md`](../requirements/charter.md#L28)). The current state only supports this during one run; it has no prior-run loader.
- Resume an unfinished preparation by showing the earlier `member_message`, `missing_requirements`, `case_summary`, and stop reason. This supports the charter's single case-preparation workflow and its clarification and case-summary activities ([`charter.md`](../requirements/charter.md#L89), [`charter.md`](../requirements/charter.md#L97)). Resumption across runs is a proposed capability, not an existing user-story acceptance criterion.
- Let a reviewing officer see earlier preparation results and run evidence, including the case summary and agent actions. This supports the officer summary and handover stories ([`user-stories.md`](../requirements/user-stories.md#L206), [`user-stories.md`](../requirements/user-stories.md#L227)) and the audit-trail story requiring actions, clarifications, failures, and refusals to be reviewable ([`user-stories.md`](../requirements/user-stories.md#L246)).

This is memory, rather than session state, only if the selected history survives the end of one run and can be retrieved in a later run. Today, `new_state()` creates fresh state for one request and `run_agent_loop()` returns a trace; the prompt versions do not receive a prior-case input ([`loop.py`](../../src/agent/loop.py#L70), [`loop.py`](../../src/agent/loop.py#L1225), [`v1.2.md`](../../prompts/v1.2.md#L39)).

## 3. What it explicitly does NOT do

These are firm constraints for any implementation:

- It does not approve or reject, recommend a lending decision, score or rate a member, or determine or infer creditworthiness. The charter says: “The agent will not approve or reject loans, determine creditworthiness, disburse funds, modify accounts, or perform real financial transactions.” ([`charter.md`](../requirements/charter.md#L16)); the Boundary Matrix prohibits credit scoring and creditworthiness labels ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L36)).
- It does not use earlier case outcomes, requests, or clarifications to judge eligibility or suitability, or to alter product matching. Product matching remains a deterministic comparison against documented product conditions ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L18)); eligibility and suitability judgments are prohibited ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L38)).
- It does not make an old member record, transaction fact, policy excerpt, or AI summary authoritative or current. Current member information must still come from the read-only member-record lookup and current policy from the approved source; officers review the prepared case ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L15), [`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L27)).
- It does not expose one member's history to another member. A member's history is scoped to their own membership number; the record lookup is read-only and checks that a member's requester membership number matches the requested record ([`tools.py`](../../src/agent/tools.py#L88), [`tools.py`](../../src/agent/tools.py#L117)).
- It does not store or claim to verify raw uploaded documents. Current workflow state has no uploaded-document field, and the project says submitted documents are synthetic and authenticity requires human verification ([`user-stories.md`](../requirements/user-stories.md#L178), [`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L25)).
- It does not overwrite official member records or perform transactions. The existing lookup is read-only; editing records and real transactions are prohibited ([`tools.py`](../../src/agent/tools.py#L92), [`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L39)).
- It contains synthetic project data only. The charter limits member records and transactions to synthetic data and bars real personal data ([`charter.md`](../requirements/charter.md#L111), [`charter.md`](../requirements/charter.md#L138)).
- It does not continue autonomous preparation after handover. The matrix says the agent takes no action after handover and stops ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L28)). A later run must not silently reopen a handed-over case.

## 4. Safeguards

- **Member access:** a member may read only history associated with their own membership number. Apply authorization at history lookup, not just when fetching the current member record.
- **Officer access:** a relationship officer may read only histories for members they are authorized to review. The contract allows an officer to read “any authorized record,” but the current tool does not implement an officer assignment/authorization list. Enforcing that scope for memory is **proposed** ([`agent-task-contract.md`](../requirements/agent-task-contract.md#L17), [`tools.py`](../../src/agent/tools.py#L110)).
- **Authentication limitation:** the prototype explicitly has no real login or authentication; the supplied role and membership number are not proof of identity ([`user-stories.md`](../requirements/user-stories.md#L20)). Memory access must remain synthetic/test-only until identity and officer authorization are provided by a real trusted layer.
- **Officer visibility:** every run that uses prior memory must let the reviewing officer inspect which prior entry or fields were supplied to the agent, alongside the existing per-run actions and results. A memory-use reference/content snapshot in the audit trace is **proposed**; no such field exists today. Audit logs remain agent-uneditable, and the officer can review them ([`ai-boundary-matrix.md`](../requirements/ai-boundary-matrix.md#L30), [`user-stories.md`](../requirements/user-stories.md#L256)).
- **Freshness and provenance:** label reused details as coming from an earlier preparation, preserve their original run timestamp, and ask the member to clarify any conflict with the current request. Do not treat remembered facts as verified or as a substitute for current record retrieval. This behavior is **proposed**.

## 5. Data handling summary

- **Stored:** the minimal history projection of the existing fields listed in Section 1, linked by `requester_membership_number`; it may include request text, a case summary, unresolved requirements, calculator output, stop/handover-required status, timestamps, and tool-call evidence. Do not duplicate the full member record, policy corpus, or raw documents in the memory store.
- **Why:** preserve preparation continuity and provide the officer with earlier case context and an auditable account of what the agent used.
- **Access:** member's own history; relationship officer histories only for members they are authorized to review. Both controls require real identity/authorization support before use with real people; that support does not exist in this prototype.
- **Data class:** synthetic data only, consistent with the charter. `data/` currently contains `member_records.json`; it has member/account facts but no transaction ledger or case-history records ([`member_records.json`](../../data/member_records.json#L1)).
- **Retention — proposed:** retain a closed case history for 90 days after closure; retain an unfinished case until 90 days of inactivity. The repository does not set a memory-retention period.
- **Deletion — proposed:** on expiry or an authorized deletion request, remove the history projection and its search/index copies from the active memory store; purge backup copies within 30 days. Keep the memory store separate from immutable audit evidence. How deletion interacts with persistent audit traces and their own retention is unresolved; the agent must not edit or delete audit-trail entries ([`user-stories.md`](../requirements/user-stories.md#L256)). No memory deletion mechanism currently exists.

## 6. Acceptance checks

1. A later run for an authorized member retrieves only that member's earlier history; a member asking for another membership's history is refused.
2. When a member explicitly resumes an earlier case and an earlier request or summary contains an unambiguous value, the agent reuses it without asking for it again; if the new request conflicts, it asks for clarification instead of choosing silently.
3. A resumed case fetches current member information and current policy as needed; an old snapshot is identified as historical and is not presented as current or verified.
4. Memory does not change deterministic product matching and is never presented as a reason to approve, reject, recommend a lending decision, score, or label creditworthiness.
5. For every run that used memory, the officer-facing audit trail identifies the prior entry/fields used and the run that supplied them; refused memory access is also recorded.
6. A handed-over case is not autonomously resumed, and stored memory contains synthetic data only; expiry/deletion removes the proposed memory copies without agent edits to audit-trail entries.
