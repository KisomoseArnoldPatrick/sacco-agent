"""
RAG package initialization for the SACCO agent.
Provides package-level exports for retrieval and question answering.
"""
from rag.retrieval import retrieve_top_k

def answer_question(*args, **kwargs):
    """Lazy import of answer_question to avoid circular dependency with rag_chat."""
    from rag_chat import answer_question as _aq
    return _aq(*args, **kwargs)

__all__ = ["answer_question", "retrieve_top_k"]

