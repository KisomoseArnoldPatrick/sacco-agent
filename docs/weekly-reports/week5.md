# Weekly Progress Report — Week 5

**Group / project:** I Evening — SACCO Loan Application Preparation Agent
**Week ending:** 2 October 2026 (Week 5 of 8: 28 September – 2 October 2026)

Weekly focus: Agent Architecture and Bounded Autonomy.

## 1. Work completed against the weekly objectives

| Deliverable | Status (Done / Partial / Not started) |
|---|---|
| Agent Task Contract (goal, approved tools, workflow state, limits and stop conditions) | Done |
| Implement the bounded Python loop with `max_iterations` and Week 3 RAG tool calls | Done |
| Implement stop conditions and human hand-off / approval checks inside the loop | Done |
| Happy-path end-to-end run and integration fixes | Done |
| Trace 1: clean happy path | Done |
| Failure scenario and Trace 2 capture | Done |
| Architecture diagram showing the full bounded agent workflow | Done |
| Buffer-day fixes; re-run and re-capture where needed | Done |
| Week 5 progress report (this document) | Done |


## 2. Key engineering decisions and why

- **Decision:** Bound requests to six iterations and two calls per approved tool, with one tool call per model round. **Why:** Limits repeated model and tool activity while allowing observation and re-planning.
- **Decision:** Stop on tool errors, blocked or unknown calls, and the iteration limit; require human hand-off for those cases and classify model refusals of prohibited actions for hand-off. **Why:** The agent prepares cases but does not make loan decisions.
- **Decision:** Use deterministic fake-model scenarios for safety checks; track Gemini calls against a daily budget, leave quota-exhausted cases PENDING, and skip passed scenarios only when their source fingerprint is unchanged. **Why:** Controls test cost without treating unrun or stale scenarios as current passes.

## 3. Failures, challenges and current response

- **Issue:** The contract and bounded loop do not document and implement the requested RAG integration and approval workflow.
  **Cause:** The contract describes bounds generally without numeric values; the agent tool reads local policy files rather than calling `src/rag/retrieval.py`, and the approval refusal check classifies model output rather than the incoming request.
  **Response / status:** The code sets six iterations and two calls per tool and has hand-off paths, but no verified correction connecting vector RAG or adding a request-side approval gate appears in current code or history.
- **Issue:** The saved scenario run does not verify the happy path or all safety cases.
  **Cause:** `normal_loan_case`, `missing_repayment_term`, `prohibited_approval_request` and `max_iterations` failed with `service_unavailable`; the unauthorized-record and missing-policy assertions expect `tool_call["result"]`, while the loop records `result_summary`.
  **Response / status:** `test_progress.json` still lists these six failures; only `unknown_tool` is passed. No fix followed by a passing re-run is evidenced. The cause of the `service_unavailable` results is not recorded.
- **Issue:** The required trace set and updated architecture diagram are not evidenced.
  **Cause:** `manual_agent_run.json` ends at `clarification_required`; only `unknown_tool.json` is a failure trace, and no third recovery trace or bounded-workflow diagram exists under `docs/architecture/`.
  **Response / status:** The latest evidence does not show a clean `case_complete` trace, three traces, or a re-capture after fixes. The architecture overview remains the initial diagram; the screenshot is not a diagram. No verified completion fix is present in the current files or history.

## 4. Links

- GitHub: https://github.com/KisomoseArnoldPatrick/sacco-agent
- ClickUp: paste Week 5 Tasks List URL
- AI Engineering Log entries this week: No Week 5 entries recorded under the Week 5 heading in `docs/ai-engineering-log.md`.

## 5. Individual contribution summary

| Member | Role | Task(s) owned this week | Evidence |
|---|---|---|---|
| Kisomose Arnold Patrick | | Run happy-path end-to-end early, fix integration bugs (Done); update Architecture Diagram (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/run_agent_cases.py<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/architecture/architecture-overview.md |
| Hannington Wandera | | Implement the bounded Python loop (Done); implement stop conditions and human hand-off / approval check (Done); buffer-day fixes (Done, shared) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/loop.py<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent_tools.py<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/agent/tools.py |
| Kukiriza Sinai Jose | | Define the agent's goal and write the Agent Task Contract (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/agent-task-contract.md |
| Mugisha Modern | | Capture Trace 1 (Done); capture a failure trace (Done); buffer-day fixes (Done, shared) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/evidence/traces/manual_agent_run.json<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/evidence/traces/unknown_tool.json<br>https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/evidence/test_runs/test_progress.json |
| Kabalebe Joshua | | Compile Week 5 progress report (Done) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/weekly-reports/week5.md |

## 6. Plan for next week

Next week's focus (from the brief): Memory, State and Interoperability (Week 6, 5-9 October 2026).

Planned tasks:
- Model the workflow/session state explicitly and document it as a State Model (what the agent tracks, its fields, and how they change per loop iteration).
- Implement one justified persistent-memory use case (for example an approved member preference, case history or a prior task result), and demonstrate that it improves a legitimate task without silently controlling critical decisions such as approval.
- Write the Memory Design and Data Handling Note: what is stored, why, who can access it, retention period and how it is deleted.
- Implement one external integration OR document one project capability as an MCP-style interface (capability, inputs, outputs, permissions and security boundary).
- Produce a working memory/state demonstration (trace or run evidence saved under `evidence/`).
- Compile the Week 6 progress report.

Deliverables due: State Model; Memory Design and Data Handling Note; working memory/state demonstration; integration or MCP-style interface specification; Week 6 progress report.

Task owners and deadlines will be recorded on ClickUp.
