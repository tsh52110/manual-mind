"""Retrieval configurations for the before/after study.

Each named config changes exactly ONE variable relative to `baseline`, so Ragas
metric deltas are attributable to that variable.
"""
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = REPO_ROOT / "data" / "daimler"
INDEX_DIR = REPO_ROOT / "indexes"
MANIFEST = REPO_ROOT / "data" / "manuals.json"

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
GENERATION_MODEL = "claude-haiku-4-5-20251001"
JUDGE_MODEL = "claude-sonnet-5"

BRANDS = ["Freightliner", "Western Star", "FUSO", "Mercedes-Benz Trucks",
          "Mercedes-Benz Buses", "Other Daimler"]


def load_manifest() -> list[dict]:
    """Corpus manifest: one entry per manual (brand, title, file, source, license).

    Uploads via the app append here, so read fresh rather than caching at import.
    """
    import json
    with open(MANIFEST) as f:
        return json.load(f)["manuals"]


def manuals_by_id() -> dict[str, dict]:
    return {m["id"]: m for m in load_manifest()}


@dataclass(frozen=True)
class RAGConfig:
    name: str
    chunk_size: int = 800
    chunk_overlap: int = 150
    top_k: int = 4
    retriever: str = "dense"        # "dense" | "hybrid" (BM25 + dense ensemble)
    use_reranker: bool = False      # cross-encoder rerank of fetch_k candidates
    fetch_k: int = 20               # candidates fetched when reranking
    description: str = ""

    @property
    def index_name(self) -> str:
        """Configs sharing a chunking share an index."""
        return f"chunk{self.chunk_size}-ov{self.chunk_overlap}"

    @property
    def index_path(self) -> Path:
        return INDEX_DIR / self.index_name


CONFIGS = {
    "baseline": RAGConfig(
        name="baseline",
        description="Dense-only, chunk 800/150, k=4",
    ),
    "small-chunks": RAGConfig(
        name="small-chunks",
        chunk_size=300, chunk_overlap=100,
        description="Baseline but chunk 300/100 (the forked repo's original setting)",
    ),
    "reranker": RAGConfig(
        name="reranker",
        use_reranker=True,
        description="Baseline + cross-encoder rerank of top-20 candidates down to k=4",
    ),
    "hybrid": RAGConfig(
        name="hybrid",
        retriever="hybrid",
        description="Baseline but hybrid BM25+dense (equal weights) instead of dense-only",
    ),
}
