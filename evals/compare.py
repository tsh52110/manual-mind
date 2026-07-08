"""Build the before/after comparison table from saved Ragas run summaries.

Reads evals/results/{config}_summary.json (full runs only, not CI subsets) and
writes comparison.xlsx (metrics + per-metric deltas vs baseline) plus
comparison.md for embedding in the README. Never invents numbers: a config with
no saved summary simply doesn't appear.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RESULTS = Path(__file__).resolve().parent / "results"
ORDER = ["baseline", "small-chunks", "reranker", "hybrid"]
METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def load() -> pd.DataFrame:
    rows = []
    for name in ORDER:
        f = RESULTS / f"{name}_summary.json"
        if not f.exists():
            continue
        s = json.loads(f.read_text())
        rows.append({"config": name, "change vs baseline": s["description"],
                     "n": s["questions"], **s["metrics"]})
    if not rows:
        raise SystemExit("No full-run summaries found in evals/results/")
    return pd.DataFrame(rows).set_index("config")


def main() -> None:
    df = load()
    if "baseline" in df.index:
        for m in METRICS:
            df[f"Δ {m}"] = (df[m] - df.loc["baseline", m]).round(4)

    xlsx = RESULTS / "comparison.xlsx"
    with pd.ExcelWriter(xlsx, engine="openpyxl") as xw:
        df.to_excel(xw, sheet_name="ragas_comparison")
    print(f"wrote {xlsx}")

    md_lines = ["| Config | " + " | ".join(METRICS) + " |",
                "|---|" + "---|" * len(METRICS)]
    for name, row in df.iterrows():
        cells = []
        for m in METRICS:
            delta = row.get(f"Δ {m}")
            base = f"{row[m]:.3f}"
            if name != "baseline" and pd.notna(delta):
                base += f" ({'+' if delta >= 0 else ''}{delta:.3f})"
            cells.append(base)
        md_lines.append(f"| {name} | " + " | ".join(cells) + " |")
    md = RESULTS / "comparison.md"
    md.write_text("\n".join(md_lines) + "\n")
    print(f"wrote {md}")
    print("\n".join(md_lines))


if __name__ == "__main__":
    main()
