"""Multi-provider LLM + max-level agent routing."""
from __future__ import annotations

from openai import AsyncOpenAI
from typing import List, Dict, Any, Optional
from config.settings import settings
import json
import logging

logger = logging.getLogger("obra.llm")

def _is_gemini_endpoint(base_url: str, model: str = "") -> bool:
    u = (base_url or "").lower()
    m = (model or "").lower()
    return "generativelanguage.googleapis.com" in u or "gemini" in m


def _extract_tool_calls(message) -> list:
    """Parse tool calls and preserve Gemini thought_signature / extra_content."""
    out = []
    for tc in (getattr(message, "tool_calls", None) or []):
        item = {
            "id": tc.id,
            "name": tc.function.name,
            "arguments": json.loads(tc.function.arguments or "{}"),
        }
        # OpenAI-compat Gemini attaches signature here
        extra = None
        if hasattr(tc, "model_extra") and tc.model_extra:
            extra = tc.model_extra.get("extra_content") or tc.model_extra
        if hasattr(tc, "extra_content") and tc.extra_content:
            extra = tc.extra_content if not isinstance(tc.extra_content, dict) else tc.extra_content
        # pydantic v2
        try:
            dump = tc.model_dump(exclude_none=True) if hasattr(tc, "model_dump") else {}
            if dump.get("extra_content"):
                extra = dump["extra_content"]
            # some SDKs nest under function
            if not extra and isinstance(dump.get("function"), dict):
                extra = dump["function"].get("extra_content")
        except Exception:
            pass
        sig = None
        if isinstance(extra, dict):
            g = extra.get("google") or {}
            sig = g.get("thought_signature") or extra.get("thought_signature")
        if sig:
            item["extra_content"] = {"google": {"thought_signature": sig}}
        out.append(item)
    return out


def _assistant_tool_message(content, tool_calls: list, gemini: bool = False) -> dict:
    """Build assistant message with tool_calls, injecting Gemini signature bypass if needed."""
    formatted = []
    for i, tc in enumerate(tool_calls):
        entry = {
            "id": tc["id"],
            "type": "function",
            "function": {
                "name": tc["name"],
                "arguments": json.dumps(tc["arguments"]) if isinstance(tc.get("arguments"), dict) else (tc.get("arguments") or "{}"),
            },
        }
        extra = tc.get("extra_content")
        if not extra and gemini:
            # Official bypass sentinel when signature was stripped by OpenAI-compat layer
            extra = {"google": {"thought_signature": "skip_thought_signature_validator"}}
        if extra:
            entry["extra_content"] = extra
        formatted.append(entry)
    msg = {"role": "assistant", "content": content, "tool_calls": formatted}
    return msg


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
        # provider name -> unix ts until which it is skipped after failures
        self._down_until: Dict[str, float] = {}
        # provider name -> {"ok": int, "fail": int, "last_error": str}
        self.stats: Dict[str, Dict[str, Any]] = {}
        self.cooldown_seconds = float(getattr(settings, "PROVIDER_COOLDOWN_SECONDS", 60) or 60)

    def _client(self, base_url: str, api_key: str) -> AsyncOpenAI:
        key = f"{base_url}|{api_key[:16]}"
        if key not in self._clients:
            timeout = float(getattr(settings, "LLM_TIMEOUT_SECONDS", 90) or 90)
            self._clients[key] = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        return self._clients[key]

    def _mark(self, name: str, ok: bool, err: str = ""):
        import time
        st = self.stats.setdefault(name, {"ok": 0, "fail": 0, "last_error": ""})
        if ok:
            st["ok"] += 1
            st["last_error"] = ""
            self._down_until.pop(name, None)
        else:
            st["fail"] += 1
            st["last_error"] = err[:200]
            self._down_until[name] = time.time() + self.cooldown_seconds

    def _is_down(self, name: str) -> bool:
        import time
        until = self._down_until.get(name)
        return bool(until and time.time() < until)

    def healthy_providers(self, chain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Chain with cooling-down providers moved to the back (used only if all are down)."""
        up = [p for p in chain if not self._is_down(p["name"])]
        down = [p for p in chain if self._is_down(p["name"])]
        return up + down

    def provider_stats(self) -> Dict[str, Dict[str, Any]]:
        import time
        out = {}
        for name, st in self.stats.items():
            out[name] = {**st, "cooling_down": self._is_down(name)}
        return out

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
        if not chain:
            logger.error("provider_chain EMPTY — set GROQ_API_KEY or OPENAI_API_KEY")
        else:
            logger.info("LLM chain: %s", [p["name"] for p in chain])
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
        # Sanitize history for Gemini thought_signature requirements
        patched = []
        for m in messages:
            if m.get("role") == "assistant" and m.get("tool_calls"):
                gem = True  # safe to inject sentinel; non-Gemini ignores unknown fields
                patched.append(_assistant_tool_message(m.get("content"), [
                    {
                        "id": tc.get("id"),
                        "name": (tc.get("function") or {}).get("name") or tc.get("name"),
                        "arguments": (tc.get("function") or {}).get("arguments") or tc.get("arguments") or {},
                        "extra_content": tc.get("extra_content"),
                    }
                    for tc in m["tool_calls"]
                ], gemini=gem))
            else:
                patched.append(m)
        full.extend(patched)
        last_err: Optional[Exception] = None

        import asyncio
        retries = max(0, int(getattr(settings, "PROVIDER_RETRIES", 1) or 0))

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
            if tools:
                kwargs["tools"] = tools
                kwargs["tool_choice"] = "auto"

            response = None
            err = None
            for attempt in range(retries + 1):
                try:
                    response = await client.chat.completions.create(**kwargs)
                    err = None
                    break
                except Exception as e1:
                    err = e1
                    # Some providers reject tool calling — retry once without tools
                    if tools and kwargs.get("tools"):
                        kwargs.pop("tools", None)
                        kwargs.pop("tool_choice", None)
                        logger.info("Provider %s: retrying without tools (%s)", prov["name"], str(e1)[:120])
                        continue
                    if attempt < retries:
                        await asyncio.sleep(min(2 ** attempt, 4) * 0.5)
                        continue
            if response is None:
                last_err = err
                self._mark(prov["name"], False, str(err)[:200])
                logger.warning("Provider %s failed (will try next): %s", prov["name"], str(err)[:200])
                continue

            self._mark(prov["name"], True)
            message = response.choices[0].message
            result: Dict[str, Any] = {
                "content": message.content,
                "tool_calls": None,
                "raw_message": message,
                "provider": prov["name"],
                "model_used": use_model,
            }
            if getattr(message, "tool_calls", None):
                result["tool_calls"] = _extract_tool_calls(message)
                result["gemini"] = _is_gemini_endpoint(prov["base_url"], use_model)
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
