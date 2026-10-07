
import math

from embeddings import build_index, embed_text


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def retrieve_top_k(query: str, k: int = 3, min_score: float = 0.0) -> list[dict]:
    """Return the top-k most relevant chunks for a query, each with its score."""
    index = build_index()
    query_embedding = embed_text(query)

    scored = []
    for entry in index:
        score = cosine_similarity(query_embedding, entry["embedding"])
        if score >= min_score:
            scored.append({**entry, "score": score})

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:k]


if __name__ == "__main__":
    results = retrieve_top_k("What documents are required for a loan application?", k=3)
    for r in results:
        print(f"[{r['score']:.3f}] {r['source']} :: {r['text'][:100]}...")