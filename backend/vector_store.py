"""
Vector store abstraction.

Tries to use sentence-transformers + FAISS for semantic search (best quality).
If those packages/models aren't available (e.g. no internet to download the
model), it transparently falls back to a scikit-learn TF-IDF + cosine-similarity
index so the platform still works end-to-end offline.
"""
from typing import List, Dict, Tuple
import numpy as np

_BACKEND = None  # "dense" or "tfidf"


class VectorStore:
    def __init__(self):
        self.records: List[Dict] = []   # parallel to embedding rows
        self._dense_index = None
        self._model = None
        self._tfidf_vectorizer = None
        self._tfidf_matrix = None
        self._init_backend()

    def _init_backend(self):
        global _BACKEND
        import os
        # If explicitly set to tfidf (e.g. on memory-constrained free hosting),
        # skip the heavy sentence-transformers model entirely.
        if os.environ.get("VECTOR_BACKEND", "").lower() == "tfidf":
            _BACKEND = "tfidf"
            return
        # Give the HF Hub a short timeout so a flaky/absent connection falls back
        # to TF-IDF quickly instead of hanging server startup for a minute+.
        os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "3")
        os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "5")
        try:
            from sentence_transformers import SentenceTransformer
            import faiss  # noqa
            self._model = SentenceTransformer("all-MiniLM-L6-v2")
            _BACKEND = "dense"
        except Exception:
            _BACKEND = "tfidf"

    @property
    def backend(self) -> str:
        return _BACKEND

    def add(self, records: List[Dict]):
        """records: list of {chunk_id, text, ...metadata}"""
        if not records:
            return
        self.records.extend(records)
        self._rebuild_index()

    def _rebuild_index(self):
        texts = [r["text"] for r in self.records]
        if not texts:
            return
        if _BACKEND == "dense":
            import faiss
            embeddings = self._model.encode(texts, normalize_embeddings=True)
            embeddings = np.array(embeddings, dtype="float32")
            index = faiss.IndexFlatIP(embeddings.shape[1])
            index.add(embeddings)
            self._dense_index = index
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._tfidf_vectorizer = TfidfVectorizer(stop_words="english", max_features=20000)
            self._tfidf_matrix = self._tfidf_vectorizer.fit_transform(texts)

    def search(self, query: str, top_k: int = 5) -> List[Tuple[Dict, float]]:
        if not self.records:
            return []
        if _BACKEND == "dense":
            q_emb = self._model.encode([query], normalize_embeddings=True)
            q_emb = np.array(q_emb, dtype="float32")
            scores, idxs = self._dense_index.search(q_emb, min(top_k, len(self.records)))
            results = []
            for score, idx in zip(scores[0], idxs[0]):
                if idx == -1:
                    continue
                results.append((self.records[idx], float(score)))
            return results
        else:
            from sklearn.metrics.pairwise import cosine_similarity
            q_vec = self._tfidf_vectorizer.transform([query])
            sims = cosine_similarity(q_vec, self._tfidf_matrix)[0]
            top_idx = sims.argsort()[::-1][:top_k]
            return [(self.records[i], float(sims[i])) for i in top_idx if sims[i] > 0]

    def stats(self) -> Dict:
        return {
            "backend": _BACKEND,
            "total_chunks": len(self.records),
            "unique_docs": len(set(r["doc_id"] for r in self.records)) if self.records else 0,
        }
