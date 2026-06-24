"""Build the definitions RAG corpus: read methodology docs, chunk, embed, index.

Each chunk is one `## Heading` section of a methodology markdown file.
Metadata stored with each vector:
    - citation: full heading text (e.g. "Methodology 4.1 – Coincidence view")
    - terms:    comma-joined term tags from the `terms:` line

Run as a script (or via `make corpus`) to (re)build the Chroma index:
    python -m delinquency_agent.knowledge.corpus

The index is written to the path set in CHROMA_PATH (default: data/chroma/).
The embedding model is all-MiniLM-L6-v2, run locally via ONNX (no API key).
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent  # …/delinquency-benchmarking-agent
_CORPUS_DIR_DEFAULT = _PROJECT_ROOT / "corpus" / "definitions"
_CHROMA_DIR_DEFAULT = _PROJECT_ROOT / "data" / "chroma"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class CorpusChunk:
    chunk_id:  str
    citation:  str          # full heading text
    terms:     list[str]    # metric/lens keys this chunk covers
    text:      str          # full body text of the chunk


# ---------------------------------------------------------------------------
# Markdown parser — one chunk per ## heading
# ---------------------------------------------------------------------------

def _parse_markdown_file(md_path: Path) -> list[CorpusChunk]:
    """Split a methodology markdown file into heading-level chunks.

    Convention (from corpus/definitions/methodology.md):
        ## Section heading text
        terms: term1, term2, term3
        <body text...>

    The `terms:` line on the first content line is optional but strongly
    recommended. If missing, the chunk is still indexed with an empty terms list.
    """
    raw = md_path.read_text(encoding="utf-8")

    # Split on "## " at the start of a line
    parts = re.split(r"(?m)^## ", raw)

    chunks: list[CorpusChunk] = []
    for i, part in enumerate(parts):
        if not part.strip():
            continue

        lines = part.splitlines()
        heading = lines[0].strip()  # "Definitions 1.1 – Member and Industry"
        rest = lines[1:]

        # Extract terms: tag if present on the first non-blank content line
        terms: list[str] = []
        body_start = 0
        for j, line in enumerate(rest):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("terms:"):
                terms_raw = stripped[len("terms:"):].strip()
                terms = [t.strip() for t in terms_raw.split(",") if t.strip()]
                body_start = j + 1
            break

        body = "\n".join(rest[body_start:]).strip()

        chunk_id = f"{md_path.stem}_{i:03d}"
        chunks.append(CorpusChunk(
            chunk_id = chunk_id,
            citation = heading,
            terms    = terms,
            text     = f"## {heading}\n\n{body}",
        ))

    return chunks


def load_definition_docs(corpus_path: str | Path | None = None) -> list[CorpusChunk]:
    """Load all *.md files under corpus_path and return a flat list of chunks."""
    corpus_dir = Path(corpus_path) if corpus_path else _CORPUS_DIR_DEFAULT
    if not corpus_dir.exists():
        raise FileNotFoundError(
            f"Corpus directory not found: {corpus_dir}. "
            "Create corpus/definitions/ with at least one .md file."
        )

    chunks: list[CorpusChunk] = []
    for md_file in sorted(corpus_dir.glob("*.md")):
        chunks.extend(_parse_markdown_file(md_file))

    if not chunks:
        raise ValueError(f"No chunks found in {corpus_dir}. Check .md file format.")

    return chunks


# ---------------------------------------------------------------------------
# Chroma index builder
# ---------------------------------------------------------------------------

def build_index(
    chunks: list[CorpusChunk],
    chroma_path: str | Path | None = None,
    *,
    collection_name: str = "definitions",
    reset: bool = True,
) -> None:
    """Embed chunks with all-MiniLM-L6-v2 (local ONNX) and persist to Chroma.

    Args:
        chunks:          Parsed corpus chunks.
        chroma_path:     Directory for the persistent Chroma store.
        collection_name: Chroma collection name.
        reset:           If True (default), drop and recreate the collection
                         so this function is idempotent.
    """
    import chromadb
    from chromadb.utils import embedding_functions

    chroma_dir = Path(chroma_path) if chroma_path else _CHROMA_DIR_DEFAULT
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=str(chroma_dir))
    ef = embedding_functions.DefaultEmbeddingFunction()

    if reset:
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )

    ids       = [c.chunk_id for c in chunks]
    documents = [c.text     for c in chunks]
    metadatas = [
        {"citation": c.citation, "terms": ",".join(c.terms)}
        for c in chunks
    ]

    # Chroma requires non-empty IDs and documents
    valid = [(i, d, m) for i, d, m in zip(ids, documents, metadatas) if d.strip()]
    if not valid:
        raise ValueError("All chunks are empty — nothing to index.")

    v_ids, v_docs, v_metas = zip(*valid)
    collection.add(ids=list(v_ids), documents=list(v_docs), metadatas=list(v_metas))

    print(f"[corpus] Indexed {len(v_ids)} chunks → {chroma_dir}")


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """Build (or rebuild) the Chroma definitions index.

    Usage:
        python -m delinquency_agent.knowledge.corpus [corpus_dir] [chroma_dir]

    Both arguments are optional; defaults come from the project layout.
    """
    args = argv or sys.argv[1:]
    corpus_arg = args[0] if len(args) > 0 else None
    chroma_arg = args[1] if len(args) > 1 else os.environ.get("CHROMA_PATH")

    print("[corpus] Parsing corpus documents …")
    chunks = load_definition_docs(corpus_arg)
    print(f"[corpus] Found {len(chunks)} chunks across all .md files")
    for c in chunks:
        print(f"         {c.chunk_id:30s}  [{', '.join(c.terms[:4])}{'…' if len(c.terms) > 4 else ''}]")

    print("[corpus] Embedding and indexing …")
    build_index(chunks, chroma_arg)
    print("[corpus] Done. Run make retrieve to test retrieval.")


if __name__ == "__main__":
    main()
