"""Step 2: LLM se requirements, buying signals aur website ki kamiyan nikalna.
Provider switchable hai: Gemini (free), Groq (free), Claude (paid), ya offline rules.
"""
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests

SYSTEM_PROMPT = """You analyze business text for a B2B sales team.
The text is either a post (forum/social/directory) or the text of a company website.
Return ONLY a JSON object, no extra text, with these keys:
- "has_requirement": true/false (does the company need a product/service?)
- "requirement": short summary of what they need ("" if none)
- "industry": best-guess industry
- "buying_signals": list of short strings (budget, urgency, deadline, expansion, hiring, pain point)
- "website_gaps": list of missing things that are clearly visible in the text
  (e.g. no online ordering, no contact form, no WhatsApp link). [] if text is not a website.
- "urgency": "low" | "medium" | "high"
- "outreach_angle": one sentence on how to open the conversation
The text may be cut off at the end because of length limits: never report that as a problem.
If the input has a "Special focus", put your findings about it in "website_gaps".
Only use facts present in the text. Never invent anything."""


def _parse_json(text):
    """Model kabhi ```json fences laga deta hai - unhein hata kar parse karein."""
    text = re.sub(r"```(?:json)?", "", text).strip()
    return json.loads(text)


def _user_text(listing):
    focus = f"\nSpecial focus: {listing['focus']}" if listing.get("focus") else ""
    return (f"Company: {listing['company']}\nSource: {listing['source']}{focus}\n"
            f"Text: {listing['text']}")


def _post_with_retry(url, **kwargs):
    """
    503 (server busy): 2 dafa ruk kar dobara.
    429 (limit poori): sirf EK dafa retry; agar 'per day' wali limit ho to foran ruk jao.
    Ziyada retry karne se limit aur jaldi poori hoti hai.
    """
    waits_503 = [5, 15]
    tried_429 = False
    attempt_503 = 0
    while True:
        resp = requests.post(url, timeout=60, **kwargs)
        code = resp.status_code
        if code == 429:
            body = resp.text[:300]
            daily = any(w in body.lower() for w in ("per day", "tpd", "rpd", "daily"))
            if daily or tried_429:
                raise requests.HTTPError(f"429 limit poori (retry se faida nahi): {body}")
            tried_429 = True
            wait = min(int(resp.headers.get("retry-after", 20) or 20), 40)
            print(f"[429] limit lagi, {wait}s baad ek dafa dobara... ({body[:120]})")
            time.sleep(wait)
            continue
        if code in (500, 502, 503, 504) and attempt_503 < len(waits_503):
            print(f"[retry] server busy ({code}), {waits_503[attempt_503]}s baad dobara...")
            time.sleep(waits_503[attempt_503])
            attempt_503 += 1
            continue
        resp.raise_for_status()
        return resp.json()


def _call_gemini(user_text):
    models = [os.getenv("GEMINI_MODEL", "gemini-2.5-flash")]
    models += [m.strip() for m in os.getenv("GEMINI_FALLBACK_MODELS", "").split(",") if m.strip()]
    last_error = None
    for model in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        try:
            data = _post_with_retry(
                url,
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json={
                    "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
                    "contents": [{"role": "user", "parts": [{"text": user_text}]}],
                    "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
                },
            )
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            print(f"[warning] gemini model '{model}' fail: {e}")
            last_error = e
    raise last_error


def _call_groq(user_text):
    data = _post_with_retry(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                         {"role": "user", "content": user_text}],
        },
    )
    return data["choices"][0]["message"]["content"]


def _call_claude(user_text):
    import anthropic  # lazy import: sirf Claude use karne par zaroori
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5"),
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_text}],
    )
    return msg.content[0].text


CALLERS = {"gemini": _call_gemini, "groq": _call_groq, "claude": _call_claude}


def pick_provider():
    forced = os.getenv("LLM_PROVIDER", "").lower()
    if forced in ("gemini", "groq", "claude", "offline"):
        return forced
    if os.getenv("GEMINI_API_KEY"):
        return "gemini"
    if os.getenv("GROQ_API_KEY"):
        return "groq"
    if os.getenv("ANTHROPIC_API_KEY"):
        return "claude"
    return "offline"


def extract_offline(listing):
    """Fallback (bina API key ke): simple keyword rules - sirf demo ke liye."""
    t = listing["text"].lower()
    signals = [w for w in ("budget", "urgent", "deadline", "new branches", "hiring", "failing")
               if w in t]
    needs = any(w in t for w in ("looking for", "need", "exploring", "hiring"))
    return {
        "has_requirement": needs,
        "requirement": listing["text"][:80] if needs else "",
        "industry": "unknown",
        "buying_signals": signals,
        "website_gaps": [],
        "urgency": "high" if ("urgent" in t or "budget" in t) else "medium" if needs else "low",
        "outreach_angle": "Offline mode: LLM provider lagayen behtar result ke liye.",
    }


def available_providers():
    """Jin ki key .env mein maujood hai, unki list (tarteeb: gemini, groq, claude)."""
    keys = {"gemini": "GEMINI_API_KEY", "groq": "GROQ_API_KEY", "claude": "ANTHROPIC_API_KEY"}
    return [p for p, k in keys.items() if os.getenv(k)]


CACHE_FILE = Path(__file__).parent / ".cache" / "llm_cache.json"


def _cache_key(listing):
    return hashlib.sha256((SYSTEM_PROMPT + _user_text(listing)).encode("utf-8")).hexdigest()


def _cache_load():
    try:
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _cache_save(cache):
    CACHE_FILE.parent.mkdir(exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def extract(listing, provider="offline"):
    if provider == "offline":
        return extract_offline(listing)

    # Cache: wahi text + wahi sawal dobara aaye to API call nahi hoti
    cache = _cache_load()
    key = _cache_key(listing)
    if key in cache:
        print("[info] cache se jawab mila (API call nahi hui)")
        return cache[key]

    # pehle chuna hua provider, phir baqi available providers (automatic fallback)
    chain = [provider] + [p for p in available_providers() if p != provider]
    for name in chain:
        try:
            result = _parse_json(CALLERS[name](_user_text(listing)))
        except Exception as e:  # network, rate limit, ya JSON parse error
            print(f"[warning] {name} fail hua: {e}")
            continue
        print(f"[info] jawab mila: {name}")
        base = extract_offline({"text": ""})
        base.update(result)
        base["buying_signals"] = base.get("buying_signals") or []
        base["website_gaps"] = base.get("website_gaps") or []
        cache[key] = base
        _cache_save(cache)
        return base
    print("[warning] sab providers fail - offline rules use ho rahe hain")
    return extract_offline(listing)