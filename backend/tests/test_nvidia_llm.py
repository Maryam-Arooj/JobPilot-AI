import sys
from pathlib import Path
from unittest import mock

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from backend.services import nvidia_llm as llm
from backend.services.nvidia_llm import LLMResponseError, LLMUnavailableError

KEY = "nvapi-TEST-SECRET-KEY"
BASE = "https://nim.example.test/v1"


def resp(status=200, content="hello", finish="stop", headers=None):
    r = mock.Mock(status_code=status, headers=headers or {})
    r.json.return_value = {"choices": [{"message": {"content": content}, "finish_reason": finish}]}
    return r


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    monkeypatch.setenv("OPENAI_BASE_URL", BASE)
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_FALLBACK_MODEL", raising=False)
    monkeypatch.delenv("NVIDIA_TIMEOUT", raising=False)
    monkeypatch.delenv("NVIDIA_EXTRA_BODY", raising=False)
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)


def assert_safe(err):
    assert KEY not in str(err) and "nim.example.test" not in str(err)


def test_no_key_raises_unavailable(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setattr(llm, "env_paths", [])
    with pytest.raises(LLMUnavailableError):
        llm.call_nvidia_llm("hi")


def test_defaults_model_and_timeout():
    with mock.patch.object(llm.requests, "post", return_value=resp()) as post:
        assert llm.call_nvidia_llm("hi") == "hello"
    kwargs = post.call_args.kwargs
    assert kwargs["json"]["model"] == llm.DEFAULT_MODEL
    assert kwargs["timeout"] == 60.0


def test_env_model_and_timeout(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "vendor/model-a")
    monkeypatch.setenv("NVIDIA_TIMEOUT", "12")
    with mock.patch.object(llm.requests, "post", return_value=resp()) as post:
        llm.call_nvidia_llm("hi")
    assert post.call_args.kwargs["json"]["model"] == "vendor/model-a"
    assert post.call_args.kwargs["timeout"] == 12.0


def test_explicit_timeout_wins(monkeypatch):
    monkeypatch.setenv("NVIDIA_TIMEOUT", "12")
    with mock.patch.object(llm.requests, "post", return_value=resp()) as post:
        llm.call_nvidia_llm("hi", timeout=45)
    assert post.call_args.kwargs["timeout"] == 45


def test_timeout_is_typed_and_safe():
    with mock.patch.object(llm.requests, "post", side_effect=requests.Timeout(f"{BASE}/chat/completions key={KEY}")):
        with pytest.raises(LLMUnavailableError) as e:
            llm.call_nvidia_llm("hi")
    assert "timed out" in str(e.value)
    assert_safe(e.value)


def test_network_error_is_safe():
    with mock.patch.object(llm.requests, "post", side_effect=requests.ConnectionError(f"HTTPSConnectionPool {BASE}")):
        with pytest.raises(LLMUnavailableError) as e:
            llm.call_nvidia_llm("hi")
    assert_safe(e.value)


@pytest.mark.parametrize("status", [429, 500, 503])
def test_retries_once_on_429_and_5xx(status):
    with mock.patch.object(llm.requests, "post", side_effect=[resp(status), resp(content="ok")]) as post:
        assert llm.call_nvidia_llm("hi") == "ok"
    assert post.call_count == 2


def test_gives_up_after_one_retry():
    with mock.patch.object(llm.requests, "post", side_effect=[resp(503), resp(503), resp(content="never")]) as post:
        with pytest.raises(LLMUnavailableError) as e:
            llm.call_nvidia_llm("hi")
    assert post.call_count == 2
    assert "HTTP 503" in str(e.value)
    assert_safe(e.value)


def test_no_retry_on_4xx():
    with mock.patch.object(llm.requests, "post", side_effect=[resp(404), resp(content="never")]) as post:
        with pytest.raises(LLMUnavailableError):
            llm.call_nvidia_llm("hi")
    assert post.call_count == 1


def test_fallback_model_used(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "vendor/primary")
    monkeypatch.setenv("NVIDIA_FALLBACK_MODEL", "vendor/fallback")
    with mock.patch.object(llm.requests, "post", side_effect=[resp(404), resp(content="from fallback")]) as post:
        assert llm.call_nvidia_llm("hi") == "from fallback"
    assert [c.kwargs["json"]["model"] for c in post.call_args_list] == ["vendor/primary", "vendor/fallback"]


def test_empty_content_is_an_error_not_empty_string():
    with mock.patch.object(llm.requests, "post", return_value=resp(content="", finish="length")):
        with pytest.raises(LLMResponseError) as e:
            llm.call_nvidia_llm("hi")
    assert "length" in str(e.value)


def test_call_nvidia_json_strips_fences_and_asks_for_json():
    with mock.patch.object(llm.requests, "post", return_value=resp(content='```json\n{"a": [1, 2]}\n```')) as post:
        assert llm.call_nvidia_json("give json", system_prompt="Be strict.") == {"a": [1, 2]}
    system = post.call_args.kwargs["json"]["messages"][0]["content"]
    assert system.startswith("Be strict.") and "JSON" in system


def test_call_nvidia_json_extracts_from_prose():
    with mock.patch.object(llm.requests, "post", return_value=resp(content='Sure! {"ok": true} Hope that helps.')):
        assert llm.call_nvidia_json("x") == {"ok": True}


def _body(monkeypatch, model="vendor/thinker", extras_map=None, env_extra=None):
    monkeypatch.setenv("NVIDIA_MODEL", model)
    monkeypatch.setattr(llm, "MODEL_EXTRAS", extras_map or {})
    if env_extra is not None:
        monkeypatch.setenv("NVIDIA_EXTRA_BODY", env_extra)
    with mock.patch.object(llm.requests, "post", return_value=resp()) as post:
        llm.call_nvidia_llm("hi", max_tokens=99)
    return post.call_args.kwargs["json"]


def test_builtin_model_extras_applied(monkeypatch):
    body = _body(monkeypatch, extras_map={"vendor/thinker": {"reasoning_effort": "low"}})
    assert body["reasoning_effort"] == "low" and body["max_tokens"] == 99


def test_builtin_extras_only_for_their_model(monkeypatch):
    body = _body(monkeypatch, model="vendor/other", extras_map={"vendor/thinker": {"reasoning_effort": "low"}})
    assert "reasoning_effort" not in body


def test_env_extra_body_global_merges_over_builtin(monkeypatch):
    body = _body(monkeypatch, extras_map={"vendor/thinker": {"reasoning_effort": "low", "top_p": 0.9}},
                 env_extra='{"reasoning_effort": "medium"}')
    assert body["reasoning_effort"] == "medium" and body["top_p"] == 0.9


def test_env_extra_body_per_model_map(monkeypatch):
    env = '{"vendor/thinker": {"chat_template_kwargs": {"enable_thinking": false}}, "vendor/x": {"a": 1}}'
    body = _body(monkeypatch, extras_map={"vendor/thinker": {"reasoning_effort": "low"}}, env_extra=env)
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert "reasoning_effort" not in body and "a" not in body


def test_env_extra_body_invalid_json_ignored(monkeypatch):
    body = _body(monkeypatch, extras_map={"vendor/thinker": {"reasoning_effort": "low"}}, env_extra="{not json")
    assert body["reasoning_effort"] == "low"


def test_extras_cannot_replace_model_or_messages(monkeypatch):
    body = _body(monkeypatch, env_extra='{"model": "evil/model", "messages": [], "temperature": 0.9}')
    assert body["model"] == "vendor/thinker" and body["messages"][-1]["content"] == "hi"
    assert body["temperature"] == 0.9


def test_fallback_uses_its_own_extras(monkeypatch):
    monkeypatch.setenv("NVIDIA_MODEL", "vendor/primary")
    monkeypatch.setenv("NVIDIA_FALLBACK_MODEL", "vendor/fallback")
    monkeypatch.setattr(llm, "MODEL_EXTRAS", {"vendor/primary": {"p": 1}, "vendor/fallback": {"f": 2}})
    with mock.patch.object(llm.requests, "post", side_effect=[resp(404), resp(content="ok")]) as post:
        llm.call_nvidia_llm("hi")
    first, second = (c.kwargs["json"] for c in post.call_args_list)
    assert first.get("p") == 1 and "f" not in first
    assert second.get("f") == 2 and "p" not in second


def _json_call_body(monkeypatch, model, json_call=True):
    monkeypatch.setenv("NVIDIA_MODEL", model)
    with mock.patch.object(llm.requests, "post", return_value=resp(content='{"x": 1}')) as post:
        (llm.call_nvidia_json if json_call else llm.call_nvidia_llm)("x")
    return post.call_args.kwargs["json"]


def test_json_object_format_only_for_verified_models(monkeypatch):
    assert _json_call_body(monkeypatch, "nvidia/nemotron-3.5-lightning-30b-a3b")["response_format"] == {"type": "json_object"}
    assert "response_format" not in _json_call_body(monkeypatch, "openai/gpt-oss-20b")


def test_json_object_format_not_added_to_plain_calls(monkeypatch):
    assert "response_format" not in _json_call_body(monkeypatch, "nvidia/nemotron-3.5-lightning-30b-a3b", json_call=False)


def test_builtin_extras_for_measured_models(monkeypatch):
    assert _json_call_body(monkeypatch, "openai/gpt-oss-20b")["reasoning_effort"] == "low"
    body = _json_call_body(monkeypatch, "nvidia/nemotron-3.5-lightning-30b-a3b")
    assert body["chat_template_kwargs"] == {"enable_thinking": False}


def test_call_nvidia_json_invalid_raises():
    with mock.patch.object(llm.requests, "post", return_value=resp(content="not json at all {broken")):
        with pytest.raises(LLMResponseError):
            llm.call_nvidia_json("x")
