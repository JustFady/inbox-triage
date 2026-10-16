"""Pull messages from an IMAP mailbox (Gmail/Outlook/Fastmail with an app password).

Read-only: we fetch with BODY.PEEK so nothing is marked as read, and we never move or delete.
Settings come from a URL like imap://user@example.com@imap.gmail.com:993/INBOX plus the
IMAP_PASSWORD environment variable.
"""

from __future__ import annotations

import email as email_lib
import imaplib
import os
from email import policy
from typing import Protocol
from urllib.parse import unquote, urlparse

from .models import Email
from .pipeline import _from_message


class IMAPLike(Protocol):
    def login(self, user: str, password: str): ...
    def select(self, mailbox: str, readonly: bool = False): ...
    def search(self, charset, *criteria): ...
    def fetch(self, message_set: str, message_parts: str): ...
    def logout(self): ...


def parse_url(url: str) -> dict:
    """imap://user%40example.com@imap.gmail.com:993/INBOX → {user, host, port, mailbox}."""
    u = urlparse(url)
    if u.scheme not in ("imap", "imaps") or not u.hostname or not u.username:
        raise ValueError("expected imap://USER@HOST[:PORT]/MAILBOX (URL-encode @ in the user as %40)")
    return {"user": unquote(u.username), "host": u.hostname, "port": u.port or 993,
            "mailbox": (u.path or "/INBOX").lstrip("/") or "INBOX"}


def fetch_emails(url: str, password: str | None = None, limit: int = 50, unseen_only: bool = True,
                 client: IMAPLike | None = None) -> list[Email]:
    cfg = parse_url(url)
    password = password or os.environ.get("IMAP_PASSWORD")
    if not password:
        raise ValueError("set IMAP_PASSWORD (use an app password, never your main password)")
    conn = client or imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    try:
        conn.login(cfg["user"], password)
        conn.select(cfg["mailbox"], readonly=True)
        status, data = conn.search(None, "UNSEEN" if unseen_only else "ALL")
        if status != "OK" or not data:
            raise RuntimeError(f"IMAP search failed: {status}")
        first = data[0] or b""
        ids = first.split()[-limit:] if first else []
        out: list[Email] = []
        for uid in ids:
            status, parts = conn.fetch(uid.decode() if isinstance(uid, bytes) else uid, "(BODY.PEEK[])")
            if status != "OK" or not parts:
                continue
            raw = next((p[1] for p in (parts or []) if isinstance(p, tuple) and len(p) > 1), None)
            if raw is None:
                continue
            msg = email_lib.message_from_bytes(raw, policy=policy.default)
            out.append(_from_message(msg, f"imap-{uid.decode() if isinstance(uid, bytes) else uid}"))
        return out
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
