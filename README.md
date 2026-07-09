# ManualMind — RAG over Daimler Truck Brand Manuals, Measured with Ragas

A chatbot that answers questions **only** from official Daimler Truck brand
manuals — **Freightliner** (Cascadia, eCascadia), **Western Star** (47X/49X),
**FUSO** (FE/FG), and **Mercedes-Benz Trucks** (Actros/Arocs) — cites the
**manual and page** for every claim, lets you **add new manuals from the UI**,
and backs every retrieval design choice with **measured Ragas metrics**,
including a before/after study that changes one variable at a time.

> Personal learning/portfolio project. Not affiliated with or endorsed by
> Daimler Truck AG or Daimler Truck North America.

<!-- SCREENSHOT -->

## What it does

- **Grounded chat** — Claude (haiku-4.5) answers strictly from retrieved manual
  excerpts; each claim carries an inline `[n]` citation that maps to a source
  card (brand + manual + page). Off-corpus questions get an honest refusal.
- **Add a manual from the UI** — upload any text-layer PDF, name it, pick the
  brand (including Mercedes-Benz Buses), and it is chunked, embedded, and
  searchable immediately; scanned PDFs without OCR are rejected with a clear
  message instead of silently indexing nothing.
- **Plain-language search settings** — the retrieval configs live behind an
  "Advanced" expander as *Best quality (recommended)* / *Fastest* / *Exact
  words + meaning*; the jargon (cross-encoders, RRF, k) stays here in the README.
- **Measured, not asserted** — a 28-question eval set with ground truths taken
  from the manuals' own pages, scored with Ragas on faithfulness, answer
  relevancy, context precision, and context recall.

## Results (before/after config study)

<!-- RESULTS -->

## Corpus & licensing

Seven official manuals (≈1,900 pages) across four Daimler Truck brands, each
publicly distributed by its manufacturer (DTNA service literature portal,
mitfuso.com, a public FCC filing). They are **© Daimler Truck — publicly
downloadable but *not* public domain — so this repo does not redistribute
them**: PDFs and index text are gitignored, and per-manual source URLs and
copyright notes live in [data/manuals.json](data/manuals.json). After cloning:

```bash
python -m scripts.fetch_manuals   # downloads from the official sources
python -m src.ingest              # builds the FAISS indexes locally
```

(The project previously ran on public-domain US Army technical manuals; that
corpus's sources and its full Ragas study are archived under
[docs/ARMY_CORPUS_SOURCES.md](docs/ARMY_CORPUS_SOURCES.md) and
`evals/results/archive-army-corpus/`.)

## Architecture

```
data/daimler (7 manuals, ~1,900 pages; fetched, not committed)
  └─ src/ingest.py    PyMuPDF page-wise extract → per-page chunks (citations
                      never cross pages) → bge-small (local) → FAISS
                      add_manual(): append an uploaded PDF to every index
  └─ src/rag.py       retrieve (dense | +reranker | hybrid RRF) → Claude answers
                      with forced inline [n] citations
  └─ evals/           questions.csv (28 q) → run_ragas.py (judge: sonnet-5)
                      → results/*.json|csv → compare.py → comparison.xlsx/md
  └─ app.py           Streamlit chat UI (streaming, brand-grouped sidebar,
                      source cards, uploads, plain-language search settings)
```

**Model split:** generation is `claude-haiku-4-5` (fast, cheap), the Ragas judge
is `claude-sonnet-5` (stronger, and a different model avoids self-preference
bias). Embeddings are local — no embedding API cost.

## Run it

```bash
git clone https://github.com/tsh52110/manual-mind && cd manual-mind
uv venv --python 3.11 .venv && uv pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

python -m scripts.fetch_manuals
python -m src.ingest

.venv/bin/streamlit run app.py
```

Evaluate a config and rebuild the comparison table:

```bash
.venv/bin/python -m evals.run_ragas --config reranker
.venv/bin/python -m evals.compare
```

## Eval methodology

- 28 questions across all seven manuals (`evals/questions.csv`); each
  `ground_truth` was written from the manual's own text, page-verified.
- One Ragas run per config; per-question scores and aggregates are saved in
  `evals/results/` — every number in the table above comes from a saved run.
- **Read faithfulness and context recall together**: faithfulness measures
  whether the answer sticks to the retrieved excerpts; recall measures whether
  the right excerpts were retrieved at all.
- CI: `.github/workflows/eval-gate.yml` fetches the corpus, builds the baseline
  index, runs a fixed 10-question subset, and fails below a 0.85 faithfulness
  floor (manual dispatch + PRs touching `src/` — judge calls cost real money).

**Two bugs this eval caught in earlier iterations** (both "before" run sets
archived in `evals/results/archive-*/` with explanations):

1. **Corpus extraction** — pypdf emitted kerning-broken text ("`15 0
   horsepower`") on spec tables; answers looked right but the judge correctly
   scored them unsupported. Fixed by switching extraction to PyMuPDF.
2. **Eval harness** — `retrieved_contexts` lacked the source headers the
   generator sees, so the judge rejected claims naming the vehicle
   (faithfulness 0.0 with recall 1.0 on correct answers). Contexts now match
   what the generator saw.

## Fork provenance & fixes

Forked from [RitikaVerma7/Chatbot-RAG_with_Evaluation](https://github.com/RitikaVerma7/Chatbot-RAG_with_Evaluation)
(FAISS + LangChain + Ragas + Streamlit over an insurance policy PDF). Kept: the
pipeline shape (PDF → chunk → FAISS → retrieve → answer → Ragas) and its
chunk 300/100 setting as the `small-chunks` study arm. Fixed/replaced:

- Stale pins (LangChain 0.2.x, Ragas 0.1.9) → current LangChain 1.x / Ragas 0.4.
- Ragas legacy `ChatVertexAI` import crash → shimmed in `evals/run_ragas.py`.
- Claude 5 judge rejects `temperature` → wrapper's `bypass_temperature`.
- Re-embedding the whole corpus on every chat message → indexes built once,
  loaded and cached at startup, appended to on upload.
- "Source: Policy document" string citations → per-chunk brand/manual/page
  metadata citations rendered as source cards.
- OpenAI-only → Anthropic + local embeddings.
- Original notebooks and app remain in `Code/` and `Streamlit/`; upstream
  README preserved at `docs/UPSTREAM_README.md`.

## Deploy

Deployment needs a corpus build (the manuals aren't in the repo): point
Streamlit Community Cloud or an HF Space (Streamlit SDK) at this repo, set the
`ANTHROPIC_API_KEY` secret, and run `python -m scripts.fetch_manuals &&
python -m src.ingest` once in the environment (or bake it into the Space's
startup). <!-- LIVE-LINK -->
