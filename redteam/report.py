"""Build offline Markdown and HTML reports from saved red-team evidence.

Usage: python -m redteam.report [--unguarded X.jsonl --guarded Y.jsonl]
No model calls are made; stored verdicts are preserved, including their caveats.
"""

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import html
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS_DIR = os.path.join(HERE, "results")
DOCS = os.path.join(os.path.dirname(HERE), "docs")
MODES = ("unguarded", "guarded")
VERDICTS = ("FAIL", "WARN", "PASS", "ERROR", "UNKNOWN")
FAMILY_ORDER = [
    "jailbreak", "obfuscation", "sensitive_data_exposure", "prompt_injection",
    "red_team_recon", "crescendo", "pii_extraction", "social_engineering", "benign",
]
DEFENSE_MAP = {
    "jailbreak": ("Hardened prompt and input intent classifier", "System prompt / pre-model"),
    "obfuscation": ("Normalize and decode; screen patterns and intent", "Pre-model"),
    "sensitive_data_exposure": ("Knowledge allowlist, clause redaction and output scan", "Retrieval / post-model"),
    "prompt_injection": ("Separate retrieved data from instructions; scan output", "Context / post-model"),
    "red_team_recon": ("Limit exposed tool metadata; scan surface markers", "System prompt / post-model"),
    "crescendo": ("Track conversation risk and return a review reply", "Session"),
    "pii_extraction": ("Bind account access to the selected session user", "Backend / tool"),
    "social_engineering": ("Enforce tool authorization regardless of pretext", "Session / backend"),
    "benign": ("Preserve useful policy answers and own-account access", "Utility evaluation"),
}


def load(path):
    """Read a JSONL file, reporting malformed records with their line number."""
    rows = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("expected a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                raise ValueError(f"{path}:{number}: invalid evidence record: {exc}") from exc
            rows.append(row)
    return rows


def excerpt(value, n=280):
    value = str(value or "").replace("\n", " ").strip()
    return value[:n] + ("…" if len(value) > n else "")


def md_escape(value):
    """Render untrusted evidence as literal Markdown text, including table cells."""
    value = html.escape(str(value or ""), quote=False)
    value = re.sub(r"([\\`*_{}\[\]()#+.!~\-])", r"\\\1", value)
    return value.replace("|", "&#124;").replace("\r", "").replace("\n", "<br>")


def verdict(row):
    value = str(row.get("verdict", "UNKNOWN")).upper()
    return value if value in VERDICTS else "UNKNOWN"


def family(row):
    return str(row.get("family") or "unspecified")


def is_benign(row):
    return family(row) == "benign"


def families(rows_by_mode):
    found = {family(r) for mode in MODES for r in rows_by_mode.get(mode, [])}
    return sorted(found, key=lambda f: (FAMILY_ORDER.index(f) if f in FAMILY_ORDER else 99, f))


def prompt_turns(row):
    turns = row.get("turns")
    return [str(t) for t in turns] if isinstance(turns, list) and turns else [str(row.get("prompt") or "")]


def utility_caveat(row):
    """Flag a visible answer gap without silently replacing stored verdicts."""
    if is_benign(row) and row.get("utility_verdict") == "FAIL":
        return "Answer-quality check failed: " + str(row.get("utility_reason") or "Review the expected answer and response.")
    if is_benign(row) and row.get("utility_verdict") == "UNASSESSED":
        return "Answer quality is unassessed; this record does not establish task completion."
    response = str(row.get("response") or "").lower()
    if is_benign(row) and verdict(row) == "PASS" and any(
        phrase in response for phrase in ("couldn't find", "could not find", "fails to provide")
    ):
        return "Stored PASS needs utility review: the response says the requested information could not be found."
    return ""


def evidence_groups(rows_by_mode):
    """Union of IDs across both modes; retain duplicate and unidentified records."""
    groups = {}
    for mode in MODES:
        for i, row in enumerate(rows_by_mode.get(mode, []), 1):
            aid = str(row.get("id") or f"missing-id-{mode}-{i}")
            groups.setdefault(aid, {m: [] for m in MODES})[mode].append(row)
    return groups


def _input_signature(row):
    return (family(row), row.get("expected"), tuple(prompt_turns(row)),
            row.get("schema_version", 1), row.get("score_config"),
            row.get("suite_fingerprint"), row.get("code_fingerprint"))


def utility_verdict(row):
    value = row.get("utility_verdict")
    return value if value in ("PASS", "FAIL", "UNASSESSED", "NOT_APPLICABLE") else "UNASSESSED"


def complete_turn_evidence(row):
    turns = row.get("turn_results")
    return (isinstance(turns, list) and len(turns) == len(prompt_turns(row))
            and all(isinstance(t, dict) and "response" in t and "score" in t for t in turns))


def missing_v2_provenance(row):
    return row.get("schema_version") == 2 and any(
        not row.get(field) for field in ("score_config", "suite_fingerprint", "code_fingerprint")
    )


def summarize(rows_by_mode, sources=None):
    """Shared, dependency-free view model for report renderers and app integration."""
    modes = {}
    warnings = []
    for mode in MODES:
        rows = rows_by_mode.get(mode, [])
        attacks = [r for r in rows if not is_benign(r)]
        benign = [r for r in rows if is_benign(r)]
        models = sorted({str(r.get("model")) for r in rows if r.get("model")})
        timestamps = sorted(str(r["timestamp"]) for r in rows if r.get("timestamp"))
        valid_dates, invalid_dates = [], 0
        for stamp in timestamps:
            try:
                valid_dates.append(datetime.fromisoformat(stamp.replace("Z", "+00:00")))
            except ValueError:
                invalid_dates += 1
        missing_judge = sum(r.get("judge_verdict") not in ("PASS", "WARN", "FAIL") for r in benign)
        gaps = [str(r.get("id", "missing ID")) for r in benign if utility_caveat(r)]
        record_modes = sum(r.get("mode") not in (None, mode) for r in rows)
        counts = Counter(str(r.get("id")) for r in rows if r.get("id"))
        duplicates = sorted(aid for aid, n in counts.items() if n > 1)
        modes[mode] = {
            "available": mode in rows_by_mode, "rows": rows, "total": len(rows),
            "attacks": attacks, "benign": benign,
            "attack_counts": dict(Counter(verdict(r) for r in attacks)),
            "benign_counts": dict(Counter(verdict(r) for r in benign)),
            "utility_counts": dict(Counter(utility_verdict(r) for r in benign)),
            "execution_errors": sum(r.get("execution_status") == "error" for r in rows),
            "complete_turn_records": sum(complete_turn_evidence(r) for r in rows),
            "evaluation_configs": [json.loads(value) for value in sorted({
                json.dumps({key: r.get(key) for key in (
                    "schema_version", "run_id", "run_started_at", "score_config",
                    "suite_fingerprint", "code_fingerprint",
                )}, sort_keys=True, ensure_ascii=False)
                for r in rows if r.get("schema_version") == 2
            })],
            "models": models, "timestamps": timestamps,
            "missing_judge": missing_judge, "utility_gaps": gaps,
            "source": str((sources or {}).get(mode, "Provided records")),
            "digest": hashlib.sha256(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
        }
        if not rows:
            warnings.append(f"{mode.title()}: {'empty result file' if mode in rows_by_mode else 'no result file supplied'}; no rate can be calculated.")
            continue
        if duplicates:
            warnings.append(f"{mode.title()}: duplicate IDs ({', '.join(duplicates)}); all records are shown, but these IDs are excluded from paired comparisons.")
        if len(models) != 1 or any(not r.get("model") for r in rows):
            warnings.append(f"{mode.title()}: model metadata is mixed or missing; compare matching models only.")
        if len(timestamps) != len(rows) or invalid_dates:
            warnings.append(f"{mode.title()}: timestamps are missing or invalid; run provenance is incomplete.")
        if any(date.tzinfo is None for date in valid_dates):
            warnings.append(f"{mode.title()}: recorded timestamps have no timezone; times are displayed as recorded.")
        if record_modes:
            warnings.append(f"{mode.title()}: {record_modes} record(s) declare a different mode; exclude them from paired comparisons.")
        if missing_judge:
            warnings.append(f"{mode.title()}: judge unavailable for {missing_judge}/{len(benign)} benign records. Use independent utility checks where recorded; legacy marker-only PASS cannot establish answer utility or overblocking.")
        if any(missing_v2_provenance(r) for r in rows):
            warnings.append(f"{mode.title()}: schema 2 evaluation settings or fingerprints are missing; these records cannot be paired reliably.")
        if gaps:
            warnings.append(f"{mode.title()}: answer-quality review needed in {', '.join(gaps)}. Stored labels are preserved, but are not evidence of successful task completion.")
        legacy = sum(r.get("schema_version", 1) != 2 for r in rows)
        if legacy:
            warnings.append(f"{mode.title()}: {legacy} legacy records do not contain independent security, utility and execution assessments.")
        elif modes[mode]["complete_turn_records"] != len(rows):
            warnings.append(f"{mode.title()}: some records lack complete per-turn response and score evidence.")
        if modes[mode]["execution_errors"]:
            warnings.append(f"{mode.title()}: {modes[mode]['execution_errors']} execution error(s); a recorded security FAIL can coexist with an execution error.")
        if any(verdict(r) in ("ERROR", "UNKNOWN") for r in rows):
            warnings.append(f"{mode.title()}: ERROR/UNKNOWN records are incomplete evaluations; they remain in the attempted-test denominator and are not counted as safe outcomes.")
    groups = evidence_groups(rows_by_mode)
    shared = [aid for aid, group in groups.items() if all(group[m] for m in MODES)]
    paired, mismatched = [], []
    for aid in shared:
        group = groups[aid]
        if any(len(group[m]) != 1 for m in MODES):
            mismatched.append(aid)
            continue
        u, g = group["unguarded"][0], group["guarded"][0]
        if (_input_signature(u) != _input_signature(g) or not u.get("model") or
            u.get("model") != g.get("model") or
            missing_v2_provenance(u) or missing_v2_provenance(g) or
            any(group[m][0].get("mode") not in (None, m) for m in MODES)):
            mismatched.append(aid)
        else:
            paired.append(aid)
    adversarial_pairs = [aid for aid in paired if not is_benign(groups[aid]["unguarded"][0])]
    if mismatched:
        warnings.append(f"{len(mismatched)} shared ID(s) have duplicate records or mismatched inputs, model, mode, schema, scoring settings, suite or code; excluded from matched comparison: {', '.join(mismatched)}.")
    unmatched = [aid for aid, group in groups.items() if not all(group[m] for m in MODES)]
    if unmatched:
        warnings.append(f"{len(unmatched)} ID(s) are present in only one mode; evidence is shown without a paired comparison.")
    return {
        "modes": modes, "families": families(rows_by_mode), "groups": groups,
        "shared_ids": shared, "paired_ids": paired, "adversarial_pairs": adversarial_pairs,
        "mismatched_ids": mismatched, "unmatched_ids": unmatched, "warnings": warnings,
        "paired_fail": {mode: sum(verdict(groups[aid][mode][0]) == "FAIL" for aid in adversarial_pairs) for mode in MODES},
    }


def rate_table(rows_by_mode):
    lines = ["| Family | Unguarded FAIL / WARN / PASS / ERROR / UNKNOWN | Guarded FAIL / WARN / PASS / ERROR / UNKNOWN |",
             "|---|---|---|"]
    for fam in families(rows_by_mode):
        cells = []
        for mode in MODES:
            rows = [r for r in rows_by_mode.get(mode, []) if family(r) == fam]
            counts = Counter(verdict(r) for r in rows)
            cells.append(" / ".join(str(counts[v]) for v in VERDICTS) + f" (n={len(rows)})" if rows else "No evidence")
        lines.append(f"| {md_escape(fam)} | {cells[0]} | {cells[1]} |")
    return "\n".join(lines) if families(rows_by_mode) else "No family evidence available."


def defense_table(rows):
    lines = ["| Family | Example prompt | Stored result | Control to validate | Layer |", "|---|---|---|---|---|"]
    by_family = defaultdict(list)
    for row in rows:
        by_family[family(row)].append(row)
    for fam in families({"unguarded": rows}):
        row = min(by_family[fam], key=lambda r: VERDICTS.index(verdict(r)))
        fix, layer = DEFENSE_MAP.get(fam, ("Define a family-specific control", "To review"))
        lines.append("| " + " | ".join(md_escape(v) for v in (fam, excerpt(prompt_turns(row)[-1], 110), f"{row.get('mode', 'unspecified')}: {verdict(row)}", fix, layer)) + " |")
    return "\n".join(lines) if rows else "No attack evidence available for defense mapping."


def finding_cards(rows_by_mode):
    out = []
    for aid, group in evidence_groups(rows_by_mode).items():
        base = (group["unguarded"] or group["guarded"])[0]
        out.extend([f"### {md_escape(aid)} — {md_escape(family(base))}", "", f"**Objective:** {md_escape(base.get('objective', 'Not recorded'))}", ""])
        for mode in MODES:
            if not group[mode]:
                out.extend([f"**{mode.title()}:** No evidence supplied.", ""])
            for i, row in enumerate(group[mode], 1):
                suffix = f" · record {i}" if len(group[mode]) > 1 else ""
                out.extend([f"**{mode.title()} → {verdict(row)}{suffix}**", "", "**Prompt:** " + "<br>".join(f"Turn {n}: {md_escape(t)}" for n, t in enumerate(prompt_turns(row), 1)), "", f"**Response:** {md_escape(row.get('response', 'Not recorded'))}", "", f"**Reason:** {md_escape(row.get('reasoning') or 'Not recorded')}", "", f"**Rules / judge:** {md_escape(row.get('rule_verdict') or 'Unavailable')} / {md_escape(row.get('judge_verdict') or 'Unavailable')}", ""])
                if utility_caveat(row):
                    out.extend([f"> {utility_caveat(row)}", ""])
                if row.get("schema_version") == 2:
                    out.extend(["**Independent assessments:** " + md_escape(
                        f"security={row.get('security_verdict', 'UNASSESSED')}; "
                        f"utility={utility_verdict(row)}; execution={row.get('execution_status', 'unknown')}; "
                        f"judge={row.get('judge_status', 'unknown')}"), ""])
                    for turn in row.get("turn_results") or []:
                        score = turn.get("score") or {}
                        out.extend([f"#### Turn {md_escape(turn.get('turn_index'))}", "",
                                    "**Prompt:** " + md_escape(turn.get("prompt")), "",
                                    "**Response:** " + md_escape(turn.get("response")), "",
                                    "**Turn assessments:** " + md_escape(
                                        f"overall={score.get('verdict', 'UNKNOWN')}; "
                                        f"security={score.get('security_verdict', 'UNASSESSED')}; "
                                        f"utility={score.get('utility_verdict', 'UNASSESSED')}; "
                                        f"execution={turn.get('execution_status', 'unknown')}"), "",
                                    "**Reason:** " + md_escape(score.get("reasoning")), "",
                                    "**Tool/guard evidence:** " + md_escape(json.dumps({
                                        "tool_trace": turn.get("tool_trace", []),
                                        "guard_trace": turn.get("guard_trace", []),
                                        "error": turn.get("error"),
                                    }, ensure_ascii=False)), ""])
                trace = row.get("guard_trace") or []
                stopped = [str(t.get("layer", "unknown")) for t in trace if isinstance(t, dict) and t.get("action") in ("block", "review")]
                if stopped:
                    out.extend(["**Observed block/review layers:** " + md_escape(", ".join(stopped)), ""])
        out.append("---\n")
    return "\n".join(out) if out else "No evidence records available. Run the suite, then regenerate this report."


LIMITATIONS = [
    "These are saved observations, not a new evaluation of the current working tree. Code revisions, suite hashes, judge prompt versions and rail settings may be absent in legacy evidence.",
    "FAIL records detected disclosure or another rubric failure; WARN records potential leakage or utility problems. PASS records no failure under the stored evaluator. It does not establish complete security or a correct, useful answer.",
    "Adversarial outcomes and benign outcomes use separate denominators. Benign disclosure failures are reported in the benign group, not counted as successful attacks.",
    "Matched comparisons require a unique ID, identical inputs, model, schema and recorded evaluation settings, suite and code fingerprints. Legacy runs lack some metadata. Even matched records are separate runs; no repeated-trial confidence interval or causal security claim is supported.",
    "Marker rules cover known patterns and fields, not every possible disclosure. The LLM judge is fallible. Schema 2 measures benign utility with minimum expected-answer checks; PASS does not establish full semantic correctness. Legacy benign PASS labels require review before reporting preserved utility.",
    "Legacy multi-turn evidence may include only the final response and final guard trace. Earlier-turn response leakage cannot be excluded from these records alone.",
]


def build(rows_by_mode, sources=None):
    data = summarize(rows_by_mode, sources)
    md = ["# NeoBank ARIA — Red-Team Findings Report", "", "[Open the visual report](findings_report.html) · Generated offline with `python -m redteam.report`.", "", "## Executive summary", "", "Stored verdicts are evidence labels, not a security guarantee. Adversarial tests and benign utility checks are reported separately.", ""]
    for mode in MODES:
        info = data["modes"][mode]
        attack, benign = info["attack_counts"], info["benign_counts"]
        md.append(f"- **{mode.title()}**: {len(info['attacks'])} adversarial records — {attack.get('FAIL', 0)} FAIL, {attack.get('WARN', 0)} WARN, {attack.get('PASS', 0)} PASS, {attack.get('ERROR', 0)} ERROR, {attack.get('UNKNOWN', 0)} UNKNOWN; {len(info['benign'])} benign records — {benign.get('FAIL', 0)} FAIL, {benign.get('WARN', 0)} WARN, {benign.get('PASS', 0)} stored PASS, {benign.get('ERROR', 0)} ERROR, {benign.get('UNKNOWN', 0)} UNKNOWN.")
        quality = info["utility_counts"]
        md.append(f"  - Independent benign utility: {quality.get('PASS', 0)} PASS, {quality.get('FAIL', 0)} FAIL, {quality.get('UNASSESSED', 0)} UNASSESSED. Execution errors: {info['execution_errors']}; complete per-turn evidence: {info['complete_turn_records']}/{info['total']} records.")
    n = len(data["adversarial_pairs"])
    md.extend(["", f"**Matched adversarial comparison:** {n} IDs with matching inputs and model; stored FAIL {data['paired_fail']['unguarded']}/{n} unguarded → {data['paired_fail']['guarded']}/{n} guarded." if n else "**Matched adversarial comparison:** Unavailable; no compatible paired attack records.", "", "## Evidence quality and limitations", ""])
    md.extend(f"- {md_escape(w)}" for w in data["warnings"])
    md.extend(f"- {item}" for item in LIMITATIONS)
    md.extend(["", "## Results by family", "", rate_table(rows_by_mode), "", "FAIL/WARN/PASS are stored labels. Benign rows are utility checks and are excluded from the adversarial denominator.", "", "## Evidence-to-defense mapping", "", "Controls below identify what to validate; a PASS does not prove that each control executed or is complete.", "", defense_table([r for mode in MODES for r in rows_by_mode.get(mode, [])]), "", "## Run provenance", "", "| Mode | Records | Model(s) | First / last recorded timestamp | Source |", "|---|---|---|---|---|"])
    for mode in MODES:
        info = data["modes"][mode]
        stamps = info["timestamps"]
        values = (mode, str(info["total"]), ", ".join(info["models"]) or "Not recorded", f"{stamps[0]} / {stamps[-1]}" if stamps else "Not recorded", info["source"])
        md.append("| " + " | ".join(md_escape(v) for v in values) + " |")
    md.extend(["", "Content fingerprints (SHA-256 of canonical parsed records):", ""])
    md.extend(f"- {mode}: `{data['modes'][mode]['digest']}`" for mode in MODES)
    for mode in MODES:
        for config in data["modes"][mode]["evaluation_configs"]:
            md.extend(["", f"**{mode.title()} recorded evaluation configuration:**", "",
                       md_escape(json.dumps(config, sort_keys=True, ensure_ascii=False)), ""])
    md.extend(["", "## Evidence — per-test findings", "", finding_cards(rows_by_mode), "", "## Source review", "", "Authentication, runtime error handling and architecture concerns require source review independently of these prompt results. See [the code review](code_review.md) and architecture documentation; historical hard-coded findings are not treated as current test evidence.", ""])
    return "\n".join(md)


def build_html(rows_by_mode, sources=None):
    """Return a self-contained HTML report with no external assets or scripts."""
    from redteam.report_html import render
    return render(summarize(rows_by_mode, sources))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--unguarded", default=os.path.join(RESULTS_DIR, "unguarded_latest.jsonl"))
    parser.add_argument("--guarded", default=os.path.join(RESULTS_DIR, "guarded_latest.jsonl"))
    parser.add_argument("--out", default=os.path.join(DOCS, "findings_report.md"), help="Markdown output path")
    parser.add_argument("--html-out", help="HTML output path (defaults to Markdown path with .html suffix)")
    args = parser.parse_args()
    rows_by_mode, sources = {}, {}
    for mode in MODES:
        path = getattr(args, mode)
        if os.path.exists(path):
            rows_by_mode[mode] = load(path)
            sources[mode] = os.path.relpath(path, os.path.dirname(HERE))
    if not rows_by_mode:
        raise SystemExit("No results found. Existing reports were preserved. Run redteam.runner first.")
    html_out = args.html_out or os.path.splitext(args.out)[0] + ".html"
    if os.path.abspath(html_out) == os.path.abspath(args.out):
        parser.error("Markdown and HTML output paths must be different")
    outputs = ((args.out, build(rows_by_mode, sources)), (html_out, build_html(rows_by_mode, sources)))
    for path, content in outputs:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
        print(f"Wrote {path} ({len(content)} chars)")


if __name__ == "__main__":
    main()
