"""Ingest the manual corpus: PDF -> page-wise chunks -> local embeddings -> FAISS.

Chunking is per-page so every chunk carries an honest page citation (a chunk never
spans a page boundary). Chunk documents are also persisted to chunks.jsonl per index
so BM25 (hybrid config) can be rebuilt without re-parsing PDFs.

Two entry points:
    python -m src.ingest              build indexes for every distinct chunking
    add_manual(path, brand, title)    append one PDF to ALL existing indexes
                                      (used by the app's "Add a manual" upload)
"""
from __future__ import annotations

import argparse
import json
import os
import time

# faiss-cpu and torch each bundle OpenMP on macOS; see src/rag.py.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import fitz  # PyMuPDF: unlike pypdf, reconstructs kerned text correctly
from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.config import (CONFIGS, EMBEDDING_MODEL, MANIFEST, PDF_DIR, RAGConfig,
                        load_manifest)


def _pdf_pages(path, manual_id: str, brand: str, title: str) -> tuple[list[Document], int]:
    """One Document per page with text; returns (pages, low_text_page_count)."""
    doc = fitz.open(path)
    pages, low = [], 0
    for i, page in enumerate(doc):
        text = page.get_text().strip()
        if len(text) < 50:  # image-only / near-empty page
            low += 1
            continue
        pages.append(Document(
            page_content=text,
            metadata={"manual": title, "tm": manual_id, "brand": brand, "page": i + 1},
        ))
    doc.close()
    return pages, low


def load_pages() -> list[Document]:
    pages: list[Document] = []
    low_total = total = 0
    for m in load_manifest():
        p, low = _pdf_pages(PDF_DIR / m["file"], m["id"], m["brand"], m["title"])
        pages.extend(p)
        low_total += low
        total += len(p) + low
        print(f"  {m['id']}: {len(p) + low} pages")
    print(f"Loaded {len(pages)}/{total} pages with text ({low_total} low-text skipped)")
    if pages and len(pages) < 0.7 * total:
        raise SystemExit("More than 30% of pages lack a text layer — check the PDFs.")
    return pages


def chunk_pages(pages: list[Document], cfg: RAGConfig) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap
    )
    return splitter.split_documents(pages)  # per-page: metadata survives intact


def _embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        encode_kwargs={"normalize_embeddings": True, "batch_size": 64},
    )


def _append_chunks_jsonl(cfg: RAGConfig, chunks: list[Document], mode: str) -> None:
    with open(cfg.index_path / "chunks.jsonl", mode) as f:
        for c in chunks:
            f.write(json.dumps({"text": c.page_content, "metadata": c.metadata}) + "\n")


def build_index(cfg: RAGConfig, pages: list[Document]) -> None:
    from langchain_community.vectorstores import FAISS
    chunks = chunk_pages(pages, cfg)
    print(f"[{cfg.index_name}] embedding {len(chunks)} chunks "
          f"(size={cfg.chunk_size}, overlap={cfg.chunk_overlap})")
    t0 = time.time()
    vs = FAISS.from_documents(chunks, _embeddings())
    cfg.index_path.mkdir(parents=True, exist_ok=True)
    vs.save_local(str(cfg.index_path))
    _append_chunks_jsonl(cfg, chunks, "w")
    print(f"[{cfg.index_name}] saved to {cfg.index_path} in {time.time() - t0:.0f}s")


def add_manual(pdf_path: str, brand: str, title: str) -> dict:
    """Append one uploaded PDF to the manifest and to every built index.

    Returns a stats dict for the UI. Raises ValueError on unusable PDFs.
    """
    import re
    import shutil

    from langchain_community.vectorstores import FAISS

    manual_id = re.sub(r"[^a-z0-9]+", "-", f"{brand}-{title}".lower()).strip("-")
    if any(m["id"] == manual_id for m in load_manifest()):
        raise ValueError(f"A manual named “{title}” for {brand} is already indexed.")

    pages, low = _pdf_pages(pdf_path, manual_id, brand, title)
    if not pages:
        raise ValueError("No selectable text found in this PDF — it looks like a "
                         "scan without OCR. Run OCR first, then re-upload.")
    if len(pages) < 0.5 * (len(pages) + low):
        raise ValueError("More than half the pages have no text layer — the index "
                         "would miss most of this manual. Run OCR first.")

    dest = PDF_DIR / f"{manual_id}.pdf"
    shutil.copyfile(pdf_path, dest)

    emb = _embeddings()
    per_index = {}
    for cfg in {c.index_name: c for c in CONFIGS.values()}.values():
        if not (cfg.index_path / "index.faiss").exists():
            continue
        chunks = chunk_pages(pages, cfg)
        vs = FAISS.load_local(str(cfg.index_path), emb,
                              allow_dangerous_deserialization=True)
        vs.add_documents(chunks)
        vs.save_local(str(cfg.index_path))
        _append_chunks_jsonl(cfg, chunks, "a")
        per_index[cfg.index_name] = len(chunks)

    data = {"manuals": load_manifest()}
    data["manuals"].append({
        "id": manual_id, "brand": brand, "title": title, "file": dest.name,
        "source_url": "user-upload", "license": "Uploaded by user; not redistributed.",
    })
    with open(MANIFEST, "w") as f:
        json.dump(data, f, indent=2)

    return {"id": manual_id, "pages": len(pages), "chunks": per_index}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=list(CONFIGS), default=None)
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
