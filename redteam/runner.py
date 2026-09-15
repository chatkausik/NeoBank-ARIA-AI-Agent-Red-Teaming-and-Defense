"""Run saved attack fixtures and persist complete, versioned turn evidence.

The CLI reads credentials only when explicitly run. Imports and offline tests do
not read .env, create a database, invoke models, or change historical results.
"""
import argparse
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

import yaml

from database import get_connection, init_database
from defenses import conversation_guard as cguard
from redteam import scorer
from redteam.canaries import ATTACKER_USER_ID

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
ATTACK_DIR = str(HERE / "attacks")
RESULTS_DIR = str(HERE / "results")
SESSION_USER = {"user_id": ATTACKER_USER_ID, "tier": "Standard"}
SCHEMA_VERSION = 2


def create_aria_agent(*args, **kwargs):
    from agent import create_aria_agent as factory
    return factory(*args, **kwargs)


def run_agent(*args, **kwargs):
    from agent import run_agent as invoke
    return invoke(*args, **kwargs)


def invoke_guarded(*args, **kwargs):
    from defenses.pipeline import invoke_guarded as invoke
    return invoke(*args, **kwargs)


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def code_fingerprint():
    """Hash only named application/evaluator source files, never environment data."""
    paths = [ROOT / name for name in ("agent.py", "database.py", "seed_data.py", "knowledge_base.py")]
    paths += sorted((ROOT / "defenses").glob("*.py"))
    paths += [HERE / name for name in ("runner.py", "scorer.py", "canaries.py", "utility.py")]
    contents = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}
    return fingerprint(contents)


def load_attacks(family_filter: str | None):
    suite = []
    for path in sorted(Path(ATTACK_DIR).glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        family = data["family"]
        if family_filter and family != family_filter:
            continue
        suite.extend({**attack, "family": family} for attack in data.get("attacks", []))
    return suite


def _run_conversation(conn, mode, attack, api_key, model, use_llm, use_judge):
    components, startup_error = None, None
    if mode == "unguarded":
        try:
            components = create_aria_agent(conn, SESSION_USER["user_id"], SESSION_USER["tier"],
                                           api_key, model=model, mode=mode)
        except Exception:
            startup_error = "runner_initialization_failed"
    history, prompt_history, turn_results = [], [], []
    guard_state = cguard.new_state()
    for index, prompt in enumerate(attack.get("turns") or [attack["prompt"]], 1):
        prompt_history.append(prompt)
        try:
            if startup_error:
                out = {"response": "This request could not be completed.", "execution_status": "error", "error": startup_error}
            elif mode == "guarded":
                out = invoke_guarded(conn, prompt, SESSION_USER["user_id"], SESSION_USER["tier"], api_key,
                                     chat_history=history, guard_state=guard_state,
                                     model=model, use_llm_rails=use_llm)
                guard_state = out.get("guard_state", guard_state)
            else:
                out = run_agent(components, prompt, history)
            response = str(out.get("response") or "")
            tool_trace = copy.deepcopy(out.get("tool_calls") or [])
            guard_trace = copy.deepcopy(out.get("trace") or ([{"layer": "none", "action": "n/a", "detail": ""}] if mode == "unguarded" else []))
            execution = out.get("execution_status", "ok")
            error = out.get("error")
            if any(t.get("execution_status") == "error" for t in tool_trace):
                execution, error = "error", error or "tool_execution_failed"
        except Exception:
            # Never interpolate exception text into model-visible or saved evidence.
            response, tool_trace, guard_trace = "This request could not be completed.", [], []
            execution, error = "error", "runner_execution_failed"
        outcome = scorer.score(
            response, prompt, attack["family"], attack.get("objective", ""),
            attack.get("expected", "refuse"), api_key=api_key, model=model, use_judge=use_judge,
            session_user_id=SESSION_USER["user_id"], tool_trace=tool_trace,
            attack_id=attack.get("id"), execution_status=execution, error=error,
            prompt_history=prompt_history,
        )
        turn_results.append({
            "turn_index": index, "prompt": prompt, "prompt_history": list(prompt_history),
            "response": response, "tool_trace": tool_trace, "guard_trace": guard_trace,
            "execution_status": outcome["execution_status"], "error": outcome["error"],
            "timestamp": _now(), "score": outcome,
        })
        history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": response}])
    return turn_results


def _run_unguarded(conn, attack, api_key, model, use_judge=True):
    return _run_conversation(conn, "unguarded", attack, api_key, model, False, use_judge)


def _run_guarded(conn, attack, api_key, model, use_llm, use_judge=True):
    return _run_conversation(conn, "guarded", attack, api_key, model, use_llm, use_judge)


def run_mode(conn, mode, suite, api_key, model, use_judge, use_llm):
    if mode not in ("unguarded", "guarded"):
        raise ValueError("mode must be guarded or unguarded")
    rows = []
    run_id, started = str(uuid.uuid4()), _now()
    suite_hash, code_hash = fingerprint(suite), code_fingerprint()
    config = {"use_judge": bool(use_judge), "use_llm_rails": bool(use_llm),
              "judge_model": model if use_judge else None, "scorer_version": scorer.SCORER_VERSION,
              "judge_prompt_version": scorer.JUDGE_PROMPT_VERSION,
              "utility_rubric_version": scorer.utility.RUBRIC_VERSION,
              "session_user_id": SESSION_USER["user_id"], "session_tier": SESSION_USER["tier"]}
    for i, attack in enumerate(suite, 1):
        turns = _run_conversation(conn, mode, attack, api_key, model, use_llm, use_judge)
        aggregate = scorer.aggregate(turns)
        row = {
            "schema_version": SCHEMA_VERSION, "run_id": run_id, "run_started_at": started,
            "mode": mode, "model": model, "id": attack["id"], "family": attack["family"],
            "objective": attack.get("objective", ""), "expected": attack.get("expected", "refuse"),
            "prompt": attack.get("prompt"), "turns": attack.get("turns"),
            "response": turns[-1]["response"], "turn_results": turns,
            "tool_trace": [event for turn in turns for event in turn["tool_trace"]],
            "guard_trace": [dict(event, turn_index=turn["turn_index"]) for turn in turns for event in turn["guard_trace"]],
            **aggregate, "timestamp": _now(), "score_config": dict(config),
            "suite_fingerprint": suite_hash, "code_fingerprint": code_hash,
        }
        rows.append(row)
        print(f"  [{i:>2}/{len(suite)}] {mode:<9} {attack['id']:<18} -> {row['verdict']} "
              f"(security={row['security_verdict']}, utility={row['utility_verdict']}, execution={row['execution_status']})")
    return rows


def write_results(mode, rows):
    """Keep immutable run files; update latest only after a complete file write."""
    if mode not in ("unguarded", "guarded"):
        raise ValueError("mode must be guarded or unguarded")
    directory = Path(RESULTS_DIR)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    path = directory / f"{mode}_{stamp}_{uuid.uuid4().hex[:8]}.jsonl"
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    with path.open("x", encoding="utf-8") as fh:
        fh.write(payload)
    temporary = directory / f".{mode}_latest_{uuid.uuid4().hex}.tmp"
    with temporary.open("x", encoding="utf-8") as fh:
        fh.write(payload)
    os.replace(temporary, directory / f"{mode}_latest.jsonl")
    return str(path)


def summarize(mode, rows):
    from collections import Counter
    counts = Counter(row["verdict"] for row in rows)
    print(f"\n{mode.upper()} summary: " + "  ".join(f"{v}={counts[v]}" for v in ("PASS", "WARN", "FAIL", "ERROR", "UNKNOWN")) + f"  (n={len(rows)})")


def main():
    parser = argparse.ArgumentParser(description="ARIA red-team runner")
    parser.add_argument("--mode", choices=["unguarded", "guarded", "both"], default="both")
    parser.add_argument("--family", default=None)
    parser.add_argument("--model", default=None, help="Override ARIA_MODEL / agent default")
    parser.add_argument("--no-judge", action="store_true", help="Intentional rules-only security scoring")
    parser.add_argument("--no-llm-rails", action="store_true", help="Disable guarded input intent classifier")
    args = parser.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    from agent import DEFAULT_MODEL
    model = args.model or DEFAULT_MODEL
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not api_key:
        sys.exit("OPENAI_API_KEY not found in environment / .env")
    suite = load_attacks(args.family)
    if not suite:
        sys.exit(f"No attacks found (family={args.family})")
    conn = get_connection()
    try:
        init_database(conn)
        for mode in (["unguarded", "guarded"] if args.mode == "both" else [args.mode]):
            rows = run_mode(conn, mode, suite, api_key, model, not args.no_judge, not args.no_llm_rails)
            path = write_results(mode, rows)
            summarize(mode, rows)
            print(f"  wrote {path}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
