"""Multi-provider LLM with automatic free-API fallback + agent personas."""

from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from config.settings import settings
from services.rich_format import RICH_SYSTEM_APPENDIX
import json
import logging

logger = logging.getLogger("obra.llm")

AGENTS = {
    "default": """You are obra — a personal AI agent inside Telegram.

Behave like a capable assistant that finishes the job:
- Understand the goal from context (no special keywords needed)
- For multi-step work: plan briefly, then execute with tools
- Use tools when they improve the answer (search, files, memory, poll, etc.)
- Deliver a complete result, not only advice
- Short chats → short replies; complex tasks → structured Rich Message answers

Personality: clear, calm, slightly witty. Never claim to be Mira or any other brand.
Be honest about limits.""",
    "coder": """You are obra in coding mode.
Ship working code, explain only what matters, offer a downloadable file via create_file when useful.""",
    "researcher": """You are obra in research mode.
Use web_search for current facts. Structure findings with headings and sources.""",
    "writer": """You are obra in writing mode.
Produce polished text with clear structure and tone matching the request.""",
    "solver": """You are obra in full-task mode (auto-selected for complex goals).
1) Infer the real goal from the message
2) Break into steps
3) Use tools (search, create_file, create_zip, remember, poll, etc.) when useful
4) Return a finished outcome with ## headings, lists, and next actions
Prefer doing the work over asking unnecessary questions. Only ask if blocked.""",
    "summarizer": """You are obra in summary mode.
Key points, decisions, action items, open questions. Dense and structured.""",
}


def detect_agent(text: str) -> str:
    """Auto route from situation — user does not need magic phrases."""
    t = (text or "").lower().strip()
    n = len(t)

    # Explicit still works but is optional
    if any(w in t for w in ("summarize", "summary", "tldr", "recap", "action items")):
        return "summarizer"

    # Coding situation
    code_hits = sum(1 for w in (
        "code", "python", "javascript", "typescript", "bug", "error", "stacktrace",
        "function", "script", "debug", "sql", "api", "fastapi", "django", "react",
        "html", "css", "compile", "refactor",
    ) if w in t)
    if code_hits >= 1 and any(w in t for w in ("write", "fix", "create", "generate", "build", "implement", "make")):
        return "coder"
    if code_hits >= 2:
        return "coder"

    # Research situation
    if any(w in t for w in ("latest", "news", "research", "what happened", "sources", "according to")):
        return "researcher"
    if t.startswith(("who is", "what is", "when did", "where is")) and n > 20:
        return "researcher"

    # Writing situation
    if any(w in t for w in ("essay", "blog", "rewrite", "caption", "draft email", "linkedin post", "cover letter")):
        return "writer"

    # Auto solver: complex / multi-step / deliverable situations (NO magic phrase required)
    solver_signals = (
        "build", "create", "make me", "generate", "implement", "set up", "setup",
        "from scratch", "step by step", "steps", "plan and", "help me with",
        "i need", "i want you to", "can you", "please", "project", "full",
        "complete", "entire", "deploy", "automate", "pipeline", "integrate",
        "fix", "debug", "design", "architecture", "document", "report",
        "file", "zip", "script", "website", "bot", "database",
    )
    signal_hits = sum(1 for w in solver_signals if w in t)
    multi_step = any(w in t for w in ("then", "after that", "also", "and also", "plus", "1.", "2.", "first", "finally"))
    long_request = n > 180
    list_like = t.count(chr(10)) >= 2 or t.count('- ') >= 2
    if signal_hits >= 2 or (signal_hits >= 1 and (long_request or multi_step or list_like)):
        return "solver"
    if long_request and multi_step:
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
            self._clients[key] = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=60.0)
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
            raise RuntimeError("No LLM providers configured. Set OPENAI_API_KEY / GROQ_API_KEY / etc.")

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
    return AsyncOpenAI(api_key=p["api_key"], base_url=p["base_url"], timeout=90.0)
