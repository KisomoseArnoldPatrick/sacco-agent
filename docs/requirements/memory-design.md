# Week 6 — Memory Design and Data Handling Note

## Use case

Persist minimal case-preparation metadata so an unfinished synthetic case can be reopened with its current stage, retrieved policy-document names, completed preparation flags, outstanding requirements, and cumulative workflow/tool counters. This helps resume work without treating stored history as a decision.

## Stored

- Case ID and owner membership key
- Requester role and minimal request description
- Creation/update timestamps and workflow status/stage
- Iteration count, maximum iterations, per-tool call counts, and limits
- Policy document names (not full policy text)
- Preparation flags and missing requirements
- Stop reason and human-handoff flag
- Metadata describing the purpose and exclusions of the stored record

## Deliberately not stored

Raw member records or balances, full policy text, credentials/API keys, full model prompts, complete tool transcripts, raw repayment payloads, credit scores, loan decisions, or disbursement decisions.

## Access control

- A member can read, save, list, and delete only their own case records.
- Officers are read-only for this interface. An officer may read a particular member's history only when trusted application/session code supplies an authorization result that explicitly includes that member.
- The officer authorization list must never come from model output or an unverified claim. Without a trusted authorization result, access is denied.
- The listing operation remains owner-only; this prototype does not provide an officer-wide case search.
- Unauthorized requests should receive a generic denial that does not reveal whether a case exists.

## Retention and deletion

The local prototype retains records until the owner explicitly deletes them. The demonstration may use a temporary directory that is removed at process exit. The deletion method removes the saved case record; any production audit record or backup retention must be separately specified and must not be assumed to disappear with the case record.

A real deployment needs an approved retention schedule, a documented deletion process, clear handling of backups/audit logs, and appropriate authorization for any administrative deletion.

## Security and limitations

The JSON file is not encrypted, and a membership number/owner key is not authentication. Atomic replacement reduces the chance of a partially written JSON file but does not provide database-grade concurrent-write protection. Production requires trusted session identity, encryption, restrictive file/database permissions, audit logging, concurrency handling, backups and retention controls, and appropriate recovery procedures.

Loaded state is validated for schema version, required structure, types, and limits. Stored text must be treated as untrusted data. On resume, cumulative iteration and tool-call counters are restored; loading history must not reset execution limits. Memory is workflow history only: it must never approve/reject a loan or override current policy and authorization checks.
