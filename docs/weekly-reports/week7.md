# Weekly Progress Report — Week 7
 
**Group / Project:** Group I Evening — SACCO Loan Application Preparation Agent  
**Reporting Period:** Week 7 (12 October – 16 October 2026)  
**Weekly Focus:** Evaluation, Observability and Guardrails  

---

## 1. Work Completed Against Week 7 Objectives

| Deliverable / Activity | Status | Primary Evidence |
|---|---|---|
| **Final Evaluation Dataset (36 Scenarios)** across all 6 required categories | **Done** | `data/evaluation/scenarios.json` |
| **Deterministic Evaluation Runner & Metrics Aggregation** | **Done** | `src/agent/evaluation.py` |
| **Measurable Evaluation Criteria Document** | **Done** | `docs/week7/evaluation-criteria.md` |
| **Structured Observability & PII Masking Module** | **Done** | `src/agent/observability.py` |
| **Comprehensive Guardrails Engine** (Input, Output, Tools, Injections) | **Done** | `src/agent/guardrails.py` |
| **Unit & Integration Test Suites** (Guardrails, Observability, Evaluation) | **Done** | `tests/test_*.py` |
| **Failure Catalogue (7 genuine defects discovered, fixed & retested)** | **Done** | `docs/week7/failure-catalogue.md` |
| **Week 6 Demonstration Lifecycle & Continuity Fix** | **Done** | `src/agent/week6_memory_demo.py` |
| **Week 7 Progress Report** (this document) | **Done** | `docs/week7/progress-report.md` |

---

## 2. Evaluation Dataset & Category Coverage

A comprehensive 36-scenario machine-readable dataset was constructed in `data/evaluation/scenarios.json`, providing exactly 6 distinct executable scenarios per category:

1. **Normal Requests (6):** Complete case preparation, active loan inquiry, policy lookup, schedule calculation, multi-tool pipeline, authorized officer read-only history.
2. **Edge Cases & Missing Information (6):** Missing term, missing amount, missing member ID, exact policy boundary (UGX 10M), empty input message, iteration ceiling.
3. **Incorrect / Inconsistent Information (6):** Non-numeric principal, term exceeding policy limit, principal exceeding product max, unknown loan product, negative amount, boolean parameter.
4. **Adversarial Prompts & Injection (6):** Direct instruction override, embedded context injection, prompt injection in policy documents, DAN/jailbreak persona, concealing missing requirements, bypassing human review.
5. **Tool Failures & Recovery (6):** Member not found, policy file missing, calculator exception, repeated tool error, tool call limit exceeded, storage failure.
6. **Unauthorized & Prohibited Actions (6):** Unauthorized member record access, direct approval request, disbursement request, account balance modification, unapproved tool call, unauthorized officer history access.

---

## 3. Measured Evaluation Results vs Acceptance Thresholds

Evaluated via `python src/agent/evaluation.py` with reproducible outputs saved in `evidence/week7/`:

| Metric | Target / Threshold | Measured Week 7 Value | Status |
|---|---|---|---|
| **Overall Scenario Pass Rate** | $\ge 90.0\%$ | **100.0%** (36 / 36 scenarios passed) | **PASS** |
| **Safety Violations Count** | Exactly **0** | **0** violations detected | **PASS** |
| **Task Completion Rate** | $\ge 90.0\%$ | **100.0%** (12 / 12 normal & edge scenarios) | **PASS** |
| **Policy Groundedness Rate** | $\ge 95.0\%$ | **100.0%** (36 / 36 scenarios) | **PASS** |
| **Tool Selection Accuracy** | $100.0\%$ | **100.0%** (36 / 36 scenarios) | **PASS** |
| **Instruction Following Rate**| $\ge 90.0\%$ | **100.0%** (36 / 36 scenarios) | **PASS** |
| **Mean Latency (Deterministic)**| $\le 100\text{ ms}$ | **18.17 ms** | **PASS** |
| **p95 Latency (Deterministic)** | $\le 250\text{ ms}$ | **55.02 ms** | **PASS** |

---

## 4. Observability and Guardrail Implementations

- **Observability (`src/agent/observability.py`):** Structured event tracing capturing unique run UUIDs, scenario IDs, high-precision timing (`perf_counter`), ISO timestamps, tool execution durations, validation failures, and authorization denials. Streamed to `evidence/traces/week7_traces.jsonl`.
- **Data Protection & PII Redaction:** Automatic name masking (e.g., `Carol Atim` -> `C***l A**m`) and removal of sensitive financial fields in persistent trace snapshots (`_make_trace_state_snapshot`).
- **Guardrails (`src/agent/guardrails.py`):**
  1. *Input Validation:* Enforces non-empty strings, character length limits, role allow-list (`member`, `officer`), and membership ID format.
  2. *Prohibited Actions:* Preflight regex blocking direct loan approval, rejection, scoring, disbursement, balance tampering, and review bypass.
  3. *Tool Allow-list:* Strict Python-level enforcement of approved tools (`get_member_record`, `retrieve_policy`, `calculate_repayment`).
  4. *Output Validation:* Intercepts model responses asserting autonomous approvals or disbursements.
  5. *Prompt Injection Defense:* Scans user inputs and retrieved policy documents for adversarial override patterns.

---

## 5. Summary of Discovered Failures and Remediation

Seven genuine defects were identified, remediated, and verified with automated regression tests (see `docs/week7/failure-catalogue.md` for full details):

1. **FAIL-01 (Crash on empty message):** Empty string crashed `new_workflow_state` with unhandled `ValueError`. *Fix:* Added preflight input validation in `run_agent_loop`.
2. **FAIL-02 (PII leakage in traces):** `Carol Atim` appeared 8 times unredacted in trace snapshots. *Fix:* Integrated `sanitize_member_record` into snapshot logic.
3. **FAIL-03 (Preflight safety bypass):** Prohibited action tuple missed "disburse funds", "modify savings", and "bypass review". *Fix:* Replaced with multi-pattern regex engine.
4. **FAIL-04 (Autonomous approval output accepted):** Output claiming loan approval passed as `case_complete`. *Fix:* Added `validate_agent_output` to check generated text.
5. **FAIL-05 (Boolean parameter confusion):** `calculate_repayment` silently treated `True` as `1.0`. *Fix:* Added explicit `isinstance(val, bool)` rejection.
6. **FAIL-06 (Demo fixture deletion):** `week6_memory_demo.py` deleted `demo-case-001`. *Fix:* Segregated deletion test to temporary fixture `demo-case-to-delete`.
7. **FAIL-07 (Misleading tool metadata):** Unknown tools returned `executed: True`. *Fix:* Corrected return metadata to `executed: False`.

---

## 6. Important Limitations and Unresolved Issues

1. **Adversarial Linguistic Obfuscation:** While known injection patterns and jailbreak signatures are blocked deterministically, novel multi-language or encoded obfuscations remain a frontier risk requiring human officer verification.
2. **Advisory Nature of AI Outputs:** The agent cannot make credit scoring, approval, or disbursement decisions. AI output is strictly preparatory and advisory.
3. **Prototype Authorization Model:** Membership number checking operates on synthetic fixtures and trusted caller context; production deployment requires enterprise SSO and IAM tokens.

---

## 7. Individual Contribution Summary

| Member | Role | Task(s) Owned this Week | Evidence |
|---|---|---|---|
| **Kisomose Arnold Patrick** | Requirements / Evaluation Lead | Built evaluation runner (`evaluation.py`), aggregated metrics, scenario execution | `src/agent/evaluation.py`<br>`evidence/week7/evaluation_results.json` |
| **Hannington Wandera** | AI Engineering Lead | Implemented guardrails (`guardrails.py`), input/output validation, bounded loop integration | `src/agent/guardrails.py`<br>`src/agent/loop_with_memory.py` |
| **Kukiriza Sinai Jose** | Integration Lead | Observability engine (`observability.py`), structured tracing, PII redaction logic | `src/agent/observability.py`<br>`evidence/traces/week7_traces.jsonl` |
| **Mugisha Modern** | Quality / Security Lead | Created 36 evaluation scenarios, wrote regression test suites, failure remediation | `data/evaluation/scenarios.json`<br>`tests/test_*.py` |
| **Kabalebe Joshua** | Documentation Lead | Evaluation criteria specification, failure catalogue compilation, Week 7 report | `docs/week7/evaluation-criteria.md`<br>`docs/week7/failure-catalogue.md` |

---

## 8. Plan for Week 8 (Hardening, Final Release & Demonstration)

- Final end-to-end integration and tagged repository release (`v1.0.0`).
- Compile the comprehensive 8–12 page Final Engineering Report with evidence appendices.
- Prepare 12–15 minute live presentation deck and demonstration script showing happy path, tool failure recovery, PII redaction, and guardrail enforcement.
- Ensure repository README provides one-command reproducible setup and testing instructions.

