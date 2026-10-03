
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent / "src"))

from retrieval import retrieve_top_k
from baseline_chat import call_gemini, load_system_prompt

MIN_CONFIDENCE = 0.55  # below this, treat as "no good evidence found"


def build_grounded_prompt(query: str, chunks: list[dict]) -> str:
    if not chunks:
        return (
            f"Question: {query}\n\n"
            "No relevant SACCO policy evidence was found in the knowledge base. "
            "Say clearly that this cannot be answered from the available documents, "
            "and do not guess or use outside knowledge."
        )

    context_block = "\n\n".join(
        f"[Source: {c['source']}]\n{c['text']}" for c in chunks
    )
    return (
        f"Use ONLY the following retrieved SACCO policy evidence to answer. "
        f"Cite the source filename after your answer. If the evidence does not "
        f"fully answer the question, say what is missing rather than guessing.\n\n"
        f"--- RETRIEVED EVIDENCE ---\n{context_block}\n--- END EVIDENCE ---\n\n"
        f"Question: {query}"
    )


GAP_PHRASES = [
    "cannot be determined", "does not contain", "missing from",
    "cannot currently be verified", "is not covered", "not included in",
    "no information", "not specified", "not mentioned", "cannot be confirmed",
    "cannot be provided", "is missing", "not fully",
]


def answer_question(query: str, k: int = 3) -> dict:
    chunks = retrieve_top_k(query, k=k)
    strong_chunks = [c for c in chunks if c["score"] >= MIN_CONFIDENCE]

    system_prompt = load_system_prompt()
    grounded_prompt = build_grounded_prompt(query, strong_chunks)
    answer = call_gemini(grounded_prompt, system_prompt)

    self_reported_gap = any(phrase in answer.lower() for phrase in GAP_PHRASES)

    return {
        "query": query,
        "answer": answer,
        "sources": [c["source"] for c in strong_chunks],
        "retrieved_scores": [round(c["score"], 3) for c in chunks],
        "retrieval_confidence_met": bool(strong_chunks),  # was "grounded" — score-threshold only
        "self_reported_gap": self_reported_gap,             # model itself flagged missing/unsupported info
    }


if __name__ == "__main__":
    result = answer_question("What documents are required for a loan application?")
    print("Answer:", result["answer"])
    print("Sources:", result["sources"])
    print("Grounded:", result["grounded"])