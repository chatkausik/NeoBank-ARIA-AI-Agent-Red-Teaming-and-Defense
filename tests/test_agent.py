"""Model-free integration checks for tool protocol and execution evidence."""

import json
import sqlite3

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import tool

from agent import MAX_TOOL_CALLS, SAFE_ERROR_RESPONSE, build_tools, create_aria_agent, run_agent
from database import init_database
from defenses.tool_policy import build_secure_tools


class ModelStub:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def invoke(self, messages):
        self.calls.append(list(messages))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    init_database(connection)
    yield connection
    connection.close()


def call(name="lookup_policy", args=None, call_id="policy-1"):
    return {"name": name, "args": {"topic": "transfer_limits"} if args is None else args,
            "id": call_id, "type": "tool_call"}


def components(conn, calls, final=None, mode="guarded"):
    tools = build_secure_tools(conn, "USR-0042") if mode == "guarded" else build_tools(conn)
    return {
        "llm_with_tools": ModelStub(AIMessage(content="", tool_calls=calls)),
        "llm": ModelStub(final if final is not None else AIMessage(content="Your account summary.")),
        "tools_by_name": {item.name: item for item in tools},
        "system_prompt": "Offline test system prompt.", "mode": mode,
    }


def test_multiple_tools_get_matching_responses_and_backend_identity(conn):
    requested = [call(), call("query_account", {"user_id": "USR-PP-001"}, "account-2")]
    runtime = components(conn, requested)
    result = run_agent(runtime, "Look up my account and transfer limits.", [])

    assert result["execution_status"] == "ok"
    assert result["error"] is None
    assert len(runtime["llm_with_tools"].calls) == len(runtime["llm"].calls) == 1
    messages = runtime["llm"].calls[0]
    declared = [tc["id"] for message in messages if isinstance(message, AIMessage)
                for tc in message.tool_calls]
    answered = [message.tool_call_id for message in messages if isinstance(message, ToolMessage)]
    assert declared == answered == ["policy-1", "account-2"]
    assert len(result["tool_calls"]) == 2
    policy, account = result["tool_calls"]
    assert policy["authorization"] == "not_applicable"
    assert policy["effective_user_id"] is None
    assert account["args"] == {"user_id": "USR-PP-001"}
    assert account["requested_user_id"] == "USR-PP-001"
    assert account["effective_user_id"] == "USR-0042"
    assert account["authorization"] == "denied"
    assert account["execution_status"] == "ok"
    assert "Alex Mercer" in account["result"]
    assert "Adrian Cross" not in account["result"]
    for event in result["tool_calls"]:
        assert event["result_len"] == len(event["result"])


@pytest.mark.parametrize("args", [{}, {"user_id": "USR-0042"}, {"user_id": "  USR-0042  "}])
def test_secure_tool_own_or_implicit_identity_is_backend_authorized(conn, args):
    runtime = components(conn, [call("query_account", args, "self")])
    result = run_agent(runtime, "My balance?", [])
    assert result["execution_status"] == "ok"
    event = result["tool_calls"][0]
    assert event["effective_user_id"] == "USR-0042"
    assert event["authorization"] == "allowed"
    assert event["requested_user_id"] == (args.get("user_id", "").strip() or None)


def test_unguarded_cross_account_permissions_remain_deliberately_vulnerable(conn):
    runtime = components(conn, [call("query_account", {"user_id": "USR-PP-001"})],
                         mode="unguarded")
    result = run_agent(runtime, "Another account", [])
    event = result["tool_calls"][0]
    assert result["execution_status"] == "ok"
    assert event["effective_user_id"] == "USR-PP-001"
    assert event["authorization"] == "allowed"
    assert "Adrian Cross" in event["result"]


@pytest.mark.parametrize("bad_call,error", [
    (call(name="unknown_tool", call_id="bad"), "unknown_tool"),
    (call(args={}, call_id="bad"), "invalid_tool_arguments"),
    (call(args={"topic": 42}, call_id="bad"), "invalid_tool_arguments"),
    (call(args={"topic": "transfer_limits", "extra": True}, call_id="bad"), "invalid_tool_arguments"),
    (call(call_id=""), "invalid_tool_call"),
    (call(call_id="policy-1"), "invalid_tool_call"),
])
def test_invalid_batch_executes_no_tools_and_does_not_retry(conn, monkeypatch, bad_call, error):
    runtime = components(conn, [call(), bad_call])
    invoked = []
    for name, implementation in runtime["tools_by_name"].items():
        monkeypatch.setattr(implementation.__class__, "invoke", lambda *args, **kwargs: invoked.append(True))
    result = run_agent(runtime, "Test", [])
    assert result["execution_status"] == "error"
    assert result["error"] == error
    assert result["response"] == SAFE_ERROR_RESPONSE
    assert invoked == []
    assert runtime["llm"].calls == []
    assert all(event["execution_status"] == "not_executed" for event in result["tool_calls"])


@pytest.mark.parametrize("bad", [None, "not-json", [], {"name": "lookup_policy", "args": [], "id": "bad"}])
def test_malformed_call_shape_is_a_safe_error(conn, bad):
    runtime = components(conn, [])
    # model_construct represents a provider/parser violating the expected schema.
    runtime["llm_with_tools"].outcome = AIMessage.model_construct(content="", tool_calls=[bad])
    result = run_agent(runtime, "Test", [])
    assert result["execution_status"] == "error"
    assert result["error"] == "invalid_tool_call"
    assert result["response"] == SAFE_ERROR_RESPONSE
    assert runtime["llm"].calls == []


def test_provider_invalid_tool_calls_are_not_mistaken_for_a_direct_answer(conn):
    runtime = components(conn, [])
    runtime["llm_with_tools"].outcome = AIMessage(content="Try this", invalid_tool_calls=[
        {"name": "lookup_policy", "args": "{broken", "id": "bad", "error": "sensitive parser detail"}
    ])
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "invalid_tool_call"
    assert "sensitive parser detail" not in json.dumps(result)
    assert runtime["llm"].calls == []


def test_tool_batch_limit_prevents_execution(conn):
    runtime = components(conn, [call(call_id=f"call-{index}") for index in range(MAX_TOOL_CALLS + 1)])
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "tool_call_limit_exceeded"
    assert all(event["execution_status"] == "not_executed" for event in result["tool_calls"])
    assert runtime["llm"].calls == []


@pytest.mark.parametrize("stage,error", [
    ("llm_with_tools", "model_call_failed"), ("llm", "final_model_call_failed"),
])
def test_model_failure_has_no_raw_fallback_retry_or_exception_text(conn, caplog, stage, error):
    runtime = components(conn, [call()])
    runtime[stage].outcome = RuntimeError("SECRET API credential https://private.example/error")
    result = run_agent(runtime, "Test", [])
    assert result["execution_status"] == "error"
    assert result["error"] == error
    assert result["response"] == SAFE_ERROR_RESPONSE
    assert "SECRET" not in json.dumps(result) + caplog.text
    if stage == "llm_with_tools":
        assert runtime["llm"].calls == []
    else:
        assert "Transfer Limits" in result["tool_calls"][0]["result"]
        assert "Transfer Limits" not in result["response"]


def test_failed_tool_does_not_expose_exception_or_hide_other_executions(conn, caplog):
    @tool
    def lookup_policy(topic: str) -> str:
        """A failing offline policy backend."""
        raise RuntimeError("SECRET database connection credentials")

    runtime = components(conn, [call(), call("query_account", {}, "self")])
    runtime["tools_by_name"]["lookup_policy"] = lookup_policy
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "tool_execution_failed"
    assert result["response"] == SAFE_ERROR_RESPONSE
    assert [event["execution_status"] for event in result["tool_calls"]] == ["error", "ok"]
    assert "SECRET" not in json.dumps(result) + caplog.text
    assert runtime["llm"].calls == []


def test_missing_backend_identity_is_not_inferred_from_model_arguments(conn):
    @tool
    def query_account(user_id: str) -> str:
        """An incorrectly instrumented backend."""
        return "RAW ACCOUNT PAYLOAD"

    runtime = components(conn, [call("query_account", {"user_id": "USR-PP-001"})])
    runtime["tools_by_name"]["query_account"] = query_account
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "missing_authorization_metadata"
    assert result["tool_calls"][0]["effective_user_id"] is None
    assert result["tool_calls"][0]["execution_status"] == "error"
    assert "RAW ACCOUNT PAYLOAD" not in result["response"]


def test_unexpected_final_tool_request_is_recorded_but_not_executed(conn):
    runtime = components(conn, [call()], final=AIMessage(content="", tool_calls=[
        call("query_account", {}, "extra")]))
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "unexpected_tool_calls"
    assert [event["execution_status"] for event in result["tool_calls"]] == ["ok", "not_executed"]
    assert len(runtime["llm"].calls) == 1


@pytest.mark.parametrize("content", ["", [], [{"type": "text", "text": 12}]])
def test_empty_or_invalid_text_is_not_successful_execution(conn, content):
    runtime = components(conn, [])
    runtime["llm_with_tools"].outcome = AIMessage(content=content)
    result = run_agent(runtime, "Test", [])
    assert result["error"] == "empty_model_response"
    assert result["response"] == SAFE_ERROR_RESPONSE


def test_invalid_mode_is_rejected_before_constructing_a_model(monkeypatch):
    monkeypatch.setattr("agent.ChatOpenAI", lambda **kwargs: pytest.fail("Model creation is premature"))
    with pytest.raises(ValueError, match="invalid_agent_configuration"):
        create_aria_agent(None, "USR-0042", "Standard", "offline", mode="guardde")
