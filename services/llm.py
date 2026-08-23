"""Multi-provider LLM + max-level agent routing."""
from __future__ import annotations

from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from config.settings import settings
import json
import logging

logger = logging.getLogger("obra.llm")

AGENTS = {
    "default": """Agent: general.
Understand intent, use tools when useful, deliver finished results.
Prefer completeness over brevity for build tasks.""",
    "coder": """Agent: professional software engineer.
Ship complete, runnable projects. Multi-file via create_file/create_zip.
No stubs. Include deps + run instructions. Large codebases OK.""",
    "researcher": """Agent: research.
Use web_search/wikipedia. Cite sources. Structure with headings.""",
    "writer": """Agent: writer.
Clear structure, tone matching the user, polished output.""",
    "solver": """Agent: end-to-end solver.
Infer goal → plan → tools → finished outcome. Large projects OK.""",
    "summarizer": """Agent: summarizer.
Key points, decisions, action items. Dense.""",
    "terminal": """Agent: terminal assistant.
Use run_python for compute/tests. Explain results briefly.""",
}


def detect_agent(text: str) -> str:
    t = (text or "").lower().strip()
    n = len(t)

    if any(w in t for w in ("summarize", "summary", "tldr", "recap", "action items")):
        return "summarizer"

    if t.startswith("run:") or t.startswith("exec:") or t.startswith("$ ") or "run python" in t:
        return "terminal"
    if any(w in t for w in ("calculate", "compute", "eval ")) and n < 200:
        return "terminal"

    build = ("make", "build", "create", "generate", "write", "code", "implement", "develop", "fix", "refactor")
    botish = ("bot", "telegram", "discord", "script", "app", "downloader", "scraper", "website", "api", "project", "full code", "source")
    if any(b in t for b in build) and any(x in t for x in botish):
        return "coder"
    if any(x in t for x in ("full code", "complete code", "as a file", "downloadable", "10000", "production", "professional")):
        return "coder"

    code_hits = sum(1 for w in (
        "code", "python", "javascript", "typescript", "bug", "error", "stacktrace",
        "function", "script", "debug", "sql", "fastapi", "django", "react", "html", "css",
    ) if w in t)
    if code_hits >= 1 and any(w in t for w in build):
        return "coder"
    if code_hits >= 2:
        return "coder"

    if any(w in t for w in ("latest", "news", "research", "what happened", "sources")):
        return "researcher"
    if t.startswith(("who is", "what is", "when did", "where is")) and n > 20:
        return "researcher"

    if any(w in t for w in ("essay", "blog", "rewrite", "caption", "draft email", "linkedin")):
        return "writer"

    solver_signals = (
        "build", "create", "make me", "generate", "implement", "set up", "setup",
        "from scratch", "step by step", "project", "full", "complete", "deploy",
        "automate", "pipeline", "integrate", "fix", "debug", "design", "file", "zip",
        "bot", "database", "skill", "schedule", "remind",
    )
    hits = sum(1 for w in solver_signals if w in t)
    multi = any(w in t for w in ("then", "after that", "also", "1.", "2.", "first", "finally"))
    if hits >= 2 or (hits >= 1 and (n > 180 or multi)):
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
            self._clients[key] = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=180.0)
        return self._clients[key]

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        system: str = None,
        tools: List[Dict] = None,
        model: str = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        user_provider: dict = None,
    ) -> Dict[str, Any]:
        chain = settings.provider_chain()
        if user_provider and user_provider.get("api_key"):
            chain = [{
                "name": "user_byok",
                "base_url": user_provider.get("api_base") or settings.OPENAI_BASE_URL,
                "api_key": user_provider["api_key"],
                "model": user_provider.get("api_model") or model or settings.MODEL,
            }] + chain
        if not chain:
            raise RuntimeError("No LLM providers configured. Set GROQ_API_KEY / OPENROUTER_API_KEY / etc.")

        full = [{"role": "system", "content": system or AGENTS["default"]}]
        full.extend(messages)
        last_err: Optional[Exception] = None

        for i, prov in enumerate(chain):
            use_model = prov.get("model") or settings.MODEL
            if i == 0 and model:
                use_model = model
            client = self._client(prov["base_url"], prov["api_key"])
            kwargs: Dict[str, Any] = {
                "model": use_model,
                "messages": full,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            try:
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"
                response = await client.chat.completions.create(**kwargs)
            except Exception as e1:
                if tools:
                    try:
                        kwargs.pop("tools", None)
                        kwargs.pop("tool_choice", None)
                        response = await client.chat.completions.create(**kwargs)
                    except Exception as e2:
                        last_err = e2
                        logger.warning("Provider %s failed: %s", prov["name"], e2)
                        continue
                else:
                    last_err = e1
                    logger.warning("Provider %s failed: %s", prov["name"], e1)
                    continue

            message = response.choices[0].message
            result: Dict[str, Any] = {
                "content": message.content,
                "tool_calls": None,
                "raw_message": message,
                "provider": prov["name"],
                "model_used": use_model,
            }
            if getattr(message, "tool_calls", None):
                result["tool_calls"] = [
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "arguments": json.loads(tc.function.arguments or "{}"),
                    }
                    for tc in message.tool_calls
                ]
            if i > 0:
                logger.info("Fell back to provider=%s model=%s", prov["name"], use_model)
            return result

        raise RuntimeError(f"All LLM providers failed. Last error: {last_err}")


pool = ProviderPool()


async def chat_completion(
    messages: List[Dict[str, Any]],
    system: str = None,
    tools: List[Dict] = None,
    model: str = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    user_provider: dict = None,
) -> Dict[str, Any]:
    return await pool.chat(
        messages=messages,
        system=system,
        tools=tools,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        user_provider=user_provider,
    )


def get_primary_client() -> AsyncOpenAI:
    chain = settings.provider_chain()
    if not chain:
        raise RuntimeError("No providers")
    p = chain[0]
    return AsyncOpenAI(api_key=p["api_key"], base_url=p["base_url"], timeout=180.0)
