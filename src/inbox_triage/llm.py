"""LLM providers behind one tiny interface so the pipeline is testable offline.

`AnthropicLLM` is used when ANTHROPIC_API_KEY is set and the `anthropic` extra is installed.
`RuleLLM` is a deterministic keyword fallback used for tests, demos and evals without a key.
"""

from __future__ import annotations

import json
import os
import re
from typing import Protocol

from .models import Classification, Email


class LLM(Protocol):
    def classify(self, email: Email, categories: dict[str, str]) -> Classification: ...
    def draft(self, email: Email, category: str, voice: str, examples: list[str]) -> str: ...


class RuleLLM:
    """Keyword scoring per category description; good enough to exercise every code path."""

    def classify(self, email: Email, categories: dict[str, str]) -> Classification:
        text = email.text.lower()
        best, best_score = "other", 0
        for name, desc in categories.items():
            words = {w for w in re.findall(r"[a-z]{4,}", desc.lower())}
            score = sum(1 for w in words if w in text)
            if score > best_score:
                best, best_score = name, score
        conf = min(0.95, 0.4 + 0.15 * best_score) if best_score else 0.3
        return Classification(best, conf, reason=f"matched {best_score} keywords" if best_score else "no keyword match")

    def draft(self, email: Email, category: str, voice: str, examples: list[str]) -> str:
        first = email.sender.split("<")[0].strip().split(" ")[0] or "there"
        return (f"Hi {first},\n\nThanks for your note about \"{email.subject}\". "
                f"[{category}] We'll follow up with details shortly.\n\n{voice.splitlines()[0] if voice else 'Best'}")


class AnthropicLLM:
    def __init__(self, model: str = "claude-sonnet-5-5") -> None:
        import anthropic  # optional dependency

        self.client = anthropic.Anthropic()
        self.model = model

    def _ask(self, system: str, user: str, max_tokens: int = 600) -> str:
        msg = self.client.messages.create(model=self.model, max_tokens=max_tokens, system=system,
                                          messages=[{"role": "user", "content": user}])
        return "".join(getattr(b, "text", "") for b in msg.content)

    def classify(self, email: Email, categories: dict[str, str]) -> Classification:
        system = ("You classify inbound business email. Reply with JSON only: "
                  '{"category": <one of the names>, "confidence": 0-1, "reason": <short>}. '
                  "Use 'other' when unsure.")
        cats = "\n".join(f"- {k}: {v}" for k, v in categories.items())
        raw = self._ask(system, f"Categories:\n{cats}\n\nEmail:\n{email.text}", max_tokens=200)
        try:
            d = json.loads(raw[raw.find("{"): raw.rfind("}") + 1])
            cat = d.get("category", "other")
            return Classification(cat if cat in categories or cat == "other" else "other",
                                  float(d.get("confidence", 0.5)), str(d.get("reason", "")))
        except Exception:  # noqa: BLE001
            return Classification("other", 0.3, "unparseable model output")

    def draft(self, email: Email, category: str, voice: str, examples: list[str]) -> str:
        system = ("You draft reply emails for a human to review before sending. Match the voice guide. "
                  "Never invent facts, prices, or commitments; leave [brackets] where the human must fill in. "
                  "Plain text, no subject line, under 150 words.")
        ex = "\n\n---\n".join(examples[:3])
        user = f"Voice guide:\n{voice}\n\nExamples of past replies:\n{ex}\n\nCategory: {category}\n\nEmail to answer:\n{email.text}"
        return self._ask(system, user).strip()


def get_llm(name: str | None = None) -> LLM:
    name = (name or os.environ.get("INBOX_TRIAGE_LLM") or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "rule")).lower()
    if name == "anthropic":
        return AnthropicLLM()
    return RuleLLM()
