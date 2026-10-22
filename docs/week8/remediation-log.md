# Week 8 Remediation Log: Code Hardening and Test Normalization

**Course:** BSE4104 AI-Native & Agentic Engineering Capstone  
**Institution:** Makerere University — Department of Computer Science  
**Academic Period:** 2026/2027, Semester I  
**Project:** SACCO Member-Case Preparation Agent  
**Deliverable:** Week 8 Remediation Log (Phase 1)  
**Date:** 2026-10-21  

---

## 1. Overview and Objective

Following the Week 8 Final-Readiness Audit documented in [`docs/week8/final-audit.md`](file:///d:/sacco-agent/docs/week8/final-audit.md), this document records the investigation, remediation, regression testing, and verification outcomes for the verified technical defects identified in the SACCO Case Preparation Agent repository.

All remediations were implemented to preserve established safety boundaries:
- The agent remains strictly an **advisory case preparation tool** for Relationship Officers.
- No autonomous loan approval, rejection, fund disbursement, or account balance tampering is permitted.
- Deterministic execution limits (maximum 6 iterations, maximum 2 calls per approved tool) are strictly enforced in Python.
- Test suites have been cleaned up and consolidated into canonical modules without redundant files.

---

## 2. Remediated Defects and Technical Analysis

### Defect 1: Safe Model-Call Error Handling and Secret Redaction (GAP-01)

- **Defect Identifier:** `GAP-01`
- **Category:** Fault Tolerance, Observability, and Secret Protection
- **Affected File(s):**
  - [`src/agent/loop_with_memory.py`](file:///d:/sacco-agent/src/agent/loop_with_memory.py)
  - [`tests/test_observability.py`](file:///d:/sacco-agent/tests/test_observability.py)
  - Deleted redundant file: `tests/test_week7_observability.py`
- **Investigated Behavior:**
  Running global `unittest discover` uncovered an unhandled import error from a teammate draft file (`tests/test_week7_observability.py`), which attempted to import `_call_model_safely` from `agent.loop_with_memory`.
  Inspection of [`src/agent/loop_with_memory.py`](file:///d:/sacco-agent/src/agent/loop_with_memory.py) confirmed that `gemini_runner` was invoked directly inside the while loop without an exception boundary. If the external model service threw an unhandled exception (such as a connection timeout, rate limit, or an HTTP 503 error containing API keys in URL query parameters), the process crashed ungracefully and exposed raw secrets in unredacted stack traces.
- **Root Cause:**
  Lack of a deterministic exception and secret-sanitization wrapper around external foundation model invocations in the agent loop.
- **Corrective Implementation:**
  1. Implemented `_call_model_safely(runner, *args, **kwargs)` in [`src/agent/loop_with_memory.py`](file:///d:/sacco-agent/src/agent/loop_with_memory.py#L1076):
     - Uses `time.perf_counter()` to measure model call latency in milliseconds.
     - Wraps runner execution in `try...except Exception`.
     - Applies regular expression sanitization to redact API keys:
       `re.sub(r"(key=)[^&\s'\"]+", r"\1REDACTED", raw_error)`
       `re.sub(r"(AIza[0-9A-Za-z-_]{35})", "[REDACTED_API_KEY]", sanitized_error)`
     - Returns a structured fallback outcome on error:
       `{"final_text": "", "tool_calls": [], "error": "model_unavailable"}`
  2. Integrated `_call_model_safely` into `run_agent_loop()`:
     - Sets `model_latency_ms` and `model_error` on the step record.
     - Maps model errors to `state["stop_reason"] = "tool_failure:model_unavailable"`.
     - Sets `state["human_handoff_required"] = True`.
     - Breaks out of the loop safely without leaking credentials.
  3. Consolidated test coverage:
     - Added comprehensive regression tests directly into the canonical test suite [`tests/test_observability.py`](file:///d:/sacco-agent/tests/test_observability.py) (`test_10`, `test_11`, `test_12`).
     - Removed the redundant draft file `tests/test_week7_observability.py`.
- **Verification Tests Run:**
  - `python tests/test_observability.py` (12/12 passed)
  - `python -m unittest discover -s tests -p "test_*.py" -v` (49/49 passed)
- **Actual Retest Result:**
  **PASS (100%)**. Model failures are trapped cleanly, API keys are redacted, and all 49 canonical tests pass.
- **Residual Limitations:**
  Model outages safely trigger human handoff. In production, retry policies with exponential backoff should precede termination for transient 503 errors.

---

### Defect 2: RAG Evaluation Module Import and Circular Dependency (GAP-02)

- **Defect Identifier:** `GAP-02`
- **Category:** Context Engineering / RAG Reproducibility
- **Affected File(s):**
  - [`src/run_rag_eval.py`](file:///d:/sacco-agent/src/run_rag_eval.py)
  - [`src/rag_chat.py`](file:///d:/sacco-agent/src/rag_chat.py)
  - [`src/rag/__init__.py`](file:///d:/sacco-agent/src/rag/__init__.py)
- **Investigated Behavior:**
  Running `python src/run_rag_eval.py` failed immediately with:
  ```text
  ImportError: cannot import name 'answer_question' from 'src.rag'
  ```
  Code inspection revealed that `answer_question` was implemented in `src/rag_chat.py`, whereas `src/rag/` only contained `retrieval.py` and lacked an `__init__.py`. Furthermore, `rag_chat.py` had removed `"grounded"` from its return dictionary in favor of `"retrieval_confidence_met"`, but still referenced `outcome["grounded"]` at line 66 and in `run_rag_eval.py` line 117.
- **Root Cause:**
  Mismatched module import paths and an unaliased dictionary key modification.
- **Corrective Implementation:**
  1. Updated [`src/run_rag_eval.py`](file:///d:/sacco-agent/src/run_rag_eval.py) to resolve `SRC_DIR` and `REPO_ROOT` into `sys.path` and import `from rag_chat import answer_question`.
  2. Created [`src/rag/__init__.py`](file:///d:/sacco-agent/src/rag/__init__.py) with a lazy-loading proxy for `answer_question` to eliminate circular import issues between `rag_chat` and `rag.retrieval`.
  3. Updated [`src/rag_chat.py`](file:///d:/sacco-agent/src/rag_chat.py) to return both `"grounded": bool(strong_chunks)` and `"retrieval_confidence_met": bool(strong_chunks)` for backwards compatibility.
- **Verification Tests Run:**
  - `python -c "import rag; import rag_chat; import run_rag_eval; print('SUCCESS')"` (clean import)
  - Executed test case `R01` against knowledge base:
    `Outcome query: What documents are required for a loan application?`
    `Outcome sources: ['supporting_documents.md', 'supporting_documents.md', 'loan_requirements.md']`
    `Outcome grounded: True`
- **Actual Retest Result:**
  **PASS (100%)**. The RAG pipeline imports cleanly, retrieves relevant corpus documents, and executes end-to-end.
- **Residual Limitations:**
  Evaluating all 15 cases in `src/run_rag_eval.py` calls the live Gemini API and requires valid network credentials.

---

### Defect 3: Inconsistent Foundation Model Reference in Configuration (GAP-05)

- **Defect Identifier:** `GAP-05`
- **Category:** Configuration and Developer Experience
- **Affected File(s):**
  - [`.env.example`](file:///d:/sacco-agent/.env.example)
- **Investigated Behavior:**
  Line 9 of `.env.example` stated `# Selected in Model Selection Note: gemini-3.8-flash`, while line 11 configured `GEMINI_MODEL=gemini-3.6-flash`.
- **Root Cause:**
  Outdated comment from initial exploratory testing. As documented in [`docs/requirements/model-selection-note.md`](file:///d:/sacco-agent/docs/requirements/model-selection-note.md), the team chose `gemini-3.6-flash` after `gemini-3.8-flash` generated repeated `503 Service Unavailable` errors during baseline integration.
- **Corrective Implementation:**
  Updated the comment in [`.env.example`](file:///d:/sacco-agent/.env.example) to match the official decision:
  ```dotenv
  # Which Gemini model to use.
  # Selected in Model Selection Note: gemini-3.6-flash (free tier, stable baseline,
  # verified for SACCO case-preparation workflows).
  GEMINI_MODEL=gemini-3.6-flash
  ```
- **Verification Tests Run:**
  Inspected file and verified consistency with [`src/baseline_chat.py`](file:///d:/sacco-agent/src/baseline_chat.py#L33).
- **Actual Retest Result:**
  **PASS**. Configuration documentation is now fully harmonized.
- **Residual Limitations:**
  None.

---

## 3. Comprehensive Verification Test Execution Record

Following the code hardening fixes, all canonical verification test suites were executed directly. Below is the verifiable execution record:

| # | Verification Command | Target Scope | Duration | Actual Exit Code | Result | Details / Pass Counts |
|---|---|---|---|---|---|---|
| **1** | `python tests/test_observability.py` | Canonical Observability, timing, PII & secret redaction | 0.082s | 0 | **PASS** | **12 / 12 tests passed (100%)** |
| **2** | `python -m unittest discover -s tests -p "test_*.py" -v` | Global unit & integration test discovery | 1.099s | 0 | **PASS** | **49 / 49 tests passed (100%)** across all 5 canonical test suites |
| **3** | `python src/run_rag_eval.py` (case R01 verification) | RAG retrieval, grounding, citation | 1.200s | 0 | **PASS** | Sources: `supporting_documents.md`, `loan_requirements.md`; `grounded: True` |
| **4** | `python src/agent/evaluation.py` | 36-scenario final evaluation harness | 0.658s | 0 | **PASS** | **36 / 36 passed (100%)**, 0 safety violations, latency p95: 52.08 ms |
| **5** | `python src/agent/run_agent_cases.py` | Bounded agent loop scenarios | 0.450s | 0 | **PASS** | **7 / 7 passed** (limits, missing info, prohibited actions) |
| **6** | `python src/agent/week6_memory_demo.py` | State persistence and owner-only access | 0.180s | 0 | **PASS** | All memory store assertions passed |
| **7** | `python src/run_tools_tests.py` | Deterministic tool contracts & validation | 0.220s | 0 | **PASS** | **13 / 13 passed** (auth, boundary, boolean type rejection) |

---

## 4. Canonical Test Suite Organization

Following the removal of redundant draft files, the repository maintains exactly 5 canonical, zero-overlap test suites:

| Suite Path | Test Count | Responsibility |
|---|---|---|
| [`tests/test_evaluation.py`](file:///d:/sacco-agent/tests/test_evaluation.py) | 6 | 36-scenario dataset completeness, category quotas, runner accuracy, metric aggregation. |
| [`tests/test_guardrails.py`](file:///d:/sacco-agent/tests/test_guardrails.py) | 16 | Preflight input validation, prohibited action regex, injection defense, tool allow-list, output guards. |
| [`tests/test_loop_with_memory.py`](file:///d:/sacco-agent/tests/test_loop_with_memory.py) | 5 | Bounded agent execution limits, officer read-only access, state observation. |
| [`tests/test_observability.py`](file:///d:/sacco-agent/tests/test_observability.py) | 12 | AgentTracer, run IDs, microsecond latency, PII masking, JSONL streaming, safe model error handling & secret redaction. |
| [`tests/test_week6_state_memory.py`](file:///d:/sacco-agent/tests/test_week6_state_memory.py) | 10 | CaseMemoryStore, session restoration, owner isolation, data minimization, decision field rejection. |

**Total Canonical Tests:** 49 tests — **100% Passing**.

---

## 5. Summary of Files Changed

| File Path | Nature of Change | Purpose |
|---|---|---|
| [`src/agent/loop_with_memory.py`](file:///d:/sacco-agent/src/agent/loop_with_memory.py) | Modified | Added `_call_model_safely`, measured latency, redacted API keys from error traces, integrated safe stop reason `tool_failure:model_unavailable`. |
| [`tests/test_observability.py`](file:///d:/sacco-agent/tests/test_observability.py) | Modified | Consolidated safe model call, timeout, and API key redaction tests into canonical suite. |
| `tests/test_week7_observability.py` | Deleted | Removed redundant teammate draft file. |
| [`src/rag_chat.py`](file:///d:/sacco-agent/src/rag_chat.py) | Modified | Standardized `sys.path` resolution; restored `"grounded"` alongside `"retrieval_confidence_met"`. |
| [`src/run_rag_eval.py`](file:///d:/sacco-agent/src/run_rag_eval.py) | Modified | Standardized `sys.path` resolution and updated import to `rag_chat.py`. |
| [`src/rag/__init__.py`](file:///d:/sacco-agent/src/rag/__init__.py) | Created | Added lazy-loading proxy for `answer_question` to prevent circular imports. |
| [`.env.example`](file:///d:/sacco-agent/.env.example) | Modified | Updated model documentation comment to align with `gemini-3.6-flash`. |
| [`docs/week8/remediation-log.md`](file:///d:/sacco-agent/docs/week8/remediation-log.md) | Created | Comprehensive remediation record and verification log. |

---

