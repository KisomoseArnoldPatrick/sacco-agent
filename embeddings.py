
import os
import json
import glob
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

KNOWLEDGE_DIR = Path(__file__).resolve().parent / "Knowledge"
INDEX_CACHE_PATH = Path(__file__).resolve().parent / "knowledge_index.json"


def load_documents(knowledge_dir: Path = KNOWLEDGE_DIR) -> list[dict]:
    """Read every .md file in Knowledge/ into {id, source, text}."""
    docs = []
    for path in sorted(glob.glob(str(knowledge_dir / "*.md"))):
        text = Path(path).read_text(encoding="utf-8")
        docs.append({"source": Path(path).name, "text": text})
    return docs


def chunk_document(text: str, max_chars: int = 800) -> list[str]:
    """Split by paragraph, then group paragraphs up to max_chars per chunk."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks, current = [], ""
    for para in paragraphs:
        if len(current) + len(para) + 2 <= max_chars:
            current = f"{current}\n\n{para}".strip()
        else:
            if current:
                chunks.append(current)
            current = para
    if current:
        chunks.append(current)
    return chunks


def embed_text(text: str) -> list[float]:
    api_key = os.environ["GEMINI_API_KEY"]
    model = os.environ.get("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent"
    response = requests.post(
        url,
        params={"key": api_key},
        json={"content": {"parts": [{"text": text}]}},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["embedding"]["values"]


def build_index(force_rebuild: bool = False) -> list[dict]:
    """Build (or load cached) list of {source, chunk_id, text, embedding}."""
    if INDEX_CACHE_PATH.exists() and not force_rebuild:
        with open(INDEX_CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    index = []
    for doc in load_documents():
        chunks = chunk_document(doc["text"])
        for i, chunk in enumerate(chunks):
            embedding = embed_text(chunk)
            index.append({
                "source": doc["source"],
                "chunk_id": f"{doc['source']}#{i}",
                "text": chunk,
                "embedding": embedding,
            })
            print(f"Embedded {doc['source']} chunk {i} ({len(chunk)} chars)")

    with open(INDEX_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(index, f)
    return index


if __name__ == "__main__":
    idx = build_index(force_rebuild=True)
    print(f"\nIndexed {len(idx)} chunks from {len(load_documents())} documents.")