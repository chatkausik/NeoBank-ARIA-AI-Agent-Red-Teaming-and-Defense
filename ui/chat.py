"""Chat execution and per-turn evidence display."""

import logging
import re
import streamlit as st
import agent
from defenses import pipeline, conversation_guard as cguard
from ui.reports import _log_turn

logger = logging.getLogger(__name__)


def _chat_markdown(content):
    """Render dollar amounts literally without changing stored model evidence."""
    return re.sub(r"(?<!\\)\$(?=\d)", r"\\$", content)


def _render_turn_trace(trace, mode, model=""):
    """Keep the evidence trace visible after Streamlit reruns the page."""
    if not trace:
        return
    guarded = mode == "Guarded"
    label = "🛡️ Guard trace" if guarded else "🔧 Tool trace"
    with st.expander(f"{label} ({mode})", expanded=False):
        if model:
            st.caption(f"Model: {model}")
        for item in trace:
            st.markdown(f"- **{item['layer']}** → `{item['action']}`")
            if item.get("detail"):
                st.text(item["detail"])
        if guarded and not any(
            item["action"] in ("block", "review", "call", "error") for item in trace
        ):
            st.caption("All layers allowed; answered normally.")


def render_chat(conn):
    """Render the main chat interface."""

    # ── Validate current API key ──
    api_key = st.session_state.get("api_key", "").strip()
    validated_key = st.session_state.get("api_key_validated", "")

    if not api_key:
        st.warning(
            "⬅️ Please enter your OpenAI API key in the sidebar to start chatting."
        )
        return

    # If the user changed the API key after login,
    # force them to verify it again.
    if validated_key != api_key:
        st.warning(
            "⬅️ Your OpenAI API key has changed. "
            "Please sign in again so the new key can be verified."
        )

        st.session_state.logged_in = False
        st.session_state.pop("api_key_validated", None)

        st.rerun()

    # ── Per-session red-team state ──
    if "guard_state" not in st.session_state:
        st.session_state.guard_state = cguard.new_state()
    if "rt_log" not in st.session_state:
        st.session_state.rt_log = []
    notice = st.session_state.pop("run_notice", None)
    if notice:
        st.info(notice)

    # ── Chat header ──
    st.markdown(
        f"""
        <div class="chat-header">
            <h2>💬 ARIA — NeoBank Assistant</h2>
            <p>
                Logged in as {st.session_state.user_name}
                · {st.session_state.user_id}
                · {st.session_state.account_tier}
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Existing conversation ──
    for msg in st.session_state.messages:
        with st.chat_message(
            msg["role"],
            avatar="🤖" if msg["role"] == "assistant" else "👤",
        ):
            st.markdown(_chat_markdown(msg["content"]))
            if msg["role"] == "assistant":
                _render_turn_trace(msg.get("guard_trace", []),
                                   msg.get("mode", ""), msg.get("model", ""))

    # ── Initial welcome message ──
    if not st.session_state.messages:
        welcome = (
            f"Hello {st.session_state.user_name}! 👋 "
            f"I'm **ARIA**, your NeoBank AI assistant. "
            f"I can help you with account queries, card management, "
            f"fund transfers, transaction disputes, and general banking questions."
            f"\n\nWhat can I help you with today?"
        )

        with st.chat_message(
            "assistant",
            avatar="🤖",
        ):
            st.markdown(welcome)

    # ── User message input ──
    if prompt := st.chat_input("Message ARIA..."):

        st.session_state.messages.append(
            {
                "role": "user",
                "content": prompt,
            }
        )

        with st.chat_message(
            "user",
            avatar="👤",
        ):
            st.markdown(_chat_markdown(prompt))

        # ── Run ARIA (unguarded target, or guarded pipeline) ──
        mode = st.session_state.get("defense_mode", "Unguarded")
        model = st.session_state.get("aria_model", agent.DEFAULT_MODEL)
        guarded = mode == "Guarded"
        guard_trace = []
        tool_trace = []
        execution_status, error = "ok", None

        with st.chat_message(
            "assistant",
            avatar="🤖",
        ):
            with st.spinner("ARIA is thinking..."):
                try:
                    if guarded:
                        out = pipeline.invoke_guarded(
                            conn=conn,
                            user_message=prompt,
                            user_id=st.session_state.user_id,
                            account_tier=st.session_state.account_tier,
                            api_key=api_key,
                            chat_history=st.session_state.messages[:-1],
                            guard_state=st.session_state.guard_state,
                            model=model,
                        )
                        response = out["response"]
                        guard_trace = out["trace"]
                        result = out
                        st.session_state.guard_state = out["guard_state"]
                    else:
                        agent_components = agent.create_aria_agent(
                            conn=conn,
                            user_id=st.session_state.user_id,
                            account_tier=st.session_state.account_tier,
                            api_key=api_key,
                            model=model,
                            mode="unguarded",
                        )
                        result = agent.run_agent(
                            agent_components=agent_components,
                            user_message=prompt,
                            chat_history=st.session_state.messages[:-1],
                        )
                        response = result["response"]
                        guard_trace = [
                            {"layer": "tool", "action": "call",
                             "detail": f"{tc['name']}({tc['args']})"}
                            for tc in result.get("tool_calls", [])
                        ]
                    tool_trace = result.get("tool_calls", [])
                    execution_status = result.get("execution_status", "ok")
                    error = result.get("error")
                    if execution_status == "error" and not any(
                        t["action"] == "error" for t in guard_trace
                    ):
                        guard_trace.append({"layer": "execution", "action": "error",
                                            "detail": error or "request_failed"})
                except Exception as e:
                    logger.warning("Chat execution failed: %s", type(e).__name__)
                    execution_status, error = "error", "request_failed"
                    response = (
                        "I apologize, but I'm experiencing a technical issue. "
                        "Please try again."
                    )
                    guard_trace = [{"layer": "error", "action": "error",
                                    "detail": error}]

            st.markdown(_chat_markdown(response))

            # ── Guard / tool trace (evidence for screenshots) ──
            _render_turn_trace(guard_trace, mode, model)

        # ── Save assistant response ──
        st.session_state.messages.append(
            {"role": "assistant", "content": response,
             "guard_trace": guard_trace, "mode": mode, "model": model}
        )

        # ── Auto-log this turn for the Red Team Log page ──
        _log_turn(prompt, response, mode, model, guard_trace,
                  tool_trace=tool_trace, execution_status=execution_status, error=error)

        st.rerun()
