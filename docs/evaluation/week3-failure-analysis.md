# Week 3 — Documented RAG Failures

Three real retrieval/grounding issues observed during the 15-case evaluation
(`evidence/week3_rag_evaluation.json`). Each is a genuine issue found by
running the actual pipeline, not a hypothetical.

---

## Failure 1 — False-positive grounding signal on out-of-scope questions

**Observed in:** R11–R15 (all deliberately unanswerable questions).

**What happened:** The pipeline's `grounded` flag reported `True` for every
one of the 5 out-of-scope questions (mortgage loans, cryptocurrency,
SWIFT codes, branch transfers, credit scoring) — none of which are covered
anywhere in the corpus.

**Root cause:** `grounded` is defined purely as "did any retrieved chunk
score ≥ 0.55 cosine similarity?" In a single-domain corpus where every
document shares SACCO/loan/member vocabulary, an out-of-scope question
still scores moderately against unrelated chunks on vocabulary overlap
alone, clearing the threshold without being topically relevant.

**Consequence:** The `grounded` field cannot be trusted, on its own, to
distinguish "the answer is supported by evidence" from "retrieval found
something vaguely similar." In this run, the **model's own text** still
correctly stated the information was missing in all 5 cases — so the
symptom is a misleading internal metric, not an incorrect end-user answer.
That distinction is only visible on manual review, which is a limitation
of relying on the score threshold alone for automated grounding
evaluation.

**Fix direction:** Distinguish "retrieval confidence" (the similarity
score) from "answer groundedness" (whether the generated text is actually
supported). A more reliable version of this pipeline would either raise
the confidence threshold, or check the model's response for its own
stated evidence-sufficiency (which the prompt already asks it to report).

---

## Failure 2 — Cross-product retrieval noise from shared vocabulary

**Observed in:** R07 ("Development Loan... monthly repayment?") and R09
("...Development Loan, how much savings must each guarantor hold?").

**What happened:** In both cases, one of the top-3 retrieved chunks was
from `emergency_loan.md` — a different, unrelated loan product — even
though the question was specifically about the Development Loan.

**Root cause:** The three loan-product documents
(`development_loan.md`, `emergency_loan.md`, `school_fees_loan.md`) share
near-identical structure and vocabulary (interest rate, guarantors,
repayment period, grace period), so their chunk embeddings sit close
together in vector space. Pure semantic similarity does not reliably
disambiguate "same structure, different product."

**Consequence:** In both observed cases the model did not actually cite
or rely on the wrong document in its final answer, so there was no
visible harm here — but it shows retrieval quality would degrade further
with more, or more similar, loan products in the corpus.

**Fix direction:** Add lightweight metadata filtering (e.g., tag each
product chunk with its product name) so retrieval can be biased toward
chunks matching a product name mentioned in the query, rather than relying
on embeddings alone.

---

## Failure 3 — Incomplete inline citation relative to evidence actually used

**Observed in:** R01 ("What documents are required for a loan
application?").

**What happened:** The retrieved evidence set included both
`supporting_documents.md` and `loan_requirements.md`, and the answer
content clearly drew on both. However, the model's inline citation named
only `supporting_documents.md`.

**Root cause:** The grounded prompt instructs the model to "cite the
source," but does not require it to cite *every* source it drew on when
multiple documents contribute to one answer.

**Consequence:** A user reading only the inline citation would
under-estimate the evidence base behind the answer — a transparency gap,
even though the content itself was accurate.

**Fix direction:** Strengthen the grounding instruction to explicitly
require citing every source document that contributed to the answer, not
just one representative source.
