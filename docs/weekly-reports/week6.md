# Weekly Progress Report — Week 6

**Group / project:** I Evening — SACCO Loan Application Preparation Agent **Week ending:** 9 October 2026 (Week 6 of 8: 5 – 9 October 2026)

Weekly focus: Memory, State and Interoperability.

## 1. Work completed against the weekly objectives

| Deliverable | Status (Done / Partial / Not started) |
| --- | --- |
| Explicit state model for the agent loop's session (member ID, retrieved policy documents, counters, stage, stop reason) | Done |
| Justified memory use case: case history per member (what it is, what it is for, what it explicitly does not do) | Done |
| Persistent memory store (local JSON object keyed by case ID, with owner membership number checked for access) | Done |
| Memory Design and Data Handling Note (what is stored, why, who can access it, retention, deletion) | Partial |
| Memory integrated into the agent loop (surfaces prior case history to the officer; never auto-decides anything) | Done |
| Demonstration that memory restores prior case context without controlling critical decisions (no no-memory comparison evidenced) | Done |
| `case_memory` capability documented as a local MCP-style interface contract (not an MCP server or separate compiler) | Done |
| Week 6 progress report (this document) | Done |

## 2. Key engineering decisions and why

- **Decision:** Store workflow state as a versioned Python dictionary persisted to a local JSON file through a `CaseMemoryStore` with save, load, list and delete operations (`save_case_state`, `load_case_state`, `list_my_case_states`, `delete_case_state`). **Why:** An unfinished loan case-preparation workflow can be resumed and reviewed, and validation of the schema version, required fields, nested types, allowed statuses and tools, timestamps and limits rejects malformed or unsupported state.
- **Decision:** Keep only the metadata needed to resume a case (ownership, timestamps, status and stage, iteration and per-tool counters, preparation flags, policy document names, outstanding requirements, stop reason, handoff metadata). Exclude raw member records and balances, full policy text, full prompts and transcripts, raw repayment payloads and loan decisions. **Why:** Data minimisation limits the harm if the store is exposed and keeps memory from becoming a hidden source of decisions.
- **Decision:** Members may access only their own cases; an officer may read a cross-member case only when trusted application or session code supplies an explicit authorization result, and officer access is read-only. History retrieval returns a read-only packet and does not invoke the model or approved loan tools. **Why:** Access follows least privilege, and reviewing history cannot trigger actions.
- **Decision:** Restore the existing iteration and tool-call counters when a case is resumed, and treat `ready_for_officer_review` as a request for human review, not a loan decision. Prohibited loan-approval requests are refused before any model or tool execution. **Why:** A new session cannot reset execution limits, and the agent prepares cases but does not make loan decisions.

## 3. Failures, challenges and current response

- **Issue:** The loop tests cover guarded memory paths but do not exercise a live Gemini/tool round trip. **Cause:** The tests inject a runner that must not be called on the read-only, denied, missing-history, prohibited-action and exhausted-budget paths; import-only stubs are conditional fallbacks when `baseline_chat.py` or `agent_tools.py` are unavailable. **Response / status:** The two Week 6 test files contain 15 tests (10 state/memory and 5 loop tests), and the saved JSON results report all 15 passed. These verify the tested Week 6 logic but do not replace a live model/tool integration test. A live end-to-end integration check remains planned for Week 7.
- **Issue:** The memory store is a teaching prototype and is not production-safe. **Cause:** It uses local, unencrypted JSON, the owner key is not authentication, and concurrent writes are not protected like a database transaction. **Response / status:** This limitation follows from the implementation; the referenced Memory Design and Data Handling Note is still empty. A production version needs trusted identity and session handling, encryption and storage permissions, audit logs, concurrency control, a formal retention schedule and defined backup and deletion behaviour.
- **Issue:** Week 5's scenario failures and missing traces were resolved in the 9 October rerun, but an updated bounded-workflow architecture diagram is not evidenced. **Cause:** The scenarios were rerun and traces recorded; no updated bounded-workflow diagram appears in `docs/architecture/`. **Response / status:** `test_progress.json` records 7 passed scenarios and an empty `failed` object, with scenario traces saved under `evidence/traces/`; the architecture-diagram carry-over remains unresolved.

## 4. Evidence

On 16 October 2026 the following commands were re-run and completed successfully in the standalone Week 6 package:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
PYTHONPATH=src python3 -m py_compile src/agent/state.py src/agent/memory.py src/agent/loop_with_memory.py src/agent/week6_memory_demo.py tests/test_week6_state_memory.py tests/test_loop_with_memory.py
PYTHONPATH=src python3 src/agent/week6_memory_demo.py
```

The test suite reported **15 tests passed** (10 state/memory tests and 5 loop tests); `py_compile` reported no errors; the memory demo ran to completion.

| # | Behaviour verified | Evidence |
| --- | --- | --- |
| 1 | Case saved and loaded across separate store instances and sessions | `tests/test_week6_state_memory.py::Week6Tests.test_01_write_and_read_in_new_session`; `evidence/memory/test_results.json` |
| 2 | Unauthorized member read and delete attempts denied | `tests/test_week6_state_memory.py::Week6Tests.test_02_unauthorized_access_denied`; `evidence/memory/test_results.json` |
| 3 | Authorized officer read-only retrieval without model or tool calls | `tests/test_loop_with_memory.py::LoopMemoryIntegrationTests.test_authorized_officer_gets_visible_read_only_history`; `evidence/memory/loop_integration_test_results.json` |
| 4 | Deletion followed by a load confirming the record is gone | `tests/test_week6_state_memory.py::Week6Tests.test_04_owner_can_delete_case_history`; `evidence/memory/test_results.json` |
| 5 | Validation failures for unsupported versions, malformed state and exceeded counters | `tests/test_week6_state_memory.py::Week6Tests.test_05_workflow_limits_are_enforced` and `test_10_boolean_counter_and_unknown_tool_rejected`; `evidence/memory/test_results.json` covers counters, boolean counters and an unapproved tool. Unsupported-version and malformed-state failures are implemented in `src/agent/state.py` but are not separately demonstrated in these test results. |
| 6 | Resumed workflow preserves counters and refuses to exceed configured limits | `tests/test_loop_with_memory.py::LoopMemoryIntegrationTests.test_resumed_case_preserves_cumulative_counters`; `evidence/memory/loop_integration_test_results.json` |
| 7 | Prohibited loan-approval request refused before model or tool execution | `tests/test_loop_with_memory.py::LoopMemoryIntegrationTests.test_approval_request_is_refused_before_model_or_tools`; `evidence/memory/loop_integration_test_results.json`; `evidence/traces/prohibited_approval_request.json` |

### Demonstration: memory improving a real task

- **Without memory:** [TODO: provide a comparable no-memory run showing what information had to be recollected.]
- **With memory:** A second store instance restores the saved case and surfaces `development_loan.md` and the outstanding “Confirm repayment term” requirement. This demonstrates continuity, but does not measure time or task-outcome improvement against a no-memory run.
- **Decision control:** The authorized-officer history-read test asserts the injected model/tool runner is not called. A separate test refuses “Approve this loan” before model or tool execution and checks the `prohibited_action_requested` stop reason.

### Case File Compiler as an MCP-style interface

| Aspect | Description |
| --- | --- |
| Capability | `case_memory`: validated case-state persistence and owner/authorized-officer history retrieval; no separate Case File Compiler implementation is evidenced. |
| Inputs | State object; case ID string; trusted actor with `membership_number` (string), `role` (`member` or `officer`), and optional trusted `authorized_member_numbers` collection. |
| Outputs | Save: no return value. Load: validated state object or `None`. List: case ID, status and created/updated timestamps. Delete: boolean. |
| Permissions | Members may save, load, list and delete their own cases. Officers may read a cross-member case only when trusted authorization names its owner; officers cannot write or list all cases. |
| Security boundary | Does not execute tools, approve/reject/score/disburse loans, alter accounts, or calculate financial values; history reads do not call Gemini or loan tools. Actor context must not come from model output or unverified input. |

## 5. Links

- GitHub: https://github.com/KisomoseArnoldPatrick/sacco-agent
- ClickUp: https://app.clickup.com/1200440000000513/v/l/li/1200440000098452
- AI Engineering Log entries this week: No Week 6 entries recorded; the Week 6 heading is present but has no entries beneath it.

## 6. Individual contribution summary

| Member | Role | Task(s) owned this week | Evidence |
| --- | --- | --- | --- |
| Hannington Wandera |  | Design explicit state model (Done); implement persistent memory store (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/state.py\<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/memory.py |
| Mugisha Modern |  | Define the justified memory use case (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/architecture/memory-use-case.md |
| Kukiriza Sinai Jose |  | Write Memory Design and Data Handling Note (Partial); demonstrate memory restores prior case context (Done; no no-memory comparison evidenced) | [TODO: populate `docs/requirements/memory-design.md` with the Memory Design and Data Handling Note.]<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/week6_memory_demo.py |
| Kisomose Arnold Patrick |  | Integrate memory into the agent loop (Done); document the `case_memory` API as a local MCP-style interface contract (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/loop_with_memory.py<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/architecture/week6-mcp-style-interface.md |
| Kabalebe Joshua |  | Compile Week 6 progress report (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/weekly-reports/week6.md |

## 7. Plan for next week

Next week's focus: Evaluation, Guardrails and Failure Analysis (Week 7, 12-16 October 2026).

Planned tasks:
- Define measurable criteria and pass thresholds for task completion, groundedness, tool selection and instruction-following (Mugisha Modern, due 13 Oct).
- Assemble 30+ test scenarios across six categories, including normal, edge, incorrect-information and adversarial cases (Hannington Wandera, due 14 Oct).
- Add structured tracing that records the model used, prompt version, retrieved documents and scores, tool calls and per-step results (Kisomose Arnold Patrick, due 14 Oct).
- Implement the missing guardrails: input validation, output validation and prompt-injection checks, and document them (Kukiriza Sinai Jose, due 14 Oct).
- Write deterministic guardrail tests that use mocks and need no API quota (Hannington Wandera, due 15 Oct).
- Build the evaluation runner that scores each scenario against the criteria and works in daily batches (Kukiriza Sinai Jose, due 15 Oct).
- Run the deterministic scenarios first, then the live scenarios in daily batches (Hannington Wandera, due 15 Oct).
- Write the Failure Catalogue with at least 5 genuine failures, each with cause, fix and re-test result (Kukiriza Sinai Jose and Hannington Wandera, due 15 Oct).
- Compile the Week 7 progress report (Kabalebe Joshua, due 16 Oct).

Deliverables due: measurable evaluation criteria and thresholds; scenario set of 30+ cases; structured tracing; input, output and prompt-injection guardrails; deterministic guardrail tests; evaluation runner with scored results; Failure Catalogue (5+ failures); Week 7 progress report.

Task owners and deadlines are recorded on ClickUp.