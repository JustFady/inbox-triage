from pathlib import Path

import pytest

from inbox_triage.imap_source import fetch_emails, parse_url

SAMPLES = Path(__file__).parent / "samples"


class FakeIMAP:
    """Minimal imaplib stand-in: serves the sample .eml files as UNSEEN messages."""

    def __init__(self):
        self.calls = []
        self.raw = {str(i + 1).encode(): p.read_bytes() for i, p in enumerate(sorted(SAMPLES.glob("*.eml")))}

    def login(self, user, password):
        self.calls.append(("login", user, password))
        return "OK", [b"ok"]

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [b"5"]

    def search(self, charset, *criteria):
        self.calls.append(("search", criteria))
        return "OK", [b" ".join(self.raw)]

    def fetch(self, message_set, message_parts):
        self.calls.append(("fetch", message_set, message_parts))
        return "OK", [(b"1 (BODY[] {n})", self.raw[message_set.encode()]), b")"]

    def logout(self):
        self.calls.append(("logout",))
        return "BYE", [b"bye"]


def test_parse_url():
    cfg = parse_url("imap://fady%40example.com@imap.gmail.com:993/INBOX")
    assert cfg == {"user": "fady@example.com", "host": "imap.gmail.com", "port": 993, "mailbox": "INBOX"}
    assert parse_url("imap://u@h")["mailbox"] == "INBOX" and parse_url("imap://u@h")["port"] == 993
    with pytest.raises(ValueError):
        parse_url("https://u@h/INBOX")


def test_fetch_is_readonly_and_peeks(monkeypatch):
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)
    fake = FakeIMAP()
    emails = fetch_emails("imap://u%40x.com@imap.x.com/INBOX", password="app-pass", client=fake)
    assert len(emails) == 5 and emails[0].id.startswith("imap-")
    assert ("select", "INBOX", True) in fake.calls
    assert all(c[2] == "(BODY.PEEK[])" for c in fake.calls if c[0] == "fetch")
    assert any(c[0] == "search" and c[1] == ("UNSEEN",) for c in fake.calls)
    assert fake.calls[-1] == ("logout",)


def test_fetch_requires_password(monkeypatch):
    monkeypatch.delenv("IMAP_PASSWORD", raising=False)
    with pytest.raises(ValueError):
        fetch_emails("imap://u@h/INBOX", client=FakeIMAP())


def test_limit_takes_newest(monkeypatch):
    fake = FakeIMAP()
    emails = fetch_emails("imap://u@h/INBOX", password="p", limit=2, client=fake)
    assert [e.id for e in emails] == ["imap-4", "imap-5"]
