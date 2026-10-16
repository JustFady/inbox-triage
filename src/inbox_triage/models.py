from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class Email:
    id: str
    sender: str
    subject: str
    body: str
    received: str = ""

    @property
    def text(self) -> str:
        return f"From: {self.sender}\nSubject: {self.subject}\n\n{self.body}".strip()


@dataclass
class Classification:
    category: str
    confidence: float
    reason: str = ""


@dataclass
class Triage:
    email_id: str
    sender: str
    subject: str
    category: str
    confidence: float
    reason: str
    action: str                 # "draft" | "route" | "ignore"
    draft: str | None = None
    route_to: str | None = None
    status: str = "pending"     # pending | approved | edited | rejected | sent
    created: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds"))

    def to_dict(self) -> dict:
        return asdict(self)
