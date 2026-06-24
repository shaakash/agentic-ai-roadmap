"""Retrieve definition/methodology chunks for the terms an answer references.

Two retrieval modes:
    for_terms(terms, k)    — targeted: query using the terms themselves as text.
                             Used after the semantic layer runs: we know exactly
                             which metric_ids, buckets, and lenses were involved.
    for_question(q, k)     — free-text: semantic nearest-neighbour search.
                             Used for pure "what does X mean?" intent questions.

Both modes return RetrievedDef objects with `text`, `citation`, and `score`.
The narration layer is responsible for citing the source in its response.

The retriever is lazy: the Chroma client is opened on first use, not at import.
This avoids slowing down imports when the knowledge layer is not needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # …/delinquency-benchmarking-agent
_CHROMA_DIR_DEFAULT = _PROJECT_ROOT / "data" / "chroma"
_COLLECTION_NAME = "definitions"


# ---------------------------------------------------------------------------
# Return type
# ---------------------------------------------------------------------------

@dataclass
class RetrievedDef:
    text:     str     # full chunk text (heading + body)
    citation: str     # e.g. "Methodology 4.1 – Coincidence view"
    terms:    list[str]  # term tags from the chunk
    score:    float   # cosine distance (lower = more similar)


# ---------------------------------------------------------------------------
# DefinitionRetriever
# ---------------------------------------------------------------------------

class DefinitionRetriever:
    """Thin wrapper around a Chroma collection for definition retrieval.

    Args:
        chroma_path:  Path to the persistent Chroma directory.
                      Defaults to data/chroma/ relative to the project root.

    Example::

        retriever = DefinitionRetriever()

        # After a semantic-layer query for coincidence_acct_pct:
        defs = retriever.for_terms(["coincidence", "coincidence_acct_pct"], k=2)

        # For a pure "what is roll rate?" question:
        defs = retriever.for_question("what is the 30-60 roll rate?", k=3)
    """

    def __init__(self, chroma_path: str | Path | None = None) -> None:
        self._chroma_path = Path(chroma_path) if chroma_path else _CHROMA_DIR_DEFAULT
        self._client: Any = None
        self._collection: Any = None

    # ------------------------------------------------------------------
    # Lazy init
    # ------------------------------------------------------------------

    def _ensure_connected(self) -> None:
        if self._collection is not None:
            return

        import chromadb
        from chromadb.utils import embedding_functions

        if not self._chroma_path.exists():
            raise FileNotFoundError(
                f"Chroma index not found at '{self._chroma_path}'. "
                "Run `make corpus` (or `python -m delinquency_agent.knowledge.corpus`) "
                "to build the index first."
            )

        self._client = chromadb.PersistentClient(path=str(self._chroma_path))
        ef = embedding_functions.DefaultEmbeddingFunction()

        try:
            self._collection = self._client.get_collection(
                name=_COLLECTION_NAME,
                embedding_function=ef,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Could not open Chroma collection '{_COLLECTION_NAME}' "
                f"at '{self._chroma_path}'. Has `make corpus` been run? Error: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def for_terms(self, terms: list[str], k: int = 3) -> list[RetrievedDef]:
        """Retrieve the top-k chunks most relevant to the given metric/lens terms.

        The query text is the terms joined with spaces, which reliably retrieves
        the definitional chunk for those exact terms. For example, terms
        ["coincidence", "coincidence_acct_pct"] retrieve the coincidence-view
        chunk even if the user's question phrased it differently.

        Args:
            terms: Term tags to look up (metric_id, lens name, bucket name, etc.).
            k:     Maximum number of chunks to return.

        Returns:
            List of RetrievedDef, sorted by ascending cosine distance (best first).
        """
        if not terms:
            return []

        self._ensure_connected()
        query_text = " ".join(terms)
        return self._query(query_text, k=k)

    def for_question(self, question: str, k: int = 3) -> list[RetrievedDef]:
        """Free-text semantic search over the definition corpus.

        Use this when the planner identifies a "definition" intent question
        without a pre-determined set of metric/lens terms.

        Args:
            question: Natural-language question from the user.
            k:        Maximum number of chunks to return.

        Returns:
            List of RetrievedDef, sorted by ascending cosine distance (best first).
        """
        if not question.strip():
            return []

        self._ensure_connected()
        return self._query(question, k=k)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _query(self, query_text: str, k: int) -> list[RetrievedDef]:
        result = self._collection.query(
            query_texts=[query_text],
            n_results=min(k, self._collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        docs      = result["documents"][0]
        metas     = result["metadatas"][0]
        distances = result["distances"][0]

        return [
            RetrievedDef(
                text     = doc,
                citation = meta.get("citation", "Unknown"),
                terms    = [t for t in meta.get("terms", "").split(",") if t],
                score    = dist,
            )
            for doc, meta, dist in zip(docs, metas, distances)
        ]

    def count(self) -> int:
        """Return the number of indexed chunks (useful for health checks)."""
        self._ensure_connected()
        return self._collection.count()
