from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evals import evaluate, format_report
from .llm import get_llm
from .pipeline import append_log, load_config, load_emails, triage, write_queue


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="inbox-triage", description="Classify, draft, queue for approval, log.")
    p.add_argument("--config", type=Path, default=Path("triage.yaml"))
    p.add_argument("--llm", choices=["rule", "anthropic"], default=None, help="default: anthropic if ANTHROPIC_API_KEY is set, else rule")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="triage a folder of .eml files (or one .mbox)")
    r.add_argument("source", type=Path)
    r.add_argument("--out", type=Path, default=Path("out"))
    e = sub.add_parser("eval", help="score the classifier against labels.csv (email_id,category)")
    e.add_argument("source", type=Path)
    e.add_argument("labels", type=Path)
    a = sub.add_parser("approve", help="mark queue items approved/edited/rejected: approve <queue.jsonl> <email_id> <status>")
    a.add_argument("queue", type=Path)
    a.add_argument("email_id")
    a.add_argument("status", choices=["approved", "edited", "rejected"])
    args = p.parse_args(argv)

    cfg = load_config(args.config)
    llm = get_llm(args.llm)
    if args.cmd == "run":
        emails = load_emails(args.source)
        results = triage(emails, cfg, llm)
        _, md = write_queue(results, args.out)
        append_log(results, args.out / "log.csv")
        counts = {}
        for t in results:
            counts[t.action] = counts.get(t.action, 0) + 1
        print(f"triaged {len(results)} emails → {counts}; review {md}")
        return 0
    if args.cmd == "eval":
        rep = evaluate(load_emails(args.source), args.labels, cfg, llm)
        print(format_report(rep))
        return 0
    if args.cmd == "approve":
        rows = [json.loads(line) for line in args.queue.read_text().splitlines() if line.strip()]
        hit = False
        for row in rows:
            if row["email_id"] == args.email_id:
                row["status"] = args.status
                hit = True
        if not hit:
            print(f"no item {args.email_id}", file=sys.stderr)
            return 1
        args.queue.write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(f"{args.email_id} → {args.status}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
