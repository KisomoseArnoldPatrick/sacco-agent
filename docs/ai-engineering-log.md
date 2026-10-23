# AI Engineering Log

## AI tools and models used
- Claude (Anthropic; session configured as claude-sonnet-5-5) via the Claude app: reviewing and
  drafting requirements documents, consistency audits, diagram generation, report templates.

---

## Week 1 — Problem Framing and AI-Native Requirements
Project week 1 (31 Aug – 4 Sept 2026).

### Consistency audit: AI Boundary Matrix vs charter vs user stories
- **Member:** Kisomose Arnold Patrick
- **Tool/model:** Claude
- **Used for:** finding inconsistencies between the three Week 1 documents and the brief
- **What AI produced:** a list of gaps, including: matrix missing rows (product matching,
  transaction summary, document review, clarification, case state, handover); an "Eligibility
  checks" row that conflicted with the stories; no story for audit logging; naming and scope
  differences ("Member-Case" vs "Loan Application"); "approve the case" wording; and a scope risk
  from document review
- **What we reviewed or changed:** the charter file re-audited; we accepted the findings and made decisions on each (next entry)
- **Verification:** read all three documents in full and cross-checked against the brief's
  Week 1 requirements

### Weekly report template and AI Engineering Log
- **Member:** Kisomose Arnold Patrick
- **Tool/model:** Claude
- **Used for:** creating the weekly progress report template (from the brief's Section 8) and this
  log's structure (from the brief's Section 6)
- **What AI produced:** weekly-reports/TEMPLATE.md and this file's format
- **What we reviewed or changed:** removed repeating sections and organised tables
- **Verification:** compared the template's sections against the brief's Section 8 list

---

## Week 2 — Foundation-Model Engineering and Prompting
Project week 2 (7–11 Sept 2026).

---

## Week 3 — Context Engineering and RAG
Project week 3 (14–18 Sept 2026).

---

## Week 4 — Tools and Function Calling
Project week 4 (21–25 Sept 2026).

---

## Week 5 — Agent Architecture and Bounded Autonomy
Project week 5 (28 Sept – 2 Oct 2026).

---

## Week 6 — Memory, State and Interoperability
Project week 6 (5–9 Oct 2026).

---

## Week 7 — Evaluation, Observability and Guardrails
Project week 7 (12–16 Oct 2026).

### Evaluation Dataset and Guardrail Architecture Review
- **Member:** Kisomose Arnold Patrick & Hannington Wandera
- **Tool/model:** Google Antigravity (Gemini 3.8 Flash)
- **Used for:** Designing the 36-scenario test taxonomy, defining formal evaluation metrics, formulating prompt injection and prohibited action detection regexes, and diagnosing root causes for preflight safety bypasses.
- **What AI produced:** Draft scenario structures across 6 categories, proposed evaluation runner schema, regex patterns for prohibited actions, and PII masking function designs.
- **What we reviewed or changed:** Refactored regex patterns to prevent false positives on valid inquiries; ensured all 36 evaluation scenarios test real application code rather than separate mock paths; verified deterministic execution without consuming live model quota; verified zero PII leakage into trace snapshots.
- **Verification:** Ran `python tests/test_guardrails.py`, `python tests/test_observability.py`, `python tests/test_evaluation.py`, and `python src/agent/evaluation.py`. Confirmed 36/36 scenarios passed, 0 safety violations, and all regression suites green.

---

## Week 8 — Hardening, Final Release and Demonstration
Project week 8 (19–23 Oct 2026).
### Unified CLI entry point
- **Member:** Kisomose Arnold Patrick
- **Tool/model:** Claude Code (Claude Opus 5.5)
- **Used for:** inspecting the codebase to decide whether an entry point already existed, then
  integrating the existing components into one interactive CLI
- **What AI produced:** `src/main.py` (a thin wrapper around `run_agent_loop` in
  `loop_with_memory.py`; live per-iteration display through the existing `gemini_runner` hook;
  per-run JSON traces in `evidence/traces/cli_runs/` using the existing trace format and
  `write_trace_events`), and `tests/test_main_cli.py` (5 tests: success, prohibited request,
  model failure, unauthorized record, non-overwriting traces)
- **What we reviewed or changed:** [e.g. reviewed that main.py does not duplicate retrieval,
  tool calls or guardrails; ran the CLI ourselves with our own requests]
- **Verification:** `python -m unittest discover -s tests -p "test_*.py"` (54/54); 36/36
  evaluation scenarios, 0 safety violations; live Gemini runs of a Development Loan case and a
  prohibited request; invalid-API-key run stopped with `tool_failure:model_unavailable`

### Guardrail gap found during CLI testing
- **Member:** Kisomose Arnold Patrick
- **Tool/model:** Claude Code (Claude Opus 5.5)
- **Used for:** diagnosing why "Approve this member's loan." was not blocked by the pre-flight
  guard
- **What AI produced:** root cause (the regex did not allow a possessive such as "member's"
  between the determiner and "loan"); a widened approve/reject pattern in
  `src/agent/guardrails.py`; three new cases in `test_06` in `tests/test_guardrails.py`
- **What we reviewed or changed:** [e.g. checked that informational questions such as "Can an
  officer approve a member's loan the same day?" are still allowed]
- **Verification:** guardrail tests pass; 36/36 evaluation scenarios unchanged.
  Known remaining gap: "approve for me a loan" still gets past the regex (the model refused
  it), recorded as a limitation

  
### README
- **Member:** Kabalebe Joshua
- **Tool/model:** Claude Code (Claude Opus 5.5)
- **Used for:** writing the final README and a verified demo runbook for the Section 10
  presentation
- **What AI produced:** `README.md` (setup, run, tests, evidence, safety, limitations,
  troubleshooting)
- **Verification:** every README link checked;