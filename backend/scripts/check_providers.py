"""Read-only live check of every external provider JobPilot AI uses.

Usage (from the repo root):
    backend\\.venv\\Scripts\\python.exe backend\\scripts\\check_providers.py

Reads backend/.env. Never prints key values: every response or error text is scrubbed
of all secrets before it is shown. Costs: a few tiny NVIDIA completions plus two ~1500-token
JSON completions; SerpAPI account.json (no search credits); Apify/Firecrawl metadata reads
(no actor runs, no scrapes); one Google token request with a dummy code.
"""
import json
import re
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV = {k: (v or "").strip() for k, v in dotenv_values(Path(__file__).resolve().parent.parent / ".env").items()}
SECRETS = sorted({v for k, v in ENV.items() if v and len(v) >= 8 and any(
    s in k.upper() for s in ("KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL"))}, key=len, reverse=True)

LISTED_MODELS = ["meta/llama-3.2-11b-vision-instruct", "google/diffusiongemma-26b-a4b-it", "openai/gpt-oss-20b"]
# Strong instruction/chat models to try, best first. /models lists models this account may not
# be able to call (404 "Not found for account"), so we probe until MAX_STRONG of them answer.
PREFERRED = [
    "meta/llama-3.3-70b-instruct", "nvidia/nemotron-3-super-120b-a12b", "deepseek-ai/deepseek-v4.1-flash",
    "moonshotai/kimi-k2.6", "z-ai/glm-5.3-flash", "z-ai/glm-5.3", "google/gemma-4-31b-it",
    "meta/llama-3.2-90b-vision-instruct", "nvidia/llama-3.1-nemotron-ultra-253b-v1", "nvidia/nemotron-3.5-lightning-30b-a3b",
    "mistralai/mistral-large-2-instruct", "nvidia/llama-3.1-nemotron-70b-instruct", "nvidia/llama-3.1-nemotron-51b-instruct",
    "google/gemma-3-12b-it", "nv-mistralai/mistral-nemo-12b-instruct",
]
MAX_STRONG = 3


def scrub(text) -> str:
    text = str(text)
    for s in SECRETS:
        text = text.replace(s, "<redacted>")
    return text


def line(status: str, name: str, info: str = "") -> None:
    print(f"  [{status:4}] {name}" + (f"  {scrub(info)}" if info else ""), flush=True)


def call(method: str, url: str, timeout: float = 20, **kw):
    """Returns (http_status or None, elapsed_ms, parsed_json_or_text, error_text)."""
    t0 = time.perf_counter()
    try:
        r = requests.request(method, url, timeout=timeout, **kw)
        ms = int((time.perf_counter() - t0) * 1000)
        try:
            body = r.json()
        except ValueError:
            body = r.text[:300]
        return r.status_code, ms, body, None
    except requests.RequestException as e:
        return None, int((time.perf_counter() - t0) * 1000), None, f"{type(e).__name__}"


def short(body, n=160) -> str:
    return scrub(json.dumps(body) if not isinstance(body, str) else body)[:n]


def nim_error(body) -> str:
    """Error title only; drops account identifiers NVIDIA embeds in 404 details."""
    if isinstance(body, dict):
        err = body.get("error")
        msg = body.get("title") or body.get("detail") or (err.get("message") if isinstance(err, dict) else err) or ""
        return re.sub(r"\s*for account '[^']*'|Function '[^']*':?\s*", "", scrub(msg))[:120]
    return short(body, 120)


def nim_reply(body):
    """(content, finish_reason, has_reasoning) from a chat completion body."""
    choice = ((body or {}).get("choices") or [{}])[0] if isinstance(body, dict) else {}
    msg = choice.get("message") or {}
    return (msg.get("content") or ""), choice.get("finish_reason"), bool(msg.get("reasoning_content") or msg.get("reasoning"))


# ---------------------------------------------------------------- NVIDIA
def check_nvidia():
    print("\nNVIDIA NIM")
    key, base = ENV.get("OPENAI_API_KEY", ""), (ENV.get("OPENAI_BASE_URL") or "https://integrate.api.nvidia.com/v1").rstrip("/")
    if not key:
        line("FAIL", "OPENAI_API_KEY", "not set")
        return
    h = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    st, ms, body, err = call("GET", f"{base}/models", headers=h)
    ids = [m.get("id") for m in (body or {}).get("data", [])] if isinstance(body, dict) else []
    line("OK" if st == 200 and ids else "FAIL", "GET /models", f"HTTP {st} {ms}ms, {len(ids)} models" + (f" {err}" if err else ""))
    results = {}

    def probe(model) -> bool:
        listed = "listed" if model in ids else "NOT in /models"
        st, ms, body, err = call("POST", f"{base}/chat/completions", headers=h, timeout=60, json={
            "model": model, "max_tokens": 8, "temperature": 0,
            "messages": [{"role": "user", "content": "Reply with the single word: ready"}]})
        text, finish, reasoning = nim_reply(body) if st == 200 else ("", None, False)
        thinking = st == 200 and not text.strip() and finish == "length" and reasoning
        ok = (st == 200 and bool(text.strip())) or thinking
        results[model] = (ok, ms, thinking)
        if st == 200 and text.strip():
            line("OK", f"chat {model}", f"HTTP {st} {ms}ms ({listed}) reply={text.strip()[:30]!r}")
        elif thinking:
            line("OK", f"chat {model}", f"HTTP {st} {ms}ms ({listed}) reachable; reasoning model spent the 8 tokens thinking (no answer at this budget)")
        elif st == 200:
            line("FAIL", f"chat {model}", f"HTTP {st} {ms}ms ({listed}) empty content, finish_reason={finish!r}")
        else:
            line("FAIL", f"chat {model}", f"HTTP {st} {ms}ms ({listed}) {err or nim_error(body)}")
        return ok

    print("         models currently configured in code:")
    for model in LISTED_MODELS:
        probe(model)
    print(f"         strong instruction models (trying in order until {MAX_STRONG} answer):")
    strong = []
    for model in PREFERRED:
        if model not in ids:
            continue
        if probe(model):
            strong.append(model)
        if len(strong) >= MAX_STRONG:
            break

    # Best 2 = fastest-responding strong models; fall back to the configured ones.
    working = sorted(strong, key=lambda m: results[m][1]) or [m for m in LISTED_MODELS if results.get(m, (False,))[0]]
    print(f"         JSON test candidates (fastest strong first): {working[:2] or 'none'}")
    prompt = ("Return ONLY a JSON object, no prose, no code fences: "
              '{"roles": [ ... ]} with exactly 20 items, each {"title": str, "skills": [5 short strings], '
              '"summary": "two sentences"} describing realistic software/data job roles.')
    for model in working[:2]:
        # Reasoning models spend tokens thinking before they answer, so give them headroom.
        budget = 4096 if results[model][2] else 1600
        st, ms, body, err = call("POST", f"{base}/chat/completions", headers=h, timeout=180, json={
            "model": model, "max_tokens": budget, "temperature": 0.2,
            "messages": [{"role": "system", "content": "You output strict JSON only."},
                         {"role": "user", "content": prompt}]})
        text, finish, _ = nim_reply(body) if st == 200 else ("", None, False)
        usage = (body.get("usage") or {}) if st == 200 and isinstance(body, dict) else {}
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
        try:
            n = len(json.loads(cleaned[cleaned.find("{"): cleaned.rfind("}") + 1]).get("roles", []))
            parsed = f"valid JSON, {n} roles"
        except Exception:
            parsed = "INVALID JSON" if text else "no content"
        toks = usage.get("completion_tokens")
        rate = f", {toks / (ms / 1000):.0f} tok/s" if toks and ms else ""
        line("OK" if st == 200 and parsed.startswith("valid") else "FAIL", f"json ~1500 tok {model}",
             f"HTTP {st} {ms / 1000:.1f}s, max_tokens={budget}, completion_tokens={toks}{rate}, finish_reason={finish!r}, {parsed}"
             + (f" {err}" if err else "") + ("" if st == 200 else f" {nim_error(body)}"))


# ---------------------------------------------------------------- SerpAPI
def check_serp():
    print("\nSerpAPI (account.json, no search credits used)")
    a, b = ENV.get("SERPAPI_KEY", ""), ENV.get("SERP_API_KEY", "")
    if a and b:
        print(f"         SERPAPI_KEY and SERP_API_KEY are {'the same key' if a == b else 'DIFFERENT keys'}")
    for name in ("SERPAPI_KEY", "SERP_API_KEY"):
        key = ENV.get(name, "")
        if not key:
            line("FAIL", name, "not set")
            continue
        st, ms, body, err = call("GET", "https://serpapi.com/account.json", params={"api_key": key})
        if st == 200 and isinstance(body, dict) and not body.get("error"):
            line("OK", name, f"HTTP {st} {ms}ms plan={body.get('plan_name')!r} searches_per_month={body.get('searches_per_month')} "
                 f"plan_searches_left={body.get('plan_searches_left')} total_searches_left={body.get('total_searches_left')} "
                 f"this_month_usage={body.get('this_month_usage')}")
        else:
            line("FAIL", name, f"HTTP {st} {ms}ms {err or short(body)}")


# ---------------------------------------------------------------- Apify
def check_apify():
    print("\nApify (metadata only, no runs started)")
    names = [n for n in ("APIFY_API_TOKEN", "APIFY_API_KEY") if ENV.get(n)]
    if not names:
        line("FAIL", "APIFY_API_TOKEN", "not set")
        return
    if len(names) == 2:
        print(f"         APIFY_API_TOKEN and APIFY_API_KEY are {'the same' if ENV[names[0]] == ENV[names[1]] else 'DIFFERENT'}")
    token = ENV[names[0]]
    h = {"Authorization": f"Bearer {token}"}
    st, ms, body, err = call("GET", "https://api.apify.com/v2/users/me", headers=h)
    d = (body or {}).get("data", {}) if isinstance(body, dict) else {}
    plan = d.get("plan") or {}
    line("OK" if st == 200 and d else "FAIL", f"users/me ({names[0]})",
         f"HTTP {st} {ms}ms username={d.get('username')!r} plan={plan.get('id') or plan.get('description')!r}" + (f" {err or ''}" if st != 200 else ""))

    actor = ENV.get("APIFY_ACTOR_ID", "")
    if not actor:
        line("FAIL", "APIFY_ACTOR_ID", "not set")
        return
    slug = actor.replace("/", "~")
    st, ms, body, err = call("GET", f"https://api.apify.com/v2/acts/{slug}", headers=h)
    a = (body or {}).get("data", {}) if isinstance(body, dict) else {}
    line("OK" if st == 200 and a else "FAIL", f"actor {actor}",
         f"HTTP {st} {ms}ms title={a.get('title')!r} isPublic={a.get('isPublic')}" + ("" if st == 200 else f" {err or short(body)}"))
    if not a:
        return
    build_id = ((a.get("taggedBuilds") or {}).get("latest") or {}).get("buildId")
    if build_id:
        st, ms, body, err = call("GET", f"https://api.apify.com/v2/actor-builds/{build_id}", headers=h)
        bd = (body or {}).get("data", {}) if isinstance(body, dict) else {}
        schema = bd.get("inputSchema") or ((bd.get("actorDefinition") or {}).get("input"))
        if isinstance(schema, str):
            try:
                schema = json.loads(schema)
            except ValueError:
                schema = None
        if isinstance(schema, dict):
            props = schema.get("properties", {})
            line("OK", "latest build input schema", f"HTTP {st} {ms}ms build={bd.get('buildNumber')} "
                 f"required={schema.get('required', [])}")
            for pname, p in props.items():
                default = p.get("default", p.get("prefill"))
                print(f"           - {pname}: {p.get('type')}" + (f" (default/prefill={json.dumps(default)[:60]})" if default is not None else "")
                      + (f" — {str(p.get('title') or p.get('description') or '')[:70]}"))
        else:
            line("FAIL", "latest build input schema", f"HTTP {st} {ms}ms no inputSchema in build")
    else:
        line("FAIL", "latest build", "actor has no 'latest' tagged build")

    st, ms, body, err = call("GET", f"https://api.apify.com/v2/acts/{slug}/runs", headers=h, params={"limit": 5, "desc": 1})
    runs = ((body or {}).get("data") or {}).get("items", []) if isinstance(body, dict) else []
    line("OK" if st == 200 else "FAIL", "last 5 runs (this account)", f"HTTP {st} {ms}ms, {len(runs)} found")
    for r in runs:
        print(f"           - {r.get('startedAt')} status={r.get('status')} finished={r.get('finishedAt')} "
              f"usageUsd={r.get('usageTotalUsd')}")


# ---------------------------------------------------------------- Firecrawl
def check_firecrawl():
    print("\nFirecrawl")
    key = ENV.get("FIRECRAWL_API_KEY", "")
    if not key:
        line("FAIL", "FIRECRAWL_API_KEY", "not set")
        return
    st, ms, body, err = call("GET", "https://api.firecrawl.dev/v1/team/credit-usage", headers={"Authorization": f"Bearer {key}"})
    d = (body or {}).get("data", body) if isinstance(body, dict) else {}
    ok = st == 200 and isinstance(body, dict) and body.get("success", True)
    line("OK" if ok else "FAIL", "team/credit-usage", f"HTTP {st} {ms}ms {short(d, 200)}" + (f" {err}" if err else ""))


# ---------------------------------------------------------------- Google OAuth
def check_google():
    print("\nGoogle OAuth (dummy code; invalid_grant means the client id/secret are valid)")
    cid, secret = ENV.get("GOOGLE_CLIENT_ID", ""), ENV.get("GOOGLE_CLIENT_SECRET", "")
    if not cid or not secret:
        line("FAIL", "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET", "not set")
        return
    st, ms, body, err = call("POST", "https://oauth2.googleapis.com/token", data={
        "code": "dummy-code-for-credential-check", "client_id": cid, "client_secret": secret,
        "redirect_uri": ENV.get("GOOGLE_REDIRECT_URI") or "http://localhost:3000/api/auth/callback/google",
        "grant_type": "authorization_code"})
    e = (body or {}).get("error") if isinstance(body, dict) else None
    line("OK" if e == "invalid_grant" else "FAIL", "token endpoint",
         f"HTTP {st} {ms}ms error={e!r} ({'credentials valid' if e == 'invalid_grant' else (body or {}).get('error_description', err) if isinstance(body, dict) else err})")


if __name__ == "__main__":
    print("JobPilot AI provider check (values from backend/.env; keys are never printed)")
    for fn in (check_nvidia, check_serp, check_apify, check_firecrawl, check_google):
        try:
            fn()
        except Exception as ex:  # keep going; one provider failing must not hide the others
            line("FAIL", fn.__name__, f"unexpected {type(ex).__name__}: {scrub(ex)[:200]}")
    sys.exit(0)
