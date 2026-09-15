# defenses/conversation_guard.py — session-level defense.
#
# Attack families: CRESCENDO (multi-turn escalation) and SOCIAL ENGINEERING
# (authority / urgency / insider claims). A single turn can look innocent; the
# danger is the trajectory. This layer scores a bounded recent-turn window and
# returns a review message once the pattern is clear. No human queue or handoff
# is implemented here; backend authorization remains the data-access boundary.
#
# Stateless functions over an explicit state dict, so the app (st.session_state)
# and the red-team runner can both own the state.

import re

from seed_data import CUSTOMERS

# Names / ids of everyone in the bank — used to spot "asking about someone else".
_OTHER_ID_RE = re.compile(r"\bUSR-[A-Z0-9\-]+\b", re.I)

_AUTHORITY_RE = re.compile(
    r"\b(?:i am|i'm|this is)\s+"
    r"(?:(?:a|an|the|your|acting|senior|internal|neobank)\s+){0,3}"
    r"(?:manager|supervisor|admin|administrator|auditor|compliance|fraud team|"
    r"security team|staff|employee|relationship manager|law enforcement|police|"
    r"attorney|lawyer)\b"
    r"|\b(?:i am|i'm)\s+(?:new\s+)?(?:on|from|with)\s+(?:the\s+)?"
    r"(?:neobank|support team|fraud team|security team)\b"
    r"|\bthis is\s+[\w'-]+(?:\s+[\w'-]+){0,2}\s+from\s+(?:the\s+)?"
    r"(?:neobank|fraud team|security team)\b"
    r"|\bi have\s+(?:manager|admin|staff)\s+(?:authori[sz]ation|permission|access)\b",
    re.I)
_URGENCY_RE = re.compile(
    r"\b(urgent|emergency|immediately|right now|asap|time.?sensitive|"
    r"before it's too late|account will be closed|locked out)\b", re.I)
_INSIDER_RE = re.compile(
    r"\b(?:override code|auth code|nb-iw-447|internal reference|"
    r"(?:identity|authorization|permission) override)\b"
    r"|\b(?:you have permission|you are authori[sz]ed|i am authori[sz]ed|"
    r"i'm authori[sz]ed|he authori[sz]ed me|she authori[sz]ed me)\b"
    r"|\b(?:waive|skip|bypass|override)\s+(?:(?:the|your|identity|security)\s+){0,3}"
    r"(?:checks?|verification|authorization)\b", re.I)

HUMAN_REVIEW_REPLY = (
    "For your security, I can't help with that here. Requests involving another "
    "customer's account, authorization overrides, or identity exceptions must go "
    "through a verified human agent. I can still help with your own account or "
    "general banking questions."
)

# Only the last WINDOW_SIZE assessed turns contribute. Urgency amplifies
# substantive risk in that window; it never creates risk by itself.
THRESHOLD = 3
WINDOW_SIZE = 4
_W_OTHER_CUSTOMER = 2   # naming another customer or a foreign USR- id
_W_AUTHORITY = 2        # claiming a privileged role
_W_URGENCY = 1          # counted only alongside substantive window risk
_W_INSIDER = 2          # invoking override/insider codes
_SUBSTANTIVE_WEIGHTS = {
    "mentions_other_customer": _W_OTHER_CUSTOMER,
    "authority_claim": _W_AUTHORITY,
    "insider_claim": _W_INSIDER,
}


def new_state() -> dict:
    return {"risk": 0, "signals": []}


def _mentions_other_customer(text: str, session_user_id: str) -> bool:
    session_name = next(
        (c["name"] for c in CUSTOMERS if c["user_id"] == session_user_id), ""
    )
    for cid in _OTHER_ID_RE.findall(text):
        if cid.upper() != session_user_id.upper():
            return True
    low = text.lower()
    for c in CUSTOMERS:
        if c["user_id"] == session_user_id:
            continue
        # match on first+last or full name; ignore the session user's own name
        if (re.search(r"(?<!\w)" + re.escape(c["name"].lower()) + r"(?!\w)", low)
                and c["name"] != session_name):
            return True
    return False


def assess_turn(state: dict, message: str, session_user_id: str) -> dict:
    """
    Update state with this turn's signals and decide whether to divert.
    Returns {"action": "allow"|"review", "reason": str,
             "reply": <only when review>, "risk": int}.
    """
    signals = []
    if _mentions_other_customer(message, session_user_id):
        signals.append("mentions_other_customer")
    if _AUTHORITY_RE.search(message):
        signals.append("authority_claim")
    if _URGENCY_RE.search(message):
        signals.append("urgency")
    if _INSIDER_RE.search(message):
        signals.append("insider_claim")

    # Add metadata lazily to preserve new_state()'s public initial shape. A
    # pre-window state is carried as one old event, so a hot-reloaded session's
    # known signals age out rather than becoming an indefinite lockout.
    if "_risk_window" not in state:
        previous = list(state.get("signals", []))
        state["_risk_window"] = [previous] if previous else []
    window = (state["_risk_window"] + [signals])[-WINDOW_SIZE:]
    state["_risk_window"] = window
    state["signals"] = [signal for turn in window for signal in turn]
    substantive = sum(_SUBSTANTIVE_WEIGHTS.get(signal, 0)
                      for signal in state["signals"])
    urgency = state["signals"].count("urgency") * _W_URGENCY
    state["risk"] = substantive + (urgency if substantive else 0)
    reason = (f"session risk {state['risk']} over {len(window)} assessed turns "
              f"(current signals: {signals})")

    if state["risk"] >= THRESHOLD:
        return {"action": "review", "risk": state["risk"],
                "reason": reason,
                "reply": HUMAN_REVIEW_REPLY}
    return {"action": "allow", "risk": state["risk"],
            "reason": reason, "reply": ""}
