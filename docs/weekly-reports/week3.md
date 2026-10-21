# Weekly Progress Report — Week 3

**Group / project:** I Evening — SACCO Loan Application Preparation Agent
**Week ending:** 18 September 2026 (Week 3 of 8: 14–18 September 2026)

Week 3 delivered a controlled, traceable RAG pipeline grounded in a 20-document synthetic SACCO policy corpus, and a 15-case evaluation in which all 15 cases passed.

## 1. Work completed against the weekly objectives

**Weekly focus:** Context engineering and RAG. Build a controlled, traceable Retrieval-Augmented Generation pipeline that grounds the agent's answers in an approved knowledge corpus, rather than the model's own knowledge, and evaluate it against controlled test cases.

| Deliverable | Status (Done / Partial / Not started) |
|---|---|
| Controlled SACCO policy corpus: 20 team-created synthetic Hangs SACCO documents in `Knowledge/` covering loan products (Development, Emergency, School Fees), eligibility, guarantors, documents, procedure, repayment, default and recovery, restructuring, membership, savings, dividends, member rights, complaints, exit/withdrawal, and governance/decision authority. No real member data or external material used | Done |
| Corpus / Source Register: all 20 sources, their purpose and provenance, in `docs/rag/corpus_register.md` | Done |
| RAG pipeline: ingestion, chunking, indexing and retrieval (`embeddings.py`, `retrieval.py`) and grounded generation with source citation (`rag.py`) | Done |
| RAG architecture documented in `docs/rag/rag_architecture.md` | Done |
| RAG architecture diagram | Done |
| 15 RAG test questions (5 answerable, 5 partially answerable, 5 deliberately unanswerable) run with `src/run_rag_eval.py` and manually evaluated against expected behaviour | Done |
| At least 3 retrieval/grounding failures documented with causes in `docs/rag/rag_failures.md` | Done |
| Carry over from Week 2: find the cause of the TC05 cut-off by logging the finish reason; complete the Date, Result and Known gaps lines in the v1.2 Version Information |  Done |
| Week 3 progress report (this document) | Done |

**Pipeline components**

| File | Role |
|---|---|
| `embeddings.py` | Loads and paragraph-chunks the corpus, embeds each chunk with `gemini-embedding-001`, caches the index to `knowledge_index.json` |
| `retrieval.py` | Embeds an incoming query and ranks all cached chunks by cosine similarity, returning the top-k matches |
| `rag.py` | Orchestrates retrieval and grounded generation. Only chunks above a similarity confidence threshold count as usable evidence; the model must cite its source and state explicitly when evidence is missing rather than guess. Reuses `call_gemini()` and `load_system_prompt()` from `src/baseline_chat.py` |

**Evaluation results:** 15 controlled questions, manually evaluated against expected behaviour.

| Question type | Cases | Pass | Partial | Fail |
|---|---|---|---|---|
| Answerable | 5 | 5 | 0 | 0 |
| Partially answerable | 5 | 5 | 0 | 0 |
| Deliberately unanswerable | 5 | 5 | 0 | 0 |
| **Total** | **15** | **15** | **0** | **0** |

Pass means correct answers and AI-boundary compliance: no fabricated figures on unanswerable questions, no guessed values on partially answerable questions, and accurate, cited answers on fully answerable questions. Full results are in `evidence/week3_rag_evaluation.json` and `docs/evaluation/week3-rag-eval-table.md`.

## 2. Key engineering decisions and why

- **Decision:** Use a controlled corpus of 20 team-created synthetic documents, with every source recorded in a register.
  **Why:** Answers must come from an approved, traceable knowledge base rather than the model's own knowledge, and no real member data is involved.
- **Decision:** Treat only chunks above a similarity confidence threshold as usable evidence, and instruct the model to cite its source and say so when evidence is missing.
  **Why:** This stops the model guessing on partially answerable and unanswerable questions, which carries the AI boundary (no invented figures) into the RAG pipeline.
- **Decision:** Separate "retrieval confidence" from "the model's own reported evidence gaps" in `rag.py`.
  **Why:** The raw similarity threshold proved an unreliable proxy for correctness (see failure 1 below).
- **Decision:** Reuse the Week 2 `call_gemini()` and `load_system_prompt()` rather than building a new model interface.
  **Why:** It keeps one tested path to the model across baseline and RAG.

## 3. Failures, challenges and current response

**Retrieval / grounding failures** (documented in `docs/rag/rag_failures.md`)

| # | Issue | Cause | Response / status |
|---|---|---|---|
| 1 | False-positive grounding signal: the automated confidence flag reported evidence found even for out-of-scope questions | Similarity scoring picks up shared domain vocabulary rather than true topical relevance | Addressed: retrieval confidence is now separated from the model's own reported evidence gaps in `rag.py` |
| 2 | Cross-product retrieval noise: questions about one loan product occasionally retrieved a chunk from a different product document | Product documents are structurally similar | Documented. Fixed |
| 3 | Incomplete inline citation: an answer drawing on two source documents cited only one | Not stated in the report | Documented. Fixed |

**Key finding:** The model's answers were reliable across all 15 cases. The weaknesses were in the pipeline's internal retrieval confidence signal, not in the generated answers. This shows the limits of using a raw similarity threshold as a correctness proxy.

**Other challenges**

- **Issue:** Running 15 evaluation cases back-to-back triggered a cascade of 429 (Too Many Requests) errors.
  **Cause:** Google's free-tier Gemini API limit of roughly 15 requests per minute.
  **Response / status:** Resolved. Added retry with escalating backoff to `call_gemini()` and spaced evaluation calls 10 seconds apart.
- **Issue:** The Week 2 prompt loader failed on the current prompt file.
  **Cause:** `load_system_prompt()` expected a `## Prompt` marker, but `prompts/v1.0.md` had evolved into a fully numbered section structure.
  **Response / status:** Resolved. The loader now extracts from the first numbered section through the Version Information section.
- **Issue:** The evaluation was one manual pass over 15 cases.
  **Response / status:** Results are treated as indicative, not conclusive.

## 4. Links

- **GitHub:** <https://github.com/KisomoseArnoldPatrick/sacco-agent>
- **ClickUp:** <https://app.clickup.com/1200440000000513/v/l/6-1200440000021229-1>

## 5. Individual contribution summary

| Member | Role | Task(s) owned this week | Evidence |
|---|---|---|---|
| Kisomose Arnold Patrick | Ingestion and chunking | Implement ingestion + chunking/segmentation (shared with Kabalebe Joshua) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.mdhttps://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.md |
| Hannington Wandera | Week 3 progress report | Compile Week 3 progress report | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/weekly-reports/week3.md |
| Kukiriza Sinai Jose | Policy corpus; ingestion and chunking | Assemble policy corpus (synthetic SACCO documents); implement ingestion + chunking/segmentation | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.mdhttps://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.md |
| Mugisha Modern | RAG test questions | Write 15 RAG test questions (answerable, partially answerable, unanswerable) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/src/run_rag_eval.py |
| Kabalebe Joshua | Ingestion and chunking | Implement ingestion + chunking/segmentation (shared with Kisomose Arnold Patrick) | https://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.mdhttps://github.com/KisomoseArnoldPatrick/sacco-agent/blob/main/docs/requirements/corpus-source-register.md |

## 6. Plan for next week

**Next week's focus:** Tools and function calling (Week 4, 21–25 September 2026).

Planned tasks:

- Implement `get_member_record()` and `calculate_repayment()` as explicit tools
- Integrate both tools with Gemini function calling
- Test authorization and failure behaviour
- Build directly on the AI Boundary Matrix reinforced in `sacco_governance_and_committees.md`
- Write the Week 4 progress report
