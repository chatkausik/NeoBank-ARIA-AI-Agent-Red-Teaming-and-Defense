"""Offline regressions for configuration changes and evidence navigation."""

from pathlib import Path

import dotenv
import openai
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import agent
import database
from defenses import pipeline


APP_PATH = Path(__file__).resolve().parents[1] / "app.py"


@pytest.fixture
def offline_app(monkeypatch, tmp_path):
    """Isolate database state, dotenv loading, and every live model entry point."""
    monkeypatch.setattr(dotenv, "load_dotenv", lambda *args, **kwargs: False)
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "neobank-test.db"))

    def no_api_calls(*args, **kwargs):
        pytest.fail("App UI regression tests must not call an external model")

    monkeypatch.setattr(openai, "OpenAI", no_api_calls)
    monkeypatch.setattr(agent, "create_aria_agent", no_api_calls)
    monkeypatch.setattr(agent, "run_agent", no_api_calls)
    monkeypatch.setattr(pipeline, "invoke_guarded", no_api_calls)

    connections = []
    get_connection = database.get_connection

    def isolated_connection():
        connection = get_connection()
        connections.append(connection)
        return connection

    monkeypatch.setattr(database, "get_connection", isolated_connection)
    st.cache_resource.clear()
    try:
        yield AppTest.from_file(APP_PATH, default_timeout=10)
    finally:
        st.cache_resource.clear()
        for connection in connections:
            connection.close()


@pytest.mark.parametrize("configuration", ["defense_mode", "aria_model"])
def test_configuration_change_starts_fresh_chat_and_preserves_log(
    offline_app, configuration
):
    app = offline_app
    history = [
        {"role": "user", "content": "An earlier experiment"},
        {"role": "assistant", "content": "An earlier response"},
    ]
    log = [{"prompt": "An earlier experiment", "response": "An earlier response"}]
    app.session_state["messages"] = history
    app.session_state["guard_state"] = {"risk": 4, "signals": ["authority_claim"]}
    app.session_state["rt_log"] = log
    app.run()
    assert not app.exception

    if configuration == "defense_mode":
        app.radio(key="defense_mode").set_value("Guarded").run()
    else:
        model = app.selectbox(key="aria_model")
        next_model = next(option for option in model.options if option != model.value)
        model.set_value(next_model).run()

    assert not app.exception
    assert app.session_state["messages"] == []
    assert app.session_state["guard_state"] == {"risk": 0, "signals": []}
    assert app.session_state["rt_log"] == log
    assert "fresh conversation" in app.session_state["run_notice"]


def test_custom_configured_default_model_is_selectable(offline_app, monkeypatch):
    monkeypatch.setattr(agent, "DEFAULT_MODEL", "custom-offline-model")
    app = offline_app.run()

    assert not app.exception
    model = app.selectbox(key="aria_model")
    assert model.value == "custom-offline-model"
    assert model.options.count("custom-offline-model") == 1
    model.set_value("gpt-4o").run()
    app.selectbox(key="aria_model").set_value("custom-offline-model").run()
    assert not app.exception
    assert app.session_state["aria_model"] == "custom-offline-model"


def test_past_assistant_trace_remains_visible_after_rerun(offline_app):
    app = offline_app
    trace = [{"layer": "input_pattern", "action": "block", "detail": "matched test rule"}]
    history = [
        {"role": "user", "content": "An earlier test prompt"},
        {
            "role": "assistant",
            "content": "I can help with your own account.",
            "guard_trace": trace,
            "mode": "Guarded",
            "model": "recorded-model",
        },
    ]
    for key, value in {
        "logged_in": True,
        "user_name": "Alex Mercer",
        "user_id": "USR-0042",
        "account_tier": "Standard",
        "api_key": "offline-test-key",
        "api_key_validated": "offline-test-key",
        "messages": history,
        "defense_mode": "Guarded",
    }.items():
        app.session_state[key] = value

    for _ in range(2):
        app.run()
        assert not app.exception
        assert any(expander.label == "🛡️ Guard trace (Guarded)" for expander in app.expander)
        assert any(caption.value == "Model: recorded-model" for caption in app.caption)
        assert any("input_pattern" in markdown.value for markdown in app.markdown)
        assert any(text.value == "matched test rule" for text in app.text)
        assert app.session_state["messages"] == history


def test_findings_navigation_needs_no_api_key_or_login(offline_app):
    app = offline_app.run()
    assert not app.exception
    assert app.session_state["api_key"] == ""
    assert not app.session_state.filtered_state.get("logged_in", False)
    app.button(key="nav_📊 Findings Report").click().run()
    assert not app.exception
    assert app.session_state["page"] == "📊 Findings Report"
    assert [tab.label for tab in app.tabs] == ["Test results", "Code review"]
    assert any(markdown.value == "## 📊 Findings Report" for markdown in app.markdown)
    assert not app.session_state.filtered_state.get("logged_in", False)
    assert app.session_state["api_key"] == ""


def test_chat_preserves_backend_execution_evidence(offline_app, monkeypatch, tmp_path):
    from ui import reports
    monkeypatch.setattr(reports, "RT_LOG_PATH", str(tmp_path / "manual.jsonl"))
    event = {"name": "query_account", "args": {"user_id": "USR-PP-001"},
             "requested_user_id": "USR-PP-001", "effective_user_id": "USR-0042",
             "authorization": "denied", "execution_status": "ok", "result_len": 4,
             "result": "self", "call_id": "call-1"}
    def guarded(**kwargs):
        return {"response": "Here is your own account.", "trace": [],
                "guard_state": kwargs["guard_state"], "tool_calls": [event],
                "execution_status": "ok", "error": None}
    monkeypatch.setattr(pipeline, "invoke_guarded", guarded)
    app = offline_app
    for key, value in {"logged_in": True, "user_name": "Alex Mercer", "user_id": "USR-0042",
                       "account_tier": "Standard", "api_key": "offline-test-key",
                       "api_key_validated": "offline-test-key", "messages": [],
                       "defense_mode": "Guarded"}.items():
        app.session_state[key] = value
    app.run()
    app.chat_input[0].set_value("Please show my account").run()
    assert not app.exception
    entry = app.session_state["rt_log"][-1]
    assert entry["tool_trace"] == [event]
    assert entry["execution_status"] == "ok"
    assert "offline-test-key" not in (tmp_path / "manual.jsonl").read_text()


def test_chat_setup_failure_uses_safe_error_evidence(offline_app, monkeypatch, tmp_path):
    from ui import reports
    monkeypatch.setattr(reports, "RT_LOG_PATH", str(tmp_path / "manual.jsonl"))
    def failure(**kwargs):
        raise RuntimeError("private exception payload")
    monkeypatch.setattr(pipeline, "invoke_guarded", failure)
    app = offline_app
    for key, value in {"logged_in": True, "user_name": "Alex Mercer", "user_id": "USR-0042",
                       "account_tier": "Standard", "api_key": "offline-test-key",
                       "api_key_validated": "offline-test-key", "messages": [],
                       "defense_mode": "Guarded"}.items():
        app.session_state[key] = value
    app.run()
    app.chat_input[0].set_value("Hello").run()
    assert not app.exception
    entry = app.session_state["rt_log"][-1]
    assert entry["execution_status"] == "error"
    assert entry["error"] == "request_failed"
    assert "private exception payload" not in str(app.session_state["messages"])
    assert "private exception payload" not in (tmp_path / "manual.jsonl").read_text()
