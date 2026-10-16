"""The approve-before-send pipeline: load → classify → decide → draft → queue → log."""

from __future__ import annotations

import csv
import email as email_lib
import json
from email import policy
from pathlib import Path

import yaml

from .llm import LLM, get_llm
from .models import Classification, Email, Triage

DEFAULT_CONFIG = {
    "categories": {
        "sales_inquiry": "someone asking about pricing, a quote, a demo, or whether you offer a service",
        "support": "an existing customer reporting a problem, bug, outage, or asking how to do something",
        "billing": "invoices, payments, refunds, receipts, card or subscription questions",
        "scheduling": "booking, rescheduling, or confirming a meeting or call",
        "newsletter_or_spam": "marketing, newsletters, cold outreach, notifications nobody needs to answer",
    },
    "actions": {
        "sales_inquiry": {"action": "draft"},
        "support": {"action": "draft"},
        "billing": {"action": "route", "route_to": "billing@yourcompany.com"},
        "scheduling": {"action": "draft"},
        "newsletter_or_spam": {"action": "ignore"},
        "other": {"action": "route", "route_to": "you@yourcompany.com"},
    },
    "min_confidence": 0.6,
    "voice": "Warm, direct, two short paragraphs max. Sign off with 'Best,\\nFady'.",
    "examples": [],
}


def load_config(path: Path | None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    if path and path.exists():
        cfg.update(yaml.safe_load(path.read_text()) or {})
    return cfg


def load_emails(source: Path) -> list[Email]:
    """Read .eml files from a directory (or one .eml / .mbox file)."""
    paths = sorted(source.glob("*.eml")) if source.is_dir() else [source]
    out: list[Email] = []
    for p in paths:
        if p.suffix == ".mbox":
            import mailbox

            for i, m in enumerate(mailbox.mbox(str(p))):
                out.append(_from_message(m, f"{p.stem}-{i}"))
            continue
        msg = email_lib.message_from_bytes(p.read_bytes(), policy=policy.default)
        out.append(_from_message(msg, p.stem))
    return out


def _from_message(msg, id_: str) -> Email:
    body = ""
    if msg.is_multipart():
        part = msg.get_body(preferencelist=("plain", "html"))
        body = part.get_content() if part else ""
    else:
        body = msg.get_content() if hasattr(msg, "get_content") else str(msg.get_payload())
    return Email(id=id_, sender=str(msg.get("From", "")), subject=str(msg.get("Subject", "")),
                 body=str(body).strip(), received=str(msg.get("Date", "")))


def decide(cls: Classification, cfg: dict) -> tuple[str, str | None]:
    """Low confidence always routes to a human; otherwise follow the configured action."""
    if cls.confidence < cfg["min_confidence"]:
        return "route", cfg["actions"]["other"].get("route_to")
    rule = cfg["actions"].get(cls.category, cfg["actions"]["other"])
    return rule["action"], rule.get("route_to")


def triage(emails: list[Email], cfg: dict, llm: LLM | None = None) -> list[Triage]:
    model = llm or get_llm()
    results: list[Triage] = []
    for e in emails:
        cls = model.classify(e, cfg["categories"])
        action, route_to = decide(cls, cfg)
        draft = model.draft(e, cls.category, cfg["voice"], cfg.get("examples", [])) if action == "draft" else None
        results.append(Triage(e.id, e.sender, e.subject, cls.category, round(cls.confidence, 2), cls.reason,
                              action, draft, route_to))
    return results


def write_queue(results: list[Triage], out_dir: Path) -> tuple[Path, Path]:
    """JSONL for machines, Markdown for the human who approves."""
    out_dir.mkdir(parents=True, exist_ok=True)
    jsonl = out_dir / "queue.jsonl"
    with jsonl.open("w") as f:
        for r in results:
            f.write(json.dumps(r.to_dict()) + "\n")
    md = out_dir / "review.md"
    lines = ["# Review queue", "", "Edit the draft if needed, then mark `status: approved`, `edited`, or `rejected` in queue.jsonl.", ""]
    for r in results:
        lines += [f"## {r.email_id} · {r.category} ({r.confidence:.0%}) · {r.action}", f"**From:** {r.sender}  ", f"**Subject:** {r.subject}  ",
                  f"**Why:** {r.reason}" + (f"  \n**Route to:** {r.route_to}" if r.route_to else ""), ""]
        if r.draft:
            lines += ["```", r.draft, "```", ""]
    md.write_text("\n".join(lines))
    return jsonl, md


def append_log(results: list[Triage], log_path: Path) -> None:
    new = not log_path.exists()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["created", "email_id", "sender", "subject", "category", "confidence", "action", "status"])
        if new:
            w.writeheader()
        for r in results:
            w.writerow({k: getattr(r, k) for k in w.fieldnames})
