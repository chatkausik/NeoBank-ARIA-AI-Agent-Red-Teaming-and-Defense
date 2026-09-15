# defenses — hardened ARIA controls, mapped to attack families.
#
# Layered, defense-in-depth. No single layer is trusted:
#   prompts.py            — hardened system prompt (instruction hierarchy)
#   normalize.py          — decode obfuscation before any filter sees it
#   input_rails.py        — pattern + LLM intent screen (pre-LLM)
#   tool_policy.py        — real authorization: query_account bound to session
#   kb_filter.py          — internal content never reaches a customer tool
#   conversation_guard.py — crescendo / social-engineering session tracking
#   output_rails.py       — canary + PII/marker scan (post-LLM)
#   pipeline.py           — invoke_guarded() wires them together
