# inbox-triage

Classify inbound email, draft replies in your voice, queue them for a human to approve, and log everything. The shape of an email automation that a small team can actually trust: nothing is sent without a person saying so, low-confidence items go to a human instead of being guessed, and you can measure accuracy on your own mail before turning it on.

```
$ inbox-triage run ./mail --out ./out
triaged 5 emails → {'draft': 3, 'route': 1, 'ignore': 1}; review out/review.md

$ inbox-triage eval ./mail ./labels.csv
evaluated 5 labeled emails · accuracy 100.0%

category               precision  recall    n
billing                     100%    100%    1
newsletter_or_spam          100%    100%    1
sales_inquiry               100%    100%    1
scheduling                  100%    100%    1
support                     100%    100%    1
```

## What it does

1. **Load** `.eml` files from a folder, one `.mbox`, or an IMAP mailbox read-only (`imap://you%40gmail.com@imap.gmail.com/INBOX` with `IMAP_PASSWORD` set to an app password; messages are peeked, never marked read, moved or deleted).
2. **Classify** each email into your categories (`triage.yaml`), with a confidence and a one-line reason.
3. **Decide**: per category, `draft` a reply, `route` to a mailbox, or `ignore`. Anything under `min_confidence` is routed to a human, never auto-handled.
4. **Draft** replies that match your voice guide and past examples; the model is told to leave `[brackets]` where a human must fill in facts, prices or dates.
5. **Queue** to `out/queue.jsonl` (machines) and `out/review.md` (you). Approve, edit or reject with `inbox-triage approve`.
6. **Log** every decision to `out/log.csv` so you can audit what happened and tune the categories.

Sending is deliberately out of scope here: wire the approved queue to your mail provider (Gmail API, Graph, SMTP) in your environment.

## Install

```bash
uv tool install "inbox-triage[anthropic]"     # or: pipx install "inbox-triage[anthropic]"
export ANTHROPIC_API_KEY=...                   # omit to use the offline rule-based model
cp triage.example.yaml triage.yaml             # edit categories, actions, voice, examples
```

## Configuration (`triage.yaml`)

```yaml
categories:
  sales_inquiry: someone asking about pricing, a quote, a demo, or whether you offer a service
  support: an existing customer reporting a problem, bug, outage, or asking how to do something
actions:
  sales_inquiry: {action: draft}
  billing: {action: route, route_to: billing@yourcompany.com}
  newsletter_or_spam: {action: ignore}
  other: {action: route, route_to: you@yourcompany.com}
min_confidence: 0.6
voice: |
  Warm, direct, two short paragraphs max. Sign off with "Best,\nFady".
examples:
  - |
    Hi Sam, thanks for reaching out ...
```

## Evaluate before you trust it

Label a sample of real emails (`email_id,category`) and run `inbox-triage eval`. Adjust category descriptions until precision on the categories that trigger drafts is where you want it; raise `min_confidence` to route more to humans.

## Models

- `anthropic`: Claude via the official SDK (default when `ANTHROPIC_API_KEY` is set).
- `rule`: a deterministic keyword model for tests, demos and CI; no network.

Add another provider by implementing two methods (`classify`, `draft`) in `llm.py`.

## Development

```bash
uv venv && uv pip install -e ".[dev]" && .venv/bin/python -m pytest -q
```

## License

MIT © Fady Youssef
