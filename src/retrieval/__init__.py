"""ICMR STW Retrieval Layer.

Provides lexical (BM25), semantic (TF-IDF cosine), and hybrid (RRF)
retrieval over the ICMR STW knowledge base, with an abstracted reranker.

No LLM, SLM, or AI generation is used in this module.
"""

from .models import RetrievalResult, NO_RELIABLE_ICMR_EVIDENCE
from .lexical import LexicalRetriever
from .semantic import SemanticRetriever
from .hybrid import HybridRetriever
from .reranker import Reranker, TFIDFReranker

__all__ = [
    "RetrievalResult",
    "NO_RELIABLE_ICMR_EVIDENCE",
    "LexicalRetriever",
    "SemanticRetriever",
    "HybridRetriever",
    "Reranker",
    "TFIDFReranker",
]
