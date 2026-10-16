import json
from pathlib import Path

from inbox_triage.cli import main
from inbox_triage.evals import evaluate
from inbox_triage.llm import RuleLLM
from inbox_triage.models import Classification, Email
from inbox_triage.pipeline import DEFAULT_CONFIG, decide, load_emails, triage, write_queue

SAMPLES = Path(__file__).parent / "samples"


def test_loads_eml_folder():
    emails = load_emails(SAMPLES)
    assert len(emails) == 5
    assert all(e.subject and e.sender for e in emails)


def test_rule_llm_classifies_samples_sensibly():
    emails = {e.id: e for e in load_emails(SAMPLES)}
    llm = RuleLLM()
    assert llm.classify(emails["01-quote"], DEFAULT_CONFIG["categories"]).category == "sales_inquiry"
    assert llm.classify(emails["02-bug"], DEFAULT_CONFIG["categories"]).category == "support"
    assert llm.classify(emails["03-invoice"], DEFAULT_CONFIG["categories"]).category == "billing"


def test_low_confidence_routes_to_human():
    action, route = decide(Classification("sales_inquiry", 0.2), DEFAULT_CONFIG)
    assert action == "route" and route == DEFAULT_CONFIG["actions"]["other"]["route_to"]
    action, _ = decide(Classification("sales_inquiry", 0.9), DEFAULT_CONFIG)
    assert action == "draft"


def test_drafts_only_for_draft_actions_and_queue_files(tmp_path):
    results = triage(load_emails(SAMPLES), DEFAULT_CONFIG, RuleLLM())
    for r in results:
        assert (r.draft is not None) == (r.action == "draft")
        assert r.status == "pending"
    jsonl, md = write_queue(results, tmp_path)
    assert len(jsonl.read_text().splitlines()) == len(results)
    assert "# Review queue" in md.read_text()


def test_cli_run_and_approve(tmp_path):
    assert main(["--llm", "rule", "run", str(SAMPLES), "--out", str(tmp_path)]) == 0
    assert (tmp_path / "log.csv").exists()
    q = tmp_path / "queue.jsonl"
    first = json.loads(q.read_text().splitlines()[0])["email_id"]
    assert main(["approve", str(q), first, "approved"]) == 0
    assert json.loads(q.read_text().splitlines()[0])["status"] == "approved"
    assert main(["approve", str(q), "nope", "approved"]) == 1


def test_eval_reports_precision_recall():
    rep = evaluate(load_emails(SAMPLES), SAMPLES / "labels.csv", DEFAULT_CONFIG, RuleLLM())
    assert rep["n"] == 5
    assert 0 <= rep["accuracy"] <= 1
    assert "sales_inquiry" in rep["per_category"]


def test_email_text_includes_headers():
    e = Email("x", "A <a@b.c>", "Hello", "body")
    assert e.text.startswith("From: A <a@b.c>\nSubject: Hello")
