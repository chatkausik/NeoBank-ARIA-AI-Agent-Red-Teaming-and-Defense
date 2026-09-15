# defenses/pipeline.py — the guarded ARIA request pipeline.
#
# Order (defense in depth):
#   1. input rails      — block obvious jailbreak/obfuscation/exfil (pre-LLM)
#   2. conversation guard — divert crescendo / social-engineering trajectories
#   3. agent            — hardened prompt + session-bound tools + spotlighting
#   4. output rails     — scan the response; block leaks (post-LLM)
# Every layer that acts is recorded in the returned trace, which the app shows
# as a "guard trace" and the red-team runner stores as evidence.

import logging

from agent import (
    AGENT_ERROR_CODES, DEFAULT_MODEL, SAFE_ERROR_RESPONSE, create_aria_agent, run_agent,
)
from defenses import conversation_guard as cguard
from defenses.input_rails import check_input
from defenses.output_rails import apply_output_rails, SAFE_REFUSAL

logger = logging.getLogger("guarded_aria.pipeline")


def invoke_guarded(conn, user_message: str, user_id: str, account_tier: str,
                   api_key: str, chat_history: list[dict] | None = None,
                   guard_state: dict | None = None, model: str | None = None,
                   use_llm_rails: bool = True) -> dict:
    """
    Run the full guarded pipeline for one user turn.

    Returns:
        {
          "response": str,                 # what the user sees
          "trace": [ {layer, action, detail}, ... ],
          "blocked_by": str | None,        # first layer that stopped it
          "guard_state": dict,             # updated session risk (pass back in)
          "tool_calls": [structured tool execution records],
          "execution_status": "ok" | "error",  # policy refusals are successful
          "error": None | safe error code,
        }
    """
    chat_history = chat_history or []
    guard_state = guard_state if guard_state is not None else cguard.new_state()
    trace: list[dict] = []
    tool_calls: list[dict] = []

    def finish(response, blocked_by=None, execution_status="ok", error=None):
        return {"response": response, "trace": trace, "blocked_by": blocked_by,
                "guard_state": guard_state, "tool_calls": tool_calls,
                "execution_status": execution_status, "error": error}

    def fail(code):
        logger.warning("[PIPELINE] execution error: %s", code)
        trace.append({"layer": "runtime", "action": "error", "detail": code})
        return finish(SAFE_ERROR_RESPONSE, execution_status="error", error=code)

    # ── 1. Input rails ──
    try:
        verdict = check_input(user_message, api_key=api_key,
                              model=model or DEFAULT_MODEL, use_llm=use_llm_rails)
    except Exception:
        return fail("input_rails_failed")
    if verdict["action"] == "block":
        trace.append({"layer": verdict["layer"] or "input", "action": "block",
                      "detail": f"{verdict['family']}: {verdict['reason']}"})
        return finish(SAFE_REFUSAL, blocked_by=verdict["layer"] or "input_rails")
    trace.append({"layer": "input_rails", "action": "allow", "detail": ""})

    # ── 2. Conversation guard (crescendo / social engineering) ──
    try:
        turn = cguard.assess_turn(guard_state, user_message, user_id)
    except Exception:
        return fail("conversation_guard_failed")
    if turn["action"] == "review":
        trace.append({"layer": "conversation_guard", "action": "review",
                      "detail": turn["reason"]})
        return finish(turn["reply"], blocked_by="conversation_guard")
    trace.append({"layer": "conversation_guard", "action": "allow",
                  "detail": turn["reason"]})

    # ── 3. Agent (hardened prompt + secure tools + spotlighting) ──
    try:
        components = create_aria_agent(conn, user_id, account_tier, api_key,
                                      model=model, mode="guarded")
    except Exception:
        return fail("agent_setup_failed")
    try:
        result = run_agent(components, user_message, chat_history)
        tool_calls = result["tool_calls"]
        if (result["execution_status"] not in {"ok", "error"}
                or not isinstance(result["response"], str)
                or not isinstance(tool_calls, list)):
            return fail("agent_execution_failed")
    except Exception:
        return fail("agent_execution_failed")
    for tc in tool_calls:
        action = "call" if tc["execution_status"] == "ok" else "error"
        detail = f"{tc['name']} -> {tc['execution_status']}; {tc['result_len']} chars"
        if tc.get("effective_user_id"):
            detail += (f"; requested={tc['requested_user_id'] or '(session)'}"
                       f"; effective={tc['effective_user_id']}; authorization={tc['authorization']}")
        trace.append({"layer": "secure_tool", "action": action, "detail": detail})

    error = None
    response = result["response"]
    if result["execution_status"] == "error":
        error = result.get("error")
        if error not in AGENT_ERROR_CODES:
            error = "agent_execution_failed"
        response = SAFE_ERROR_RESPONSE
        trace.append({"layer": "runtime", "action": "error", "detail": error})

    # ── 4. Output rails ──
    try:
        scanned = apply_output_rails(response, user_id)
    except Exception:
        return fail("output_rails_failed")
    if scanned["blocked"]:
        trace.append({"layer": "output_rails", "action": "block",
                      "detail": f"leak hits: {scanned['hits']}"})
        return finish(scanned["response"], blocked_by="output_rails",
                      execution_status=result["execution_status"], error=error)
    trace.append({"layer": "output_rails", "action": "allow", "detail": ""})

    return finish(scanned["response"], execution_status=result["execution_status"], error=error)
