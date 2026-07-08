"""Run the Ragas evaluation for one retrieval config and save the results.

For each question: retrieve + generate with src.rag under the named config, then
score with Ragas (faithfulness, answer relevancy, context precision, context
recall) using a judge model that is different from the generation model.

Outputs (evals/results/):
    {config}_per_question.csv   one row per question with all four metric scores
    {config}_summary.json       aggregate means + config + models + timestamp

Usage:
    python -m evals.run_ragas --config baseline
    python -m evals.run_ragas --config baseline --subset 10   # CI gate
"""
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

RESULTS_DIR = Path(__file__).resolve().parent / "results"
QUESTIONS_CSV = Path(__file__).resolve().parent / "questions.csv"
METRIC_COLS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def generate_answers(cfg_name: str, df: pd.DataFrame) -> list[dict]:
    from src.rag import answer
    samples = []
    for i, row in df.iterrows():
        t0 = time.time()
        out = answer(row["question"], cfg_name)
        samples.append({
            "user_input": row["question"],
            "response": out["answer"],
            "retrieved_contexts": out["contexts"],
            "reference": row["ground_truth"],
        })
        print(f"  [{i + 1}/{len(df)}] answered in {time.time() - t0:.1f}s")
    return samples


def _shim_legacy_langchain() -> None:
    """Ragas (<=0.4.3) imports ChatVertexAI from a langchain-community module that
    was removed in langchain-community 1.x. Ragas only uses it for an isinstance
    check, so an empty stub keeps the import path alive. Remove once ragas drops
    the legacy import (noted in README)."""
    import sys
    import types
    try:
        from langchain_community.chat_models.vertexai import ChatVertexAI  # noqa: F401
    except ModuleNotFoundError:
        stub = types.ModuleType("langchain_community.chat_models.vertexai")
        stub.ChatVertexAI = type("ChatVertexAI", (), {})
        sys.modules["langchain_community.chat_models.vertexai"] = stub


def score(samples: list[dict]):
    _shim_legacy_langchain()
    from langchain_anthropic import ChatAnthropic
    from langchain_huggingface import HuggingFaceEmbeddings
    from ragas import EvaluationDataset, RunConfig, evaluate
    from ragas.embeddings import LangchainEmbeddingsWrapper
    from ragas.llms import LangchainLLMWrapper
    from ragas.metrics import (answer_relevancy, context_precision,
                               context_recall, faithfulness)

    from src.config import JUDGE_MODEL

    judge = LangchainLLMWrapper(ChatAnthropic(
        model=JUDGE_MODEL, temperature=0, max_tokens=4096, max_retries=5))
    emb = LangchainEmbeddingsWrapper(HuggingFaceEmbeddings(
        model_name="BAAI/bge-small-en-v1.5",
        encode_kwargs={"normalize_embeddings": True}))

    return evaluate(
        dataset=EvaluationDataset.from_list(samples),
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge, embeddings=emb,
        run_config=RunConfig(max_workers=4, timeout=180),
    )


def main() -> None:
    from src.config import CONFIGS, GENERATION_MODEL, JUDGE_MODEL

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", choices=list(CONFIGS), required=True)
    ap.add_argument("--subset", type=int, default=None,
                    help="Evaluate only the first N questions (CI gate)")
    args = ap.parse_args()
    cfg = CONFIGS[args.config]

    df = pd.read_csv(QUESTIONS_CSV)
    if args.subset:
        df = df.head(args.subset)
    print(f"Config '{cfg.name}' ({cfg.description}) — {len(df)} questions")

    samples = generate_answers(cfg.name, df)
    result = score(samples)
    per_q = result.to_pandas()

    RESULTS_DIR.mkdir(exist_ok=True)
    suffix = f"_subset{args.subset}" if args.subset else ""
    per_q.to_csv(RESULTS_DIR / f"{cfg.name}{suffix}_per_question.csv", index=False)

    summary = {
        "config": cfg.name,
        "description": cfg.description,
        "questions": len(df),
        "generation_model": GENERATION_MODEL,
        "judge_model": JUDGE_MODEL,
        "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metrics": {m: round(float(per_q[m].mean()), 4) for m in METRIC_COLS},
    }
    with open(RESULTS_DIR / f"{cfg.name}{suffix}_summary.json", "w") as f:
        json.dump(summary, f, indent=2)

    print(json.dumps(summary["metrics"], indent=2))


if __name__ == "__main__":
    main()
