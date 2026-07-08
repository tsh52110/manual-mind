# PRD — ManualMind: RAG Chatbot over Public Equipment Service Manuals

**Author:** Taha Hussain · **Date:** 2026-07-08 · **Status:** v1 (portfolio/learning project)

## Problem

Technicians and owners of vehicles/equipment routinely dig through 100+ page service
manuals for one fact — a torque spec, a fluid capacity, a fault-code meaning. Keyword
search (Ctrl+F over a PDF) misses paraphrases ("how tight should the drain plug be"
never matches "torque: 30 ft-lb"). A RAG chatbot over the manuals answers in seconds —
**but only if every answer is grounded and cited**, because a hallucinated torque spec
is worse than no answer.

This project builds that chatbot end-to-end and — the differentiator — **measures**
each retrieval design choice with Ragas instead of asserting it.

## Users

- Primary (demo persona): equipment owner/technician asking maintenance questions.
- Actual: hiring managers/reviewers assessing whether I can ship and *evaluate* a
  retrieval system, not just wire one up.

## Success metrics

| Metric | Target | How measured |
|---|---|---|
| Faithfulness | ≥ 0.85 | Ragas over a 30-question eval set built from the indexed manuals |
| Context recall | Reported alongside (no gate) | Same run — read together with faithfulness: high faithfulness + low recall = "honest but incomplete" |
| Config study | 4 runs: baseline + 3 single-variable changes | Chunk size · cross-encoder reranker · hybrid BM25+dense. Per-metric deltas in one table (xlsx + README) |
| UX | Cited sources on every answer | Each answer shows manual name + page as source cards; sidebar lists indexed manuals |
| CI | Eval gate in GitHub Actions | Small fixed question subset; fails if faithfulness < 0.85 (manual dispatch — judge calls cost money) |

## Scope

**In:** 5–10 publicly downloadable manuals (source + license recorded per PDF);
ingestion (chunk/embed/FAISS); grounded QA with page-level citations; Ragas eval
(faithfulness, answer relevancy, context precision, context recall); before/after
config comparison; polished Streamlit chat UI; CI eval gate; public deploy.

**Out:** multi-tenant auth, PDF upload by end users, OCR of scanned manuals,
fine-tuning, conversation memory across sessions, non-English manuals.

## Architecture (v1)

PDFs → pypdf page-wise extract → RecursiveCharacterTextSplitter (per-page, so page
numbers survive) → local embeddings (BAAI/bge-small-en-v1.5, no API cost) → FAISS →
top-k retrieve (variants: dense / dense+reranker / hybrid BM25+dense) →
Claude (claude-haiku-4-5) generates a grounded, citing answer → Streamlit chat UI.
Ragas judge: claude-sonnet-5 via LangchainLLMWrapper; eval embeddings local.

## Key decisions

- **Local embeddings** (bge-small): Anthropic has no embeddings API; local models make
  ingestion free, deterministic, and deployable on a CPU Space.
- **Generation ≠ judge model**: haiku-4.5 answers, sonnet-5 judges — avoids
  self-preference bias and keeps the demo snappy.
- **Page-wise chunking**: chunks never cross page boundaries so every chunk carries an
  honest page citation.
- **One variable per config run** so metric deltas are attributable.

## Risks

| Risk | Mitigation |
|---|---|
| Scanned/image-only manual pages extract no text | Pick born-digital PDFs; assert extracted char count per page at ingest |
| Ragas judge variance run-to-run | Fixed question set, temperature 0, report per-metric aggregates from saved runs only |
| Judge API cost/time (30 q × 4 configs) | Small corpus, haiku generation, CI gate uses a 10-question subset on manual dispatch |
| Base fork is stale (LangChain 0.2, Ragas 0.1.9, OpenAI-only, re-embeds per message) | Rebuilt as `src/` modules on current pins; every fix noted in README §Fork provenance |
| Manual copyright | Prefer public-domain (US gov) manuals; record source + license per file in `data/SOURCES.md` |
