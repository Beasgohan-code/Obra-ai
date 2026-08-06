"""Multi-provider LLM + auto agent routing."""
from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from config.settings import settings
from services.rich_format import RICH_SYSTEM_APPENDIX
import logging

logger = logging.getLogger("obra.llm")

AGENTS = {
    "default": """You are obra — a personal AI agent on Telegram.
Finish the user's request fully. Prefer tools (create_file, create_zip, run_python, web_search) when useful.
Structure longer answers with Markdown ## headings and tables for Rich Messages.
Never claim to be Mira. Be clear and deliver real working results.""" + RICH_SYSTEM_APPENDIX,
    "coder": """You are obra in FULL CODING mode.
When the user asks to make/build/create an app, bot, script, or tool:
1. Deliver COMPLETE, runnable code — not a short sketch or 50-line stub.
2. ALWAYS call the create_file tool (or create_zip for multi-file projects) so they get a downloadable file.
3. Include requirements, README notes, and how to run.
4. Prefer Python + aiogram for Telegram bots unless they specify otherwise.
5. For scrapers/downloaders: full structure, error handling, .env config, and a short legal/ToS note — still give complete runnable code.
6. Do NOT stop at "here's a basic example". Production-ready structure (main.py, config, handlers).
7. Multi-file projects → create_zip with all files.
Tiny one-liners only for trivial snippets. Real bots/apps = full delivery + file tool.""",
    "researcher": "You are obra in research mode. Use web_search/wikipedia. Structure findings with headings.",
    "writer": "You are obra in writing mode. Clear structure and tone.",
    "solver": """You are obra in full-task mode.
Infer the goal end-to-end. Use tools. For build/make/create requests, produce complete deliverables via create_file/create_zip.
Structure the final reply with ## headings. No half-done stubs.""",
    "summarizer": "Summarize: key points, decisions, action items.",
}

def detect_agent(text: str) -> str:
    t = (text or "").lower().strip()
    n = len(t)
    if any(w in t for w in ("summarize", "summary", "tldr", "recap")):
        return "summarizer"
    build_words = ("make", "build", "create", "generate", "write", "code", "implement", "develop")
    bot_words = ("bot", "telegram", "discord", "script", "app", "downloader", "scraper", "api", "website", "tool")
    lang_words = ("python", "javascript", "js", "html", "css", "java", "golang", "rust", "sql")
    if any(b in t for b in build_words) and (any(x in t for x in bot_words) or any(x in t for x in lang_words)):
        return "coder"
    if any(x in t for x in ("full code", "complete code", "entire project", "source code", "give me code", "as a file", "downloadable")):
        return "coder"
    code_hits = sum(1 for w in ("code", "python", "javascript", "bug", "function", "script", "debug", "sql", "html", "css", "bot") if w in t)
    if code_hits >= 1 and any(w in t for w in build_words):
        return "coder"
    if code_hits >= 2:
        return "coder"
    if any(w in t for w in ("latest", "news", "research", "what happened")):
        return "researcher"
    if any(w in t for w in ("essay", "blog", "rewrite", "caption", "draft email")):
        return "writer"
    signals = ("build", "create", "make me", "generate", "implement", "project", "complete", "fix", "file", "zip", "script", "website", "downloader")
    hits = sum(1 for w in signals if w in t)
    multi = any(w in t for w in ("then", "also", "and also", "first", "finally", "1.", "2."))
    if hits >= 2 or (hits >= 1 and (n > 120 or multi)):
        return "solver"
    if n > 400:
        return "solver"
    return "default"

class ProviderPool:
    def __init__(self):
        self._clients: Dict[str, AsyncOpenAI] = {}

    def _client(self, base_url: str, api_key: str) -> AsyncOpenAI:
        key = f"{base_url}|{api_key[:16]}"
        if key not in self._clients:
            self._clients[key] = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=90.0)
        return self._clients[key]

    async def chat(self, messages, system=None, tools=None, model=None, temperature=0.7, max_tokens=4096, user_provider=None):
        chain = settings.provider_chain()
        if user_provider and user_provider.get("api_key"):
            chain = [{
                "name": "user_byok",
                "base_url": user_provider.get("api_base") or settings.OPENAI_BASE_URL,
                "api_key": user_provider["api_key"],
                "model": user_provider.get("api_model") or model or settings.MODEL,
            }] + chain
        if not chain:
            raise RuntimeError("No LLM providers configured")
        full = [{"role": "system", "content": system or AGENTS["default"]}] + list(messages)
        last_err = None
        for p in chain:
            try:
                client = self._client(p["base_url"], p["api_key"])
                kwargs = {
                    "model": model or p.get("model") or settings.MODEL,
                    "messages": full,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                resp = await client.chat.completions.create(**kwargs)
                msg = resp.choices[0].message
                tool_calls = []
                if msg.tool_calls:
                    import json
                    for tc in msg.tool_calls:
                        try:
                            args = json.loads(tc.function.arguments or "{}")
                        except Exception:
                            args = {}
                        tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
                return {
                    "content": msg.content or "",
                    "tool_calls": tool_calls,
                    "raw_message": msg,
                    "provider": p.get("name"),
                    "model_used": kwargs["model"],
                }
            except Exception as e:
                last_err = e
                logger.warning("provider %s failed: %s", p.get("name"), e)
        raise RuntimeError(f"All providers failed: {last_err}")

_pool = ProviderPool()

async def chat_completion(messages, system=None, tools=None, model=None, temperature=0.7, max_tokens=4096, user_provider=None):
    return await _pool.chat(messages, system, tools, model, temperature, max_tokens, user_provider)
