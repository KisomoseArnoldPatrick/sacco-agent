# Week 3 Progress Report — Controlled Context and RAG

## Objective

Build a controlled, traceable Retrieval-Augmented Generation (RAG) pipeline
that grounds the SACCO Loan Application Preparation Agent's answers in an
approved knowledge corpus, rather than relying on the model's own
knowledge, and evaluate that pipeline against controlled test cases.

## Work completed

### 1. Knowledge corpus

Created 20 team-created synthetic Hangs SACCO policy documents in
`Knowledge/`, covering loan products (Development, Emergency, School
Fees), eligibility, guarantors, documents, procedure, repayment, default
and recovery, restructuring, membership, savings, dividends, member
rights, complaints, exit/withdrawal, and governance/decision authority.
No real member data or externally sourced material was used.

### 2. Corpus register

Documented all 20 sources, their purpose and provenance in
`docs/rag/corpus_register.md`.

### 3. RAG pipeline

Implemented the pipeline across three files:

- `embeddings.py` — loads and paragraph-chunks the corpus, embeds each
  chunk with the `gemini-embedding-001` model, and caches the index to
  `knowledge_index.json`.
- `retrieval.py` — embeds an incoming query and ranks all cached chunks by
  cosine similarity, returning the top-k matches.
- `rag.py` — orchestrates retrieval and grounded generation: only chunks
  above a similarity confidence threshold are treated as usable evidence;
  the model is instructed to cite its source and to state explicitly when
  evidence is missing rather than guess. Reuses the existing Week 2
  `call_gemini()` and `load_system_prompt()` functions from
  `src/baseline_chat.py`.

The pipeline and its design decisions are documented in
`docs/rag/rag_architecture.md`.

### 4. Fifteen-case evaluation

Ran `src/run_rag_eval.py` against 15 controlled questions — 5 answerable,
5 partially answerable, 5 deliberately unanswerable — and manually
evaluated each against expected behaviour. Results:
**15/15 pass** on answer correctness and AI-boundary compliance: no
fabricated figures on unanswerable questions, no guessed values on
partially answerable questions, and accurate, cited answers on fully
answerable questions. Full results are in
`evidence/week3_rag_evaluation.json` and
`docs/evaluation/week3-rag-eval-table.md`.

### 5. Documented failures

Identified and documented three genuine retrieval/grounding issues from
the actual evaluation run, in `docs/rag/rag_failures.md`:

1. A false-positive grounding signal — the automated confidence flag
   reported evidence was found even for out-of-scope questions, because
   similarity scoring picks up shared domain vocabulary rather than true
   topical relevance.
2. Cross-product retrieval noise — questions about one loan product
   occasionally retrieved a chunk from a different, structurally similar
   product document.
3. Incomplete inline citation — an answer drawing on two source documents
   cited only one of them.

## Key finding

The model's actual answers were reliable across all 15 cases; the
weaknesses found were entirely in the pipeline's internal retrieval
confidence signal, not in the generated answers. This is itself a useful
finding about the limits of using a raw similarity threshold as a
correctness proxy, and has been addressed by separating "retrieval
confidence" from "the model's own reported evidence gaps" in `rag.py`.

## Challenges encountered

- Google's free-tier Gemini API enforces a roughly 15-requests-per-minute
  limit; running 15 evaluation cases back-to-back initially triggered a
  cascade of 429 (Too Many Requests) errors. Resolved by adding
  retry-with-escalating-backoff to `call_gemini()` and spacing evaluation
  calls 10 seconds apart.
- The Week 2 baseline's prompt loader (`load_system_prompt()`) was written
  to expect a `## Prompt` marker, but `prompts/v1.0.md` had since evolved
  into a fully numbered section structure. Fixed by rewriting the loader
  to extract from the first numbered section through the Version
  Information section.

## Next step

Proceed to Week 4: implement `get_member_record()` and
`calculate_repayment()` as explicit tools, integrate them with Gemini
function calling, and test authorization and failure behaviour — building
directly on the AI Boundary Matrix reinforced in
`sacco_governance_and_committees.md`.