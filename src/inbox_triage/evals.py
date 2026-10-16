"""Offline evaluation: precision/recall per category against a labeled CSV (email_id,category)."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

from .llm import LLM
from .models import Email


def evaluate(emails: list[Email], labels_csv: Path, cfg: dict, llm: LLM) -> dict:
    gold = {row["email_id"]: row["category"] for row in csv.DictReader(labels_csv.open())}
    tp, fp, fn = Counter(), Counter(), Counter()
    confusion: dict[str, Counter] = defaultdict(Counter)
    n = 0
    for e in emails:
        if e.id not in gold:
            continue
        n += 1
        pred = llm.classify(e, cfg["categories"]).category
        truth = gold[e.id]
        confusion[truth][pred] += 1
        if pred == truth:
            tp[truth] += 1
        else:
            fp[pred] += 1
            fn[truth] += 1
    cats = sorted(set(gold.values()) | set(tp) | set(fp))
    per = {}
    for c in cats:
        p = tp[c] / (tp[c] + fp[c]) if tp[c] + fp[c] else 0.0
        r = tp[c] / (tp[c] + fn[c]) if tp[c] + fn[c] else 0.0
        per[c] = {"precision": round(p, 3), "recall": round(r, 3), "support": tp[c] + fn[c]}
    acc = sum(tp.values()) / n if n else 0.0
    return {"n": n, "accuracy": round(acc, 3), "per_category": per, "confusion": {k: dict(v) for k, v in confusion.items()}}


def format_report(rep: dict) -> str:
    lines = [f"evaluated {rep['n']} labeled emails · accuracy {rep['accuracy']:.1%}", "",
             f"{'category':22s} {'precision':>9s} {'recall':>7s} {'n':>4s}"]
    for c, m in rep["per_category"].items():
        lines.append(f"{c:22s} {m['precision']:>9.0%} {m['recall']:>7.0%} {m['support']:>4d}")
    return "\n".join(lines)
