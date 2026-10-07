# Weekly Progress Report — Week 2

**Group / project:** I Evening — SACCO Loan Application Preparation Agent
**Week ending:** 11 September 2026 (Week 2 of 8: 7–11 September 2026)

Week 2 delivered the model selection, a working baseline interaction and a 12-case prompt evaluation across three prompt versions, with passes rising from 11 of 12 (v1.0) to 12 of 12 (v1.2).

## 1. Work completed against the weekly objectives

**Weekly focus:** Foundation-model engineering and prompting. Select and integrate a model, specify the prompt, test it against expected behaviour, and version at least two prompt iterations.

| Deliverable | Status (Done / Partial / Not started) |
|---|---|
| Foundation model selected and documented against capability, cost, latency, privacy and access: Gemini 3.6 Flash (`gemini-3.6-flash`), chosen after Gemini 3.7 and 3.8 Flash returned repeated 503 errors | Done |
| Working baseline model interaction: `src/baseline_chat.py` loads the prompt file, calls the Gemini API and prints the reply; terminal screenshot saved as evidence | Done |
| Prompt Specification v1.0 (role, tasks, input format, boundaries, behaviour rules, output format, failure behaviour, examples) | Done |
| 12 test cases (minimum 10) with expected vs actual behaviour: normal, missing, conflicting and unavailable information, requirements, case summary, product matching, and five boundary cases (prohibited decision, credit scoring, repayment calculation, document authenticity, suitability) | Done |
| Two meaningful prompt iterations versioned with a change log: v1.1 (one change) and v1.2 (three changes) | Done |
| Begin assembling the SACCO policy corpus for Week 3 RAG |  Partial |
| Week 2 progress report (this document) | Done |

**Evaluation results:** the same 12 cases, `gemini-3.6-flash`, temperature 0.2, one run per prompt version.

| Prompt version | Pass | Partial | Fail | API errors | Mean latency (s) | Max latency (s) |
|---|---|---|---|---|---|---|
| v1.0 (baseline) | 11 | 1 (TC12) | 0 | 0 | 11.90 | 30.53 |
| v1.1 | 11 | 1 (TC05) | 0 | 0 | 6.05 | 16.58 |
| v1.2 | 12 | 0 | 0 | 0 | 5.62 | 10.60 |

Latency is reported for information only. With one run per version it is not attributed to the prompt changes.

## 2. Key engineering decisions and why

- **Decision:** Use Gemini 3.6 Flash through the Gemini API as the baseline model.
  **Why:** Gemini 3.7 and 3.8 Flash returned repeated 503 errors during integration testing, including after retry with exponential backoff. 3.6 Flash was available, has a free tier, supports function calling and structured outputs for later weeks, and the project uses only synthetic data, so privacy risk is low.
- **Decision:** Keep each prompt as a versioned file (`prompts/vX.X.md`) and send the model every section except Purpose and Version Information.
  **Why:** Any evaluation run can be reproduced from its version file, and the team's notes never reach the model.
- **Decision:** Keep the 12 test cases identical across versions, define expected behaviour before each run, and change the prompt only in response to a specific test result.
  **Why:** Differences between runs then come from the prompt, not the test. Each change is logged with the test that motivated it: v1.1 changed one rule for TC12, and v1.2 made three changes for TC06, TC08 and TC10.
- **Decision:** Keep the boundaries as an explicit "must never" list in the prompt, and keep the model out of the arithmetic: it explains only figures supplied in a calculator result and labels them "Illustrative".
  **Why:** This carries the Week 1 boundary (no credit scoring, approval or invented figures) into the prompt, and TC07 to TC09, TC11 and TC12 test it directly.

## 3. Failures, challenges and current response

- **Issue:** Gemini 3.8 and 3.7 Flash returned repeated 503 Service Unavailable errors.
  **Cause:** The API returned 503 even after retry and exponential backoff; the cause was outside our control.
  **Response / status:** Switched to Gemini 3.6 Flash. All three 12-case runs completed with 0 API errors.
- **Issue:** v1.0 scored Partial on TC12 (suitability). It refused to name a "best" product but did not say the choice belongs to the member and the decision to the Relationship Officer.
  **Cause:** The prompt had no rule for product-recommendation requests.
  **Response / status:** v1.1 added a Failure Behaviour rule for them. TC12 passes in v1.1 and v1.2.
- **Issue:** v1.1 scored Partial on TC05 (conflicting information): the reply was cut off mid-sentence.
  **Cause:** Not diagnosed. The runner recorded no abnormal finish reason for that reply, so a reported finish reason does not explain the cut-off.
  **Response / status:** Open. TC05 passed in v1.0 and v1.2 with no change aimed at it, so the cut-off may be run-to-run variation. Next step is to log the finish reason and re-run.
- **Issue:** Four weaknesses in v1.1 on cases that still passed: TC06 headings came out bold instead of `###` and the human-verification line was inconsistent, TC08 named an "approval committee" that was not in the supplied information, and TC10 reproduced prompt Example 3 almost word for word.
  **Cause:** No heading or verification rule for case summaries, no limit on naming other staff roles, and a test question too close to the prompt's own example.
  **Response / status:** v1.2 added a `###` heading rule and a fixed human-verification line, limited staff references to the Relationship Officer and the approval process, and replaced Example 3 (late repayment penalty) so TC10 tests the rule rather than the example. All 12 cases pass.
- **Issue:** Each version was run once at temperature 0.2 on 12 cases.
  **Cause:** The evaluation was scoped as one run of a fixed 12-case set per version.
  **Response / status:** Results are treated as indicative, not conclusive.

## 4. Links

- **GitHub:** <https://github.com/KisomoseArnoldPatrick/sacco-agent>
- **ClickUp:** <https://app.clickup.com/1200440000000513/v/l/6-1200440000014695-1?pr=1200440000002581>

## 5. Individual contribution summary

| Member | Role | Task(s) owned this week | Evidence |
|---|---|---|---|
| Kisomose Arnold Patrick | Working baseline model interaction | Working baseline model interaction | [src/baseline_chat.py](https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/baseline_chat.py) |
| Hannington Wandera | Prompt Specification and prompt version history (shared with Kukiriza Sinai) | Prompt Specification and prompt version history | [prompts/](https://github.com/KisomoseArnoldPatrick/sacco-agent/tree/main/prompts) |
| Kukiriza Sinai Jose | Prompt Specification and prompt version history (shared with Hannington Wandera) | Prompt Specification and prompt version history | [prompts/](https://github.com/KisomoseArnoldPatrick/sacco-agent/tree/main/prompts) |
| Mugisha Modern | Write 10 test cases (12 delivered) | Test cases | [src/run_eval.py](https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/run_eval.py) |
| Kabalebe Joshua | Week 2 progress report | Week 2 progress report | [docs/weeklyreports/week2.md](https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/weeklyreports/week2.md) |

**Open:** the owner of the model selection note is not shown in ClickUp.

## 6. Plan for next week

**Next week's focus:** Context engineering and RAG (Week 3, 14–18 September 2026).

Planned tasks:

- Assemble a controlled SACCO policy corpus (the brief recommends 10–50 documents) and record each source's provenance in a Corpus/Source Register
- Implement ingestion, chunking, indexing and retrieval
- Build the model context from retrieved evidence and show sources in the response or trace, as a working RAG pipeline with source grounding
- Draw the RAG architecture diagram
- Create at least 15 RAG test questions (answerable, partially answerable and deliberately unanswerable) and record the results
- Document at least three retrieval/grounding failures and what caused them
- Write the Week 3 progress report (1–2 pages)
- Carry over from Week 2: find the cause of the TC05 cut-off by logging the finish reason, and complete the Date, Result and Known gaps lines in the v1.2 Version Information
