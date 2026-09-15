"""Reporting keeps new evaluation dimensions and every turn visible."""

import copy
from redteam import report


def evidence(mode="unguarded"):
    score = {"verdict": "FAIL", "security_verdict": "FAIL",
             "utility_verdict": "NOT_APPLICABLE", "execution_status": "ok",
             "judge_status": "disabled", "reasoning": "Earlier disclosure detected"}
    return {
        "id": "multi-turn", "family": "crescendo", "mode": mode,
        "model": "offline-model", "schema_version": 2, "expected": "refuse",
        "timestamp": "2026-09-15T16:00:00+00:00", "turns": ["start", "finish"],
        "response": "A clean final refusal", "score_config": {"use_judge": False},
        "suite_fingerprint": "suite", "code_fingerprint": "code", **score,
        "turn_results": [
            {"turn_index": 1, "prompt": "start", "response": "EARLY_DISCLOSURE <script>bad()</script>",
             "score": score, "execution_status": "ok", "tool_trace": [], "guard_trace": []},
            {"turn_index": 2, "prompt": "finish", "response": "A clean final refusal",
             "score": {**score, "verdict": "PASS", "security_verdict": "PASS"},
             "execution_status": "ok", "tool_trace": [], "guard_trace": []},
        ],
    }


def test_report_exposes_early_turn_response_and_score_safely():
    rows = {"unguarded": [evidence()]}
    view = report.summarize(rows)
    assert view["modes"]["unguarded"]["complete_turn_records"] == 1
    for output in (report.build(rows), report.build_html(rows)):
        assert "EARLY_DISCLOSURE" in output.replace("\\_", "_")
        assert "&lt;script&gt;" in output
        assert "<script>bad()" not in output
        assert "Turn 1" in output and "Turn 2" in output
        assert "Earlier disclosure detected" in output


def test_pairing_excludes_schema_settings_and_code_changes():
    original = evidence()
    for field, changed in (("schema_version", 1), ("score_config", {"use_judge": True}),
                           ("code_fingerprint", "new-code"), ("suite_fingerprint", "new-suite")):
        other = evidence("guarded")
        other[field] = changed
        assert report.summarize({"unguarded": [original], "guarded": [other]})["paired_ids"] == []
    assert report.summarize({"unguarded": [original], "guarded": [evidence("guarded")]})["paired_ids"] == ["multi-turn"]


def test_legacy_pass_does_not_become_independent_utility_pass():
    legacy = {"id": "old", "family": "benign", "verdict": "PASS"}
    measured = {**evidence(), "id": "new", "family": "benign", "verdict": "WARN",
                "utility_verdict": "FAIL", "utility_reason": "Missing expected public fact"}
    view = report.summarize({"unguarded": [legacy, measured]})
    assert view["modes"]["unguarded"]["utility_counts"] == {"UNASSESSED": 1, "FAIL": 1}
    assert "Missing expected public fact" in report.utility_caveat(measured)


def test_failure_and_execution_error_remain_visible_together():
    row = evidence()
    row["execution_status"] = "error"
    view = report.summarize({"unguarded": [row]})
    assert view["modes"]["unguarded"]["execution_errors"] == 1
    assert view["modes"]["unguarded"]["attack_counts"] == {"FAIL": 1}
    assert "Execution: error" in report.build_html({"unguarded": [row]})


def test_partial_turn_records_do_not_claim_complete_evidence():
    row = copy.deepcopy(evidence())
    row["turn_results"].pop()
    view = report.summarize({"unguarded": [row]})
    assert view["modes"]["unguarded"]["complete_turn_records"] == 0
    assert any("lack complete per-turn" in text for text in view["warnings"])


def test_recorded_configuration_is_visible_and_deduplicated():
    row = evidence()
    row["score_config"] = {"judge_prompt_version": "security-only-v2.1<script>"}
    data = {"unguarded": [row, copy.deepcopy(row)]}
    assert len(report.summarize(data)["modes"]["unguarded"]["evaluation_configs"]) == 1
    for output in (report.build(data), report.build_html(data)):
        assert "security-only-v2.1&lt;script&gt;" in output.replace("\\", "")
        assert "security-only-v2.1<script>" not in output
