"""Tests for the LLM port. HTTP is mocked."""
from unittest.mock import MagicMock

import pytest
import requests

from kbase.agent.llm import AnthropicLLM, OfflineLLM, OpenAICompatibleLLM, make_llm, parse_json
from kbase.config import Settings


def response(status=200, body=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.text = text
    if isinstance(body, Exception):
        resp.json.side_effect = body
    else:
        resp.json.return_value = body
    return resp


class TestParseJson:
    @pytest.mark.parametrize("text,expected", [
        ('{"a": 1}', {"a": 1}),
        ('```json\n{"a": 1}\n```', {"a": 1}),
        ('Sure! {"a": 2} hope that helps', {"a": 2}),
        ("[1, 2]", None),
        ("no json", None),
        ("{broken", None),
        ("", None),
        (None, None),
        ('x {"a": } y', None),
        ('x ["a"] y {"b": [1]} z', {"b": [1]}),
    ])
    def test_cases(self, text, expected):
        assert parse_json(text) == expected


class TestOffline:
    def test_does_nothing(self):
        llm = OfflineLLM()
        assert not llm.enabled and llm.complete("s", "p") is None and llm.complete_json("s", "p") is None
        assert llm.describe() == {"provider": "offline", "enabled": False}


class TestAnthropic:
    def make(self, resp):
        session = MagicMock()
        session.post.return_value = resp
        return AnthropicLLM(api_key="k", model="claude-sonnet-5-5", base_url="https://api.anthropic.com/",
                            session=session), session

    def test_request_shape_and_json(self):
        llm, session = self.make(response(body={"content": [{"type": "text", "text": '{"doc_id": "KB-1"}'}]}))
        assert llm.complete_json("sys", "prompt") == {"doc_id": "KB-1"}
        url = session.post.call_args[0][0]
        kwargs = session.post.call_args[1]
        assert url == "https://api.anthropic.com/v1/messages"
        assert kwargs["headers"]["x-api-key"] == "k" and kwargs["headers"]["anthropic-version"]
        assert kwargs["json"]["model"] == "claude-sonnet-5-5"
        assert kwargs["json"]["messages"] == [{"role": "user", "content": "prompt"}]

    def test_http_error(self):
        llm, _ = self.make(response(status=429, text="rate limited"))
        assert llm.complete("s", "p") is None and "429" in llm.last_error

    def test_network_error(self):
        llm, session = self.make(response())
        session.post.side_effect = requests.ConnectionError("down")
        assert llm.complete("s", "p") is None and "ConnectionError" in llm.last_error

    def test_bad_body(self):
        llm, _ = self.make(response(body=ValueError("nope")))
        assert llm.complete("s", "p") is None

    def test_no_text_blocks(self):
        llm, _ = self.make(response(body={"content": []}))
        assert llm.complete("s", "p") is None

    def test_non_json_reply_sets_error(self):
        llm, _ = self.make(response(body={"content": [{"type": "text", "text": "hello"}]}))
        assert llm.complete_json("s", "p") is None and "not valid JSON" in llm.last_error

    def test_describe(self):
        llm, _ = self.make(response())
        assert llm.describe()["model"] == "claude-sonnet-5-5"


class TestOpenAI:
    def make(self, resp, header="Authorization"):
        session = MagicMock()
        session.post.return_value = resp
        return OpenAICompatibleLLM(api_key="k", model="gpt-x", base_url="https://h/v1", auth_header=header,
                                   session=session), session

    def test_bearer(self):
        llm, session = self.make(response(body={"choices": [{"message": {"content": "hi"}}]}))
        assert llm.complete("s", "p") == "hi"
        assert session.post.call_args[1]["headers"] == {"Authorization": "Bearer k"}
        assert session.post.call_args[0][0] == "https://h/v1/chat/completions"

    def test_api_key_header(self):
        llm, session = self.make(response(body={"choices": [{"message": {"content": "hi"}}]}), header="api-key")
        llm.complete("s", "p")
        assert session.post.call_args[1]["headers"] == {"api-key": "k"}

    def test_missing_choices(self):
        llm, _ = self.make(response(body={}))
        assert llm.complete("s", "p") is None and "no choices" in llm.last_error

    def test_http_error(self):
        llm, _ = self.make(response(status=500))
        assert llm.complete("s", "p") is None


class TestFactory:
    def test_offline_without_key(self):
        assert isinstance(make_llm(Settings.from_env({"LLM_PROVIDER": "anthropic"})), OfflineLLM)

    def test_anthropic(self):
        llm = make_llm(Settings.from_env({"LLM_PROVIDER": "anthropic", "LLM_API_KEY": "k"}))
        assert isinstance(llm, AnthropicLLM) and llm.base_url == "https://api.anthropic.com"

    def test_openai(self):
        llm = make_llm(Settings.from_env({"LLM_PROVIDER": "openai", "LLM_API_KEY": "k",
                                          "LLM_BASE_URL": "https://x/openai/v1", "LLM_AUTH_HEADER": "api-key"}))
        assert isinstance(llm, OpenAICompatibleLLM) and llm.auth_header == "api-key"
