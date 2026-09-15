# redteam — repeatable attack harness for ARIA.
#   canaries.py — sensitive markers derived from the live data
#   scorer.py   — rule verdict + optional LLM judge -> PASS/WARN/FAIL
#   runner.py   — run attacks against unguarded/guarded ARIA, write JSONL
#   report.py   — turn results into docs/findings_report.md
