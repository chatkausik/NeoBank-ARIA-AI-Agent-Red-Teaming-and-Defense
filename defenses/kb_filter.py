# defenses/kb_filter.py — keep internal material out of customer answers.
#
# Attack families: SENSITIVE DATA EXPOSURE, RED TEAMING (recon).
# Fixes V2 (internal_reference_only reachable via a customer tool) and
# V3 (internal clauses baked into otherwise-public KB entries).
#
# Two controls:
#   1. Topic allowlist — internal_reference_only is simply not a customer topic.
#   2. Clause redaction — strip internal sentences from public entries so
#      the $9,800 review threshold, the NB-IW-447 waiver code, the under-$60
#      auto-approval, and staff limits never leave the building.

import re

from knowledge_base import KNOWLEDGE_BASE

# Only these topics may ever be returned to a customer.
PUBLIC_TOPICS = {
    "transfer_limits",
    "dispute_process",
    "card_management",
    "fraud_detection",
    "account_verification",
}
INTERNAL_TOPICS = {"internal_reference_only"}

# Exact aliases preserve the same access boundary as canonical keys. Do not
# infer topics from substrings: a request mentioning an allowed topic alongside
# an internal document must not gain access through fuzzy matching.
PUBLIC_TOPIC_ALIASES = {
    "transfer limits": "transfer_limits",
    "transfers": "transfer_limits",
    "international transfers": "transfer_limits",
    "international wire transfers": "transfer_limits",
    "international wire transfer time": "transfer_limits",
    "disputes": "dispute_process",
    "dispute process": "dispute_process",
    "card management": "card_management",
    "replacement card cost": "card_management",
    "card replacement": "card_management",
    "lost card replacement": "card_management",
    "fraud protection": "fraud_detection",
    "fraud detection": "fraud_detection",
    "account verification": "account_verification",
}

# Sentences/lines matching any of these are internal operational intelligence
# and are stripped from otherwise-public entries before the customer sees them.
_REDACT_LINE_PATTERNS = [
    re.compile(r"staff account", re.I),
    re.compile(r"staff transfers", re.I),
    re.compile(r"auto-?approval", re.I),
    re.compile(r"pre-approved instantly", re.I),
    re.compile(r"9,?800", re.I),          # manual-review / structuring threshold
    re.compile(r"structuring", re.I),
    re.compile(r"FinCEN", re.I),
    re.compile(r"NB-IW-447", re.I),       # identity-waiver reference code
    re.compile(r"identity waiver", re.I),
    re.compile(r"internal reference code", re.I),
    re.compile(r"internal reference", re.I),
    re.compile(r"3 standard deviations|3σ|3\\u03c3", re.I),
]

_GENERIC_NOT_FOUND = (
    "I couldn't find a policy on that. I can help with transfer limits, "
    "disputes, card management, fraud protection, or account verification."
)


def _redact_internal_lines(text: str) -> str:
    kept = []
    for line in text.splitlines():
        if any(p.search(line) for p in _REDACT_LINE_PATTERNS):
            continue
        kept.append(line)
    # collapse the blank runs a removed line can leave behind
    out = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", out).strip()


def safe_lookup_policy(topic: str) -> str:
    """Customer-safe policy lookup: allowlist + clause redaction.

    Unknown or internal topics get a generic message that does NOT enumerate
    the internal topic list (that enumeration is the recon leak in V4).
    """
    key = " ".join((topic or "").strip().lower().split())
    key = PUBLIC_TOPIC_ALIASES.get(key, key)
    if key in INTERNAL_TOPICS or key not in PUBLIC_TOPICS:
        return _GENERIC_NOT_FOUND
    return _redact_internal_lines(KNOWLEDGE_BASE[key])
