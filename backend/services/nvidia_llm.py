"""Shared NVIDIA NIM chat client.

Configuration (backend/.env):
    OPENAI_API_KEY         NVIDIA NIM key (required)
    OPENAI_BASE_URL        default https://integrate.api.nvidia.com/v1
    NVIDIA_MODEL           primary model (default: DEFAULT_MODEL below)
    NVIDIA_FALLBACK_MODEL  optional second model, tried once if the primary fails
    NVIDIA_TIMEOUT         seconds per request, default 60
    NVIDIA_EXTRA_BODY      optional JSON merged into every request body, e.g.
                           {"reasoning_effort": "low"}; or keyed by model id,
                           e.g. {"openai/gpt-oss-20b": {"reasoning_effort": "low"}}.
                           Overrides the built-in MODEL_EXTRAS for that model.

Errors are typed and never silent: LLMUnavailableError (no key, timeout, network or HTTP
error) and LLMResponseError (empty or non-JSON output). Error messages name the model and
HTTP status only; keys and URLs never appear in them.
"""
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

# Ensure .env is loaded from backend directory or current working directory
env_paths = [
    os.path.join(os.path.dirname(__file__), "..", ".env"),
    os.path.join(os.getcwd(), "backend", ".env"),
    os.path.join(os.getcwd(), ".env"),
]
for p in env_paths:
    if os.path.exists(p):
        load_dotenv(p)
        break

logger = logging.getLogger(__name__)

# Best working model from backend/scripts/check_providers.py (2026-10-15). Override with NVIDIA_MODEL.
DEFAULT_MODEL = "meta/llama-3.2-11b-vision-instruct"
DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_TIMEOUT = 60.0
RETRY_STATUSES = {429, 500, 502, 503, 504}
RETRY_BACKOFF_SECONDS = 2.0
JSON_ONLY_INSTRUCTION = "Respond with one valid JSON value only: no prose, no markdown, no code fences."

# Per-model request fields, measured with backend/scripts/bench_nvidia_extraction.py (2026-10-15).
# Reasoning models are unusably slow with full thinking; these settings return grounded JSON in
# ~10-40 s. A "/no_think" system prefix did NOT work for the Nemotron models (they still think).
MODEL_EXTRAS: Dict[str, Dict[str, Any]] = {
    "openai/gpt-oss-20b": {"reasoning_effort": "low"},
    "nvidia/nemotron-3.5-lightning-30b-a3b": {"chat_template_kwargs": {"enable_thinking": False}},
    "nvidia/nemotron-3-super-120b-a12b": {"chat_template_kwargs": {"enable_thinking": False}},
}
# Models verified to accept response_format={"type": "json_object"}; used by call_nvidia_json only.
JSON_OBJECT_MODELS = {"nvidia/nemotron-3.5-lightning-30b-a3b", "nvidia/nemotron-3-super-120b-a12b"}


class LLMError(Exception):
    """Base class for LLM client errors. Messages are safe to show to users."""


class LLMUnavailableError(LLMError):
    """No key configured, or the request timed out / failed / returned an HTTP error."""


class LLMResponseError(LLMError):
    """The model answered, but with empty content or content that is not valid JSON."""


def get_nvidia_api_key() -> str:
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        for p in env_paths:
            if os.path.exists(p):
                load_dotenv(p)
                key = os.getenv("OPENAI_API_KEY", "").strip()
                if key:
                    break
    return key


def get_nvidia_base_url() -> str:
    return (os.getenv("OPENAI_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def get_models() -> List[str]:
    primary = (os.getenv("NVIDIA_MODEL") or DEFAULT_MODEL).strip()
    fallback = (os.getenv("NVIDIA_FALLBACK_MODEL") or "").strip()
    return [primary] + ([fallback] if fallback and fallback != primary else [])


def get_extra_body(model: str) -> Dict[str, Any]:
    """Request fields for this model: built-in MODEL_EXTRAS, overridden by NVIDIA_EXTRA_BODY."""
    extras: Dict[str, Any] = dict(MODEL_EXTRAS.get(model, {}))
    raw = os.getenv("NVIDIA_EXTRA_BODY", "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
        except ValueError:
            logger.warning("Ignoring NVIDIA_EXTRA_BODY: not valid JSON")
            parsed = None
        if isinstance(parsed, dict):
            per_model = bool(parsed) and all("/" in k and isinstance(v, dict) for k, v in parsed.items())
            if per_model:
                if model in parsed:
                    extras = dict(parsed[model])
            else:
                extras.update(parsed)
        elif parsed is not None:
            logger.warning("Ignoring NVIDIA_EXTRA_BODY: expected a JSON object")
    # Never let extras replace the core request fields.
    for reserved in ("model", "messages"):
        extras.pop(reserved, None)
    return extras


def get_timeout() -> float:
    raw = os.getenv("NVIDIA_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_TIMEOUT
    try:
        value = float(raw)
        if value > 0:
            return value
    except ValueError:
        pass
    logger.warning("Ignoring invalid NVIDIA_TIMEOUT=%r; using %ss", raw, DEFAULT_TIMEOUT)
    return DEFAULT_TIMEOUT


def _retry_delay(resp: requests.Response) -> float:
    try:
        return min(10.0, max(0.0, float(resp.headers.get("Retry-After", RETRY_BACKOFF_SECONDS))))
    except ValueError:
        return RETRY_BACKOFF_SECONDS


def _complete(model: str, messages: list, temperature: float, max_tokens: int,
              timeout: float, api_key: str, base_url: str, json_mode: bool = False) -> str:
    """One model: a single request, retried once on 429/5xx."""
    extras = get_extra_body(model)
    if json_mode and model in JSON_OBJECT_MODELS:
        extras.setdefault("response_format", {"type": "json_object"})
    body = {"temperature": temperature, "max_tokens": max_tokens, **extras,
            "model": model, "messages": messages}
    for attempt in (1, 2):
        try:
            resp = requests.post(
                f"{base_url}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                timeout=timeout,
            )
        except requests.Timeout:
            raise LLMUnavailableError(f"NVIDIA model {model} timed out after {timeout:.0f}s")
        except requests.RequestException as e:
            # str(e) contains the request URL; log the type only.
            raise LLMUnavailableError(f"NVIDIA model {model} could not be reached ({type(e).__name__})")

        if resp.status_code in RETRY_STATUSES and attempt == 1:
            delay = _retry_delay(resp)
            logger.warning("NVIDIA model %s returned HTTP %s; retrying in %.1fs", model, resp.status_code, delay)
            time.sleep(delay)
            continue
        if resp.status_code != 200:
            logger.warning("NVIDIA model %s returned HTTP %s", model, resp.status_code)
            raise LLMUnavailableError(f"NVIDIA model {model} returned HTTP {resp.status_code}")

        try:
            choice = (resp.json().get("choices") or [{}])[0]
        except (ValueError, AttributeError):
            raise LLMResponseError(f"NVIDIA model {model} returned a non-JSON HTTP body")
        content = ((choice.get("message") or {}).get("content") or "").strip()
        if not content:
            raise LLMResponseError(
                f"NVIDIA model {model} returned no content (finish_reason={choice.get('finish_reason')!r})"
            )
        return content
    raise LLMUnavailableError(f"NVIDIA model {model} failed after retry")  # pragma: no cover


def call_nvidia_llm(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 1500,
    model_override: Optional[str] = None,
    timeout: Optional[float] = None,
    json_mode: bool = False,
) -> str:
    """Return the model's text. Raises LLMUnavailableError / LLMResponseError; never returns ''."""
    api_key = get_nvidia_api_key()
    if not api_key:
        raise LLMUnavailableError("NVIDIA API key is not configured (OPENAI_API_KEY in backend/.env)")

    messages = ([{"role": "system", "content": system_prompt}] if system_prompt else []) + [
        {"role": "user", "content": prompt}
    ]
    models = [model_override] if model_override else get_models()
    request_timeout = timeout if timeout is not None else get_timeout()
    base_url = get_nvidia_base_url()

    last_error: Optional[LLMError] = None
    for model in models:
        try:
            return _complete(model, messages, temperature, max_tokens, request_timeout, api_key, base_url, json_mode)
        except LLMError as e:
            logger.warning("NVIDIA call failed: %s", e)
            last_error = e
    raise last_error  # type: ignore[misc]


def parse_json_response(raw: str) -> Any:
    """Strip ```json fences / surrounding prose and parse. Raises LLMResponseError."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    # Fall back to the outermost object/array inside surrounding prose.
    starts = [i for i in (text.find("{"), text.find("[")) if i != -1]
    if starts:
        start = min(starts)
        end = text.rfind("}" if text[start] == "{" else "]")
        if end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                pass
    raise LLMResponseError("The language model returned invalid JSON")


def call_nvidia_json(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    model_override: Optional[str] = None,
    timeout: Optional[float] = None,
) -> Any:
    """Ask for JSON only and return the parsed value. Raises LLMUnavailableError / LLMResponseError."""
    system = f"{system_prompt}\n\n{JSON_ONLY_INSTRUCTION}" if system_prompt else JSON_ONLY_INSTRUCTION
    raw = call_nvidia_llm(prompt, system_prompt=system, temperature=temperature, max_tokens=max_tokens,
                          model_override=model_override, timeout=timeout, json_mode=True)
    return parse_json_response(raw)
