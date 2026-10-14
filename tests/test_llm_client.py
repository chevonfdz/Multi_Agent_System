"""The optional Claude client, checked against a local mock of the Messages API (no real calls)."""
import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.llm.client import AnthropicLLM, LLMError, build_llm


class MockAPI(BaseHTTPRequestHandler):
    requests: list = []
    reply_text = "{}"
    status = 200
    stop_reason = "end_turn"

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        MockAPI.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if MockAPI.status != 200:
            payload = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
        else:
            payload = {"id": "msg_test", "type": "message", "role": "assistant", "model": body["model"],
                       "content": [{"type": "text", "text": MockAPI.reply_text}],
                       "stop_reason": MockAPI.stop_reason, "stop_sequence": None,
                       "usage": {"input_tokens": 10, "output_tokens": 5}}
        data = json.dumps(payload).encode()
        self.send_response(MockAPI.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


@pytest.fixture
def mock_api(monkeypatch):
    MockAPI.requests, MockAPI.status, MockAPI.stop_reason = [], 200, "end_turn"
    server = HTTPServer(("127.0.0.1", 0), MockAPI)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    yield MockAPI
    server.shutdown()


def test_json_request_shape_and_parsing(mock_api):
    mock_api.reply_text = json.dumps({"tasks": []})
    llm = AnthropicLLM(model="claude-opus-5-5", timeout=10)
    result = asyncio.run(llm.complete_json("system prompt", "user text", {"type": "object"}))
    assert result == {"tasks": []}
    sent = mock_api.requests[0]
    assert sent["path"].startswith("/v1/messages")
    assert sent["body"]["model"] == "claude-opus-5-5"
    assert sent["body"]["system"] == "system prompt"
    assert sent["body"]["output_config"]["effort"] == "low"
    assert sent["body"]["output_config"]["format"]["type"] == "json_schema"
    assert sent["body"]["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in sent["headers"].get("anthropic-beta", "")


def test_text_completion_and_refusal(mock_api):
    mock_api.reply_text = "Here's what I found"
    llm = AnthropicLLM(model="claude-opus-5-5", timeout=10)
    assert asyncio.run(llm.complete("s", "u")) == "Here's what I found"
    mock_api.stop_reason = "refusal"
    with pytest.raises(LLMError):
        asyncio.run(llm.complete("s", "u"))


def test_bad_key_disables_the_llm(mock_api):
    mock_api.status = 401
    llm = AnthropicLLM(model="claude-opus-5-5", timeout=10)
    with pytest.raises(LLMError):
        asyncio.run(llm.complete("s", "u"))
    assert not llm.enabled
    calls = len(mock_api.requests)
    with pytest.raises(LLMError):
        asyncio.run(llm.complete("s", "u"))
    assert len(mock_api.requests) == calls        # no further API calls once disabled


def test_build_llm_defaults_to_rules():
    assert not build_llm("none", "x", 5).enabled
    assert not build_llm("unknown-provider", "x", 5).enabled
