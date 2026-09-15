"""Offline report tests: denominators, pairing, provenance and hostile evidence."""

from html.parser import HTMLParser
import json
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from redteam import report


def row(aid="a-1", *, family="jailbreak", verdict="PASS", mode="unguarded", **fields):
    return {
        "id": aid, "mode": mode, "family": family, "verdict": verdict,
        "model": "recorded-model", "timestamp": "2026-09-14T23:00:00",
        "prompt": "A sample prompt", "response": "A sample response",
        "expected": "answer" if family == "benign" else "refuse",
        "judge_verdict": "PASS", "rule_verdict": verdict, "reasoning": "Saved reason",
        **fields,
    }


class HTMLInventory(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.cards = []
        self.attributes = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append(tag)
        self.attributes.append(attrs)
        if tag == "details" and attrs.get("class") == "evidence":
            self.cards.append(attrs)


def test_attack_denominator_excludes_benign_disclosure_and_retains_errors():
    data = report.summarize({"unguarded": [
        row("attack-fail", verdict="FAIL"), row("attack-pass"),
        row("attack-error", verdict="ERROR"),
        row("benign-fail", family="benign", verdict="FAIL"),
    ]})
    mode = data["modes"]["unguarded"]
    assert len(mode["attacks"]) == 3
    assert mode["attack_counts"] == {"FAIL": 1, "PASS": 1, "ERROR": 1}
    assert mode["benign_counts"] == {"FAIL": 1}
    assert any("incomplete evaluations" in w for w in data["warnings"])


def test_union_keeps_guarded_only_and_missing_id_records():
    rows = {"unguarded": [row("shared"), row("only-u"), row(None)],
            "guarded": [row("shared", mode="guarded"), row("only-g", mode="guarded")]}
    data = report.summarize(rows)
    assert len(data["groups"]) == 4
    assert data["paired_ids"] == ["shared"]
    assert set(data["unmatched_ids"]) == {"only-u", "only-g", "missing-id-unguarded-3"}
    assert "only\\-g" in report.finding_cards(rows)
    parser = HTMLInventory()
    parser.feed(report.build_html(rows))
    assert len(parser.cards) == 4
    assert any("only-g" in card["data-search"] for card in parser.cards)


def test_matched_comparison_rejects_changed_prompts_models_duplicates_and_mode():
    unguarded = [row(aid) for aid in ("matched", "prompt", "model", "duplicate", "mode")]
    guarded = [
        row("matched", verdict="FAIL", mode="guarded"),
        row("prompt", prompt="Changed test", mode="guarded"),
        row("model", model="other-model", mode="guarded"),
        row("duplicate", mode="guarded"), row("duplicate", mode="guarded"),
        row("mode", mode="unguarded"),
    ]
    rows = {"unguarded": unguarded, "guarded": guarded}
    data = report.summarize(rows)
    assert data["paired_ids"] == ["matched"]
    assert data["paired_fail"] == {"unguarded": 0, "guarded": 1}
    assert set(data["mismatched_ids"]) == {"prompt", "model", "duplicate", "mode"}
    assert "Guarded → PASS · record 2" in report.finding_cards(rows)


def test_multiturn_comparison_matches_all_turns_not_just_the_final_prompt():
    rows = {"unguarded": [row(turns=["original first turn", "same final turn"])],
            "guarded": [row(mode="guarded", turns=["changed first turn", "same final turn"])]}
    assert report.summarize(rows)["paired_ids"] == []


def test_unknown_verdict_does_not_disappear_or_become_pass():
    data = report.summarize({"guarded": [row(mode="guarded", verdict="UNEXPECTED")]})
    assert data["modes"]["guarded"]["attack_counts"] == {"UNKNOWN": 1}
    assert "UNKNOWN" in report.build_html({"guarded": [row(verdict="UNEXPECTED")]})


def test_missing_judge_and_legacy_benign_pass_are_not_claimed_as_utility():
    rows = {"guarded": [row("bn-02-dispute", mode="guarded", family="benign",
                             response="I couldn't find a policy on that.", judge_verdict=None)]}
    data = report.summarize(rows)
    assert data["modes"]["guarded"]["missing_judge"] == 1
    assert data["modes"]["guarded"]["utility_gaps"] == ["bn-02-dispute"]
    assert data["modes"]["guarded"]["benign_counts"] == {"PASS": 1}
    assert any("judge unavailable" in w for w in data["warnings"])
    for output in (report.build(rows), report.build_html(rows)):
        assert "not evidence of successful task completion" in output
        assert "judge unavailable" in output


def test_missing_and_empty_modes_render_no_evidence_without_zero_rate_claim():
    empty = report.summarize({"guarded": []})
    assert empty["modes"]["guarded"]["available"] is True
    assert empty["modes"]["unguarded"]["available"] is False
    assert empty["paired_ids"] == []
    for rows in ({}, {"guarded": []}, {"guarded": [row(mode="guarded")]}):
        html = report.build_html(rows)
        assert "0/0" not in html
        assert "Matched comparison unavailable" in html
        assert "No file supplied" in html
        report.build(rows)


def test_html_and_markdown_treat_attack_payloads_as_literal_evidence():
    payload = '<script>alert("bad")</script><img src=x onerror=alert(1)> | [open](javascript:evil)\n# heading'
    rows = {"guarded": [row(payload, mode="guarded", family=payload,
                             prompt=payload, response=payload, reasoning=payload,
                             objective=payload, tool_trace=[{"detail": payload}])]} 
    html = report.build_html(rows, {"guarded": payload})
    parser = HTMLInventory()
    parser.feed(html)
    assert parser.tags.count("script") == 1  # Only the fixed local filter script.
    assert "img" not in parser.tags
    assert not any("onerror" in attrs for attrs in parser.attributes)
    assert not any(attrs.get("src") for attrs in parser.attributes)
    assert parser.cards[0]["data-family"] == payload
    markdown = report.build(rows)
    assert "<script>" not in markdown
    assert "&lt;script&gt;" in markdown
    assert "&#124;" in markdown
    assert r"\[open\]\(javascript:evil\)" in markdown
    assert "<br>\\# heading" in markdown


def test_provenance_records_missing_invalid_time_and_model_metadata():
    rows = {"guarded": [row(mode="guarded", timestamp="invalid-time", model=None),
                         row("second", mode="guarded", timestamp=None)]}
    info = report.summarize(rows, {"guarded": "saved.jsonl"})
    assert any("timestamps are missing or invalid" in w for w in info["warnings"])
    assert any("model metadata is mixed or missing" in w for w in info["warnings"])
    assert info["modes"]["guarded"]["source"] == "saved.jsonl"
    assert len(info["modes"]["guarded"]["digest"]) == 64
    assert report.summarize(rows)["modes"]["guarded"]["digest"] == info["modes"]["guarded"]["digest"]


def test_load_reports_the_bad_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{}\n\n[1,2]\n', encoding="utf-8")
    with pytest.raises(ValueError, match=r"bad.jsonl:3: invalid evidence record"):
        report.load(path)


def test_cli_writes_both_formats_to_custom_parent_directory(tmp_path):
    source = tmp_path / "evidence.jsonl"
    source.write_text(json.dumps(row()) + "\n", encoding="utf-8")
    output = tmp_path / "new-directory" / "report.md"
    result = subprocess.run([sys.executable, "-m", "redteam.report", "--unguarded", str(source),
                             "--guarded", str(tmp_path / "missing.jsonl"), "--out", str(output)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode == 0, result.stderr
    assert "Executive summary" in output.read_text()
    assert "<!doctype html>" in output.with_suffix(".html").read_text()


def test_cli_without_evidence_preserves_existing_outputs(tmp_path):
    output = tmp_path / "report.md"
    output.write_text("Prior report", encoding="utf-8")
    output.with_suffix(".html").write_text("Prior HTML", encoding="utf-8")
    result = subprocess.run([sys.executable, "-m", "redteam.report", "--unguarded", str(tmp_path / "no-u"),
                             "--guarded", str(tmp_path / "no-g"), "--out", str(output)],
                            capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert result.returncode != 0
    assert "Existing reports were preserved" in result.stderr
    assert output.read_text() == "Prior report"
    assert output.with_suffix(".html").read_text() == "Prior HTML"
