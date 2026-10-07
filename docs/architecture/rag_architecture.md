# RAG Architecture — Week 3

## Pipeline

```
Knowledge/*.md  (20 synthetic SACCO policy documents)
        |
        v
  Chunking (embeddings.py: chunk_document)
  - split by paragraph, grouped up to ~800 characters per chunk
        |
        v
  Embedding (embeddings.py: embed_text)
  - Gemini API, model: gemini-embedding-001
        |
        v
  Vector index (knowledge_index.json)
  - cached list of {source, chunk_id, text, embedding}
  - rebuilt on demand with `python embeddings.py`
        |
        v
  User question
        |
        v
  Retrieval (retrieval.py: retrieve_top_k)
  - embed the query
  - rank all chunks by cosine similarity
  - return top-k chunks (k=3 by default)
        |
        v
  Grounded context construction (rag.py: build_grounded_prompt)
  - only chunks scoring >= 0.55 similarity are treated as strong evidence
  - if no chunk clears that threshold, the model is explicitly told no
    evidence was found and instructed not to guess
        |
        v
  Gemini (src/baseline_chat.py: call_gemini)
  - system prompt: prompts/v1.0.md (SACCO Loan Application Preparation Agent)
  - grounded prompt: retrieved evidence + question + citation instruction
        |
        v
  Answer + cited source document(s)
```

## Design choices and why

- **No external vector database.** With ~47 chunks from 20 documents, an
  in-memory cosine-similarity search over a cached JSON file is simpler to
  build, run and explain than standing up a vector database, and is
  sufficient at this corpus size (per the assignment's guidance to build
  the smallest credible system).
- **Confidence threshold, not just top-k.** Returning the top-3 chunks
  regardless of relevance would force the model to "ground" an answer in
  irrelevant evidence for out-of-scope questions. The `MIN_CONFIDENCE`
  threshold (0.55) lets the pipeline distinguish "found relevant evidence"
  from "found nothing useful," which is what the 15-case evaluation tests.
- **Source citation is enforced in the prompt, not inferred after the
  fact.** The grounded prompt explicitly instructs the model to cite the
  source filename and to state what's missing rather than guess, so
  traceability is built into generation rather than added afterward.

## Known limitation

Chunking is paragraph-based rather than semantic; a policy rule that spans
a table plus surrounding text can occasionally split across two chunks.
This is one of the three documented retrieval/grounding failures (see the
Week 3 evaluation).
