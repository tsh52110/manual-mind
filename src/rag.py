"""Retrieval + grounded, citing answers over the manual corpus.

`answer()` returns the generated answer plus the retrieved contexts and a numbered
source list (manual title + page). The prompt forces inline [n] citations that map
onto that source list, so the UI can render source cards under every answer.
"""
from __future__ import annotations

import json
import os

# faiss-cpu and torch each bundle their own OpenMP on macOS; loading the larger
# index with both runtimes active segfaults (exit 139). Single-threading OpenMP
# before either library is imported avoids it, at no practical cost here.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from functools import lru_cache

from dotenv import load_dotenv
from langchain_core.documents import Document

from src.config import CONFIGS, GENERATION_MODEL, RERANKER_MODEL, RAGConfig

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SYSTEM_PROMPT = """You are ManualMind, a technical assistant that answers questions \
about equipment strictly from excerpts of official service manuals.

Rules:
- Answer ONLY from the numbered context excerpts. Never use outside knowledge for \
specs, procedures, torques, capacities, or part numbers.
- Cite every factual claim inline with the excerpt number(s) in square brackets, \
e.g. "Tire pressure is 20 psi [1]."
- If the excerpts do not contain the answer, say so plainly in one short \
sentence. Do not guess, and do not add advice or information that is not in \
the excerpts.
- Safety warnings/cautions present in the excerpts must be repeated.
- Be concise: short paragraphs or numbered steps."""


@lru_cache(maxsize=1)
def _embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        encode_kwargs={"normalize_embeddings": True},
    )


@lru_cache(maxsize=4)
def _vectorstore(index_name: str):
    from langchain_community.vectorstores import FAISS
    cfg = next(c for c in CONFIGS.values() if c.index_name == index_name)
    return FAISS.load_local(
        str(cfg.index_path), _embeddings(), allow_dangerous_deserialization=True
    )


@lru_cache(maxsize=4)
def _chunk_docs(index_name: str) -> tuple[Document, ...]:
    cfg = next(c for c in CONFIGS.values() if c.index_name == index_name)
    docs = []
    with open(cfg.index_path / "chunks.jsonl") as f:
        for line in f:
            rec = json.loads(line)
            docs.append(Document(page_content=rec["text"], metadata=rec["metadata"]))
    return tuple(docs)


@lru_cache(maxsize=4)
def _bm25(index_name: str):
    from langchain_community.retrievers import BM25Retriever
    return BM25Retriever.from_documents(list(_chunk_docs(index_name)))


@lru_cache(maxsize=1)
def _reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(RERANKER_MODEL)


def retrieve(question: str, cfg: RAGConfig) -> list[Document]:
    vs = _vectorstore(cfg.index_name)
    n = cfg.fetch_k if cfg.use_reranker else cfg.top_k

    if cfg.retriever == "hybrid":
        # Reciprocal Rank Fusion of BM25 and dense rankings, equal weights
        # (LangChain 1.x moved EnsembleRetriever to the transitional
        # langchain_classic package, so the fusion is implemented here).
        bm25 = _bm25(cfg.index_name)
        bm25.k = n
        dense_docs = vs.similarity_search(question, k=n)
        rrf: dict[tuple, list] = {}
        for ranking in (bm25.invoke(question), dense_docs):
            for rank, d in enumerate(ranking):
                key = (d.metadata["tm"], d.metadata["page"], d.page_content[:80])
                entry = rrf.setdefault(key, [0.0, d])
                entry[0] += 0.5 / (60 + rank)  # k=60, standard RRF constant
        docs = [d for _, d in sorted(rrf.values(), key=lambda e: e[0], reverse=True)][:n]
    else:
        docs = vs.similarity_search(question, k=n)

    if cfg.use_reranker:
        scores = _reranker().predict([(question, d.page_content) for d in docs])
        docs = [d for _, d in sorted(zip(scores, docs),
                                     key=lambda p: p[0], reverse=True)][: cfg.top_k]
    return docs[: cfg.top_k]


def _source_header(m: dict) -> str:
    brand = m.get("brand", "")
    label = f"{brand} {m['manual']}" if brand else m["manual"]
    return f"({label}, p.{m['page']})"


def _format_context(docs: list[Document]) -> tuple[str, list[dict]]:
    blocks, sources = [], []
    for i, d in enumerate(docs, 1):
        m = d.metadata
        blocks.append(f"[{i}] {_source_header(m)}\n{d.page_content}")
        sources.append({
            "n": i, "manual": m["manual"], "tm": m["tm"],
            "brand": m.get("brand", ""), "page": m["page"],
            "snippet": d.page_content[:200],
        })
    return "\n\n".join(blocks), sources


def _llm(streaming: bool = False):
    from langchain_anthropic import ChatAnthropic
    return ChatAnthropic(model=GENERATION_MODEL, max_tokens=1024,
                         temperature=0, streaming=streaming)


def _messages(question: str, context: str) -> list[tuple[str, str]]:
    return [
        ("system", SYSTEM_PROMPT),
        ("human", f"Context excerpts:\n\n{context}\n\nQuestion: {question}"),
    ]


def answer(question: str, cfg: RAGConfig | str = "baseline") -> dict:
    """Retrieve, generate, and return {answer, contexts, sources}."""
    if isinstance(cfg, str):
        cfg = CONFIGS[cfg]
    docs = retrieve(question, cfg)
    context, sources = _format_context(docs)
    resp = _llm().invoke(_messages(question, context))
    return {
        "answer": resp.content,
        # contexts as the generator saw them (source header included) — the
        # Ragas judge must see the same evidence, or it correctly rejects
        # claims like "the Cascadia..." that only the header attributes.
        "contexts": [
            f"{_source_header(d.metadata)} {d.page_content}" for d in docs
        ],
        "sources": sources,
    }


def stream_answer(question: str, cfg: RAGConfig | str = "baseline"):
    """Yield ("sources", list) once, then ("delta", str) chunks for the UI."""
    if isinstance(cfg, str):
        cfg = CONFIGS[cfg]
    docs = retrieve(question, cfg)
    context, sources = _format_context(docs)
    yield "sources", sources
    for chunk in _llm(streaming=True).stream(_messages(question, context)):
        if chunk.content:
            text = chunk.content if isinstance(chunk.content, str) else "".join(
                b.get("text", "") for b in chunk.content if isinstance(b, dict))
            if text:
                yield "delta", text


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "What is the tire pressure for the HMMWV?"
    out = answer(q)
    print(out["answer"])
    print("\nSources:")
    for s in out["sources"]:
        print(f"  [{s['n']}] {s['manual']} — p.{s['page']}")
