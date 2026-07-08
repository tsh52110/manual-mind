"""Ingest the manual corpus: PDF -> page-wise chunks -> local embeddings -> FAISS.

Chunking is per-page so every chunk carries an honest page citation (a chunk never
spans a page boundary). Chunk documents are also persisted to chunks.jsonl per index
so BM25 (hybrid config) can be rebuilt without re-parsing PDFs.

Usage:
    python -m src.ingest                 # build indexes for all distinct chunkings
    python -m src.ingest --config baseline
"""
from __future__ import annotations

import argparse
import json
import time

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader

from src.config import CONFIGS, MANUALS, PDF_DIR, RAGConfig


def load_pages() -> list[Document]:
    """One Document per PDF page, with manual + page metadata."""
    pages: list[Document] = []
    low_text_pages = 0
    for stem, title in MANUALS.items():
        path = PDF_DIR / f"{stem}.pdf"
        reader = PdfReader(path)
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or "").strip()
            if len(text) < 50:  # image-only / near-empty page
                low_text_pages += 1
                continue
            pages.append(Document(
                page_content=text,
                metadata={"manual": title, "tm": stem, "page": i + 1},
            ))
        print(f"  {stem}: {len(reader.pages)} pages")
    total = len(pages) + low_text_pages
    print(f"Loaded {len(pages)}/{total} pages with text "
          f"({low_text_pages} low-text pages skipped)")
    if len(pages) < 0.7 * total:
        raise SystemExit("More than 30% of pages lack a text layer — check the PDFs.")
    return pages


def chunk_pages(pages: list[Document], cfg: RAGConfig) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap
    )
    chunks = splitter.split_documents(pages)  # per-page: metadata survives intact
    for j, c in enumerate(chunks):
        c.metadata["chunk_id"] = j
    return chunks


def build_index(cfg: RAGConfig, pages: list[Document]) -> None:
    from langchain_community.vectorstores import FAISS
    from langchain_huggingface import HuggingFaceEmbeddings

    chunks = chunk_pages(pages, cfg)
    print(f"[{cfg.index_name}] embedding {len(chunks)} chunks "
          f"(size={cfg.chunk_size}, overlap={cfg.chunk_overlap})")
    embeddings = HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        encode_kwargs={"normalize_embeddings": True, "batch_size": 64},
    )
    t0 = time.time()
    vs = FAISS.from_documents(chunks, embeddings)
    cfg.index_path.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(cfg.index_path))
    with open(cfg.index_path / "chunks.jsonl", "w") as f:
        for c in chunks:
            f.write(json.dumps({"text": c.page_content, "metadata": c.metadata}) + "\n")
    print(f"[{cfg.index_name}] saved to {cfg.index_path} in {time.time() - t0:.0f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=list(CONFIGS), default=None,
                    help="Build only this config's index (default: all distinct chunkings)")
    args = ap.parse_args()

    pages = load_pages()
    cfgs = [CONFIGS[args.config]] if args.config else list(CONFIGS.values())
    built: set[str] = set()
    for cfg in cfgs:
        if cfg.index_name in built or (
            args.config is None and (cfg.index_path / "index.faiss").exists()
        ):
            print(f"[{cfg.index_name}] already built — skipping")
            built.add(cfg.index_name)
            continue
        build_index(cfg, pages)
        built.add(cfg.index_name)


if __name__ == "__main__":
    main()
