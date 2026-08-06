from typing import Dict, Any, Optional, Tuple
import aiohttp
import json
import base64
from datetime import datetime
from config.settings import settings
from services.db import db
from services.llm import get_primary_client
from services import vector_memory

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "wikipedia",
            "description": "Get a short Wikipedia summary for a topic.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information, news, facts.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "num_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url",
            "description": "Fetch text content from a public URL (articles, docs).",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "Get current weather for a city.",
            "parameters": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember",
            "description": "Save long-term key-value info about the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remember_semantic",
            "description": "Store a free-form fact in vector memory.",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_user_memory",
            "description": "Retrieve key-value long-term memory.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "current_time",
            "description": "Get current UTC time.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an image from a text prompt.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "size": {
                        "type": "string",
                        "enum": ["1024x1024", "1792x1024", "1024x1792"],
                        "default": "1024x1024",
                    },
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculator",
            "description": "Evaluate a simple math expression (e.g. 2+2*3, sqrt via **0.5).",
            "parameters": {
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_skill",
            "description": "Save a named recurring skill/reminder instruction for this user (Mira-style skill).",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "instruction": {"type": "string", "description": "What to do, e.g. every Monday summarize GitHub"},
                },
                "required": ["name", "instruction"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Run a short restricted Python snippet and return stdout. No imports/network/files.",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_list_repos",
            "description": "List GitHub repos for the configured token.",
            "parameters": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_read_file",
            "description": "Read a file from GitHub repo (owner/name).",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "path": {"type": "string"},
                    "ref": {"type": "string", "default": "main"}
                },
                "required": ["repo", "path"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "github_create_issue",
            "description": "Create a GitHub issue on owner/name repo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo": {"type": "string"},
                    "title": {"type": "string"},
                    "body": {"type": "string"}
                },
                "required": ["repo", "title"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "group_remember",
            "description": "Store a fact in this group's shared brain (group chats).",
            "parameters": {
                "type": "object",
                "properties": {"text": {"type": "string"}, "chat_id": {"type": "integer"}},
                "required": ["text"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_file",
            "description": "Create a downloadable text/code file (txt, py, html, md, json, css, js, ...). Content is the full file body.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string", "description": "e.g. script.py, page.html, notes.txt"},
                    "content": {"type": "string", "description": "Full file contents"}
                },
                "required": ["filename", "content"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_zip",
            "description": "Create a .zip archive with multiple text files and send it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "archive_name": {"type": "string", "default": "archive.zip"},
                    "files": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "filename": {"type": "string"},
                                "content": {"type": "string"}
                            },
                            "required": ["filename", "content"]
                        }
                    }
                },
                "required": ["files"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_poll",
            "description": "Create a Telegram poll for voting / multiple choice.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                    "is_anonymous": {"type": "boolean", "default": true},
                    "allows_multiple_answers": {"type": "boolean", "default": false}
                },
                "required": ["question", "options"]
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "translate",
            "description": "Translate text to a target language.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "target_lang": {"type": "string", "default": "English"},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_skills",
            "description": "List saved skills for this user",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },

    {
        "type": "function",
        "function": {
            "name": "gmail_unread",
            "description": "List recent unread Gmail messages (requires Google OAuth tokens).",
            "parameters": {
                "type": "object",
                "properties": {"max_results": {"type": "integer", "default": 5}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "gmail_send",
            "description": "Send an email via Gmail.",
            "parameters": {
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_upcoming",
            "description": "List upcoming Google Calendar events.",
            "parameters": {
                "type": "object",
                "properties": {"days": {"type": "integer", "default": 7}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calendar_create",
            "description": "Create a Google Calendar event. start_iso like 2026-08-06T15:00:00Z",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "start_iso": {"type": "string"},
                    "end_iso": {"type": "string"},
                },
                "required": ["summary", "start_iso"],
            },
        },
    },
]


async def execute_web_search(query: str, num_results: int = 5) -> str:
    if settings.TAVILY_API_KEY:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": num_results,
                    "include_answer": True,
                },
            ) as r:
                data = await r.json()
                lines = []
                if data.get("answer"):
                    lines.append(f"**Answer:** {data['answer']}")
                for item in data.get("results", [])[:num_results]:
                    lines.append(f"- [{item.get('title')}]({item.get('url')})\n  {item.get('content','')[:200]}...")
                return "\n".join(lines) or "No results."
    if settings.SERPER_API_KEY:
        async with aiohttp.ClientSession() as s:
            async with s.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": settings.SERPER_API_KEY, "Content-Type": "application/json"},
                json={"q": query, "num": num_results},
            ) as r:
                data = await r.json()
                lines = [
                    f"- [{o.get('title')}]({o.get('link')})\n  {o.get('snippet','')}"
                    for o in data.get("organic", [])[:num_results]
                ]
                return "\n".join(lines) or "No results."
    return "Web search not configured (add TAVILY_API_KEY or SERPER_API_KEY)."


async def execute_fetch_url(url: str) -> str:
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                text = await r.text()
                # crude strip of tags
                import re
                clean = re.sub(r"<[^>]+>", " ", text)
                clean = re.sub(r"\s+", " ", clean).strip()
                return clean[:4000] or "Empty page."
    except Exception as e:
        return f"Fetch failed: {e}"


async def execute_weather(city: str) -> str:
    if not settings.OPENWEATHER_API_KEY:
        return "Weather not configured (set OPENWEATHER_API_KEY)."
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(
                "https://api.openweathermap.org/data/2.5/weather",
                params={"q": city, "appid": settings.OPENWEATHER_API_KEY, "units": "metric"},
            ) as r:
                data = await r.json()
                if data.get("cod") != 200:
                    return f"Weather error: {data.get('message', data)}"
                main = data["main"]
                w = data["weather"][0]
                return (
                    f"{data['name']}: {w['description']}, "
                    f"{main['temp']}°C (feels {main['feels_like']}°C), "
                    f"humidity {main['humidity']}%"
                )
    except Exception as e:
        return f"Weather failed: {e}"


async def execute_remember(user_id: int, key: str, value: str) -> str:
    mem = await db.get_user_memory(user_id) or {}
    prefs = mem.get("preferences", {})
    prefs[key] = value
    await db.set_user_memory(user_id, preferences=prefs)
    return f"Remembered: {key} = {value}"


async def execute_remember_semantic(user_id: int, text: str) -> str:
    await vector_memory.add_memory(user_id, text)
    return f"Stored in vector memory: {text[:120]}..."


async def execute_get_user_memory(user_id: int) -> str:
    mem = await db.get_user_memory(user_id)
    if not mem:
        return "No key-value memory yet."
    return json.dumps(mem, indent=2, ensure_ascii=False)


async def execute_generate_image(prompt: str, size: str = "1024x1024") -> Tuple[str, Optional[bytes]]:
    try:
        response = await get_primary_client().images.generate(
            model=settings.IMAGE_MODEL,
            prompt=prompt,
            size=size,
            n=1,
            response_format="b64_json",
        )
        b64 = response.data[0].b64_json
        if not b64:
            url = getattr(response.data[0], "url", None)
            if url:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url) as r:
                        return f"Generated: {prompt[:80]}...", await r.read()
            return "Empty image response.", None
        return f"Generated: {prompt[:80]}...", base64.b64decode(b64)
    except Exception as e:
        return f"Image generation failed: {str(e)[:200]}", None


async def execute_calculator(expression: str) -> str:
    import ast
    import operator as op
    allowed = {
        ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul, ast.Div: op.truediv,
        ast.Pow: op.pow, ast.USub: op.neg, ast.Mod: op.mod,
    }
    def _eval(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in allowed:
            return allowed[type(node.op)](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and type(node.op) in allowed:
            return allowed[type(node.op)](_eval(node.operand))
        raise ValueError("unsupported expression")
    try:
        tree = ast.parse(expression, mode="eval")
        return str(_eval(tree.body))
    except Exception as e:
        return f"Calc error: {e}"


async def execute_save_skill(user_id: int, name: str, instruction: str) -> str:
    await db.add_skill(user_id, name, instruction)
    try:
        from services.scheduler import reload_skills_now
        await reload_skills_now()
    except Exception:
        pass
    return f"Skill saved & scheduled: {name} → {instruction[:120]}"


async def execute_list_skills(user_id: int) -> str:
    skills = await db.list_skills(user_id)
    if not skills:
        return "No skills saved yet."
    lines = [f"- #{s['id']} **{s['name']}**: {s['instruction']}" for s in skills]
    return "\n".join(lines)



async def run_tool(name: str, arguments: Dict[str, Any], user_id: int = None) -> Tuple[str, Optional[bytes], Optional[Tuple[str, bytes]]]:
    try:
        if name == "wikipedia":
            import aiohttp
            q = arguments.get("query") or ""
            from urllib.parse import quote as _quote
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{_quote(q.replace(' ', '_'))}"
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=15) as r:
                        if r.status == 404:
                            return f"No Wikipedia page for {q}", None, None
                        data = await r.json()
                        title = data.get("title", q)
                        extract = data.get("extract") or data.get("description") or ""
                        page = (data.get("content_urls") or {}).get("desktop", {}).get("page", "")
                        return f"**{title}**\n{extract[:2000]}\n{page}", None, None
            except Exception as e:
                return f"Wikipedia error: {e}", None, None
        if name == "web_search":
            return await execute_web_search(arguments.get("query", ""), arguments.get("num_results", 5)), None, None
        if name == "fetch_url":
            return await execute_fetch_url(arguments.get("url", "")), None, None
        if name == "weather":
            return await execute_weather(arguments.get("city", "")), None, None
        if name == "remember":
            if not user_id:
                return "No user context", None, None
            return await execute_remember(user_id, arguments.get("key", ""), arguments.get("value", "")), None, None
        if name == "remember_semantic":
            if not user_id:
                return "No user context", None, None
            return await execute_remember_semantic(user_id, arguments.get("text", "")), None, None
        if name == "get_user_memory":
            if not user_id:
                return "No user context", None, None
            return await execute_get_user_memory(user_id), None, None
        if name == "current_time":
            return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"), None, None
        if name == "create_poll":
            import json as _json
            q = arguments.get("question", "Poll")
            opts = arguments.get("options") or []
            if not isinstance(opts, list):
                opts = [str(opts)]
            payload = {
                "question": q,
                "options": [str(o)[:100] for o in opts][:10],
                "is_anonymous": bool(arguments.get("is_anonymous", True)),
                "allows_multiple_answers": bool(arguments.get("allows_multiple_answers", False)),
            }
            return "POLL_REQUIRED::" + _json.dumps(payload, ensure_ascii=False), None
        if name == "translate":
            from services.media_ai import translate_text
            return await translate_text(arguments.get("text",""), arguments.get("target_lang","English")), None, None
        if name == "gmail_unread":
            from services.google_tools import gmail_list_unread
            return await gmail_list_unread(arguments.get("max_results", 5)), None, None
        if name == "gmail_send":
            # Safety: queue for user confirmation instead of sending immediately
            import uuid
            pid = str(uuid.uuid4())[:12]
            await db.save_pending(
                pid, user_id or 0, 0, "gmail_send",
                {"to": arguments.get("to",""), "subject": arguments.get("subject",""), "body": arguments.get("body","")},
            )
            return (
                f"CONFIRM_REQUIRED::{pid}::Email to {arguments.get('to')} | subject: {arguments.get('subject')}\n"
                f"Ask the user to confirm with the buttons or /confirm {pid}",
                None,
            )
        if name == "calendar_upcoming":
            from services.google_tools import calendar_upcoming
            return await calendar_upcoming(arguments.get("days", 7)), None, None
        if name == "calendar_create":
            from services.google_tools import calendar_create
            return await calendar_create(arguments.get("summary",""), arguments.get("start_iso",""), arguments.get("end_iso","")), None, None
        if name == "calculator":
            return await execute_calculator(arguments.get("expression", "0")), None, None
        if name == "save_skill":
            if not user_id:
                return "No user context", None, None
            return await execute_save_skill(user_id, arguments.get("name", ""), arguments.get("instruction", "")), None, None
        if name == "list_skills":
            if not user_id:
                return "No user context", None, None
            return await execute_list_skills(user_id), None, None
        if name == "run_python":
            from config.settings import settings as _s
            if not getattr(_s, "ENABLE_SANDBOX", True):
                return "Sandbox disabled.", None, None
            from services.sandbox import run_python
            out, ok = run_python(arguments.get("code", ""))
            return (f"{'OK' if ok else 'ERR'}:\n{out}"), None, None
        if name == "github_list_repos":
            from services.github_tools import github_list_repos
            return await github_list_repos(arguments.get("limit", 10)), None, None
        if name == "github_read_file":
            from services.github_tools import github_read_file
            return await github_read_file(arguments.get("repo",""), arguments.get("path",""), arguments.get("ref","main")), None, None
        if name == "github_create_issue":
            from services.github_tools import github_create_issue
            return await github_create_issue(arguments.get("repo",""), arguments.get("title",""), arguments.get("body","")), None, None
        if name == "group_remember":
            from services import vector_memory as vm
            cid = arguments.get("chat_id") or 0
            await vm.add_group_memory(int(cid), arguments.get("text",""))
            return "Stored in group brain.", None, None
        if name == "create_file":
            from services.file_tools import execute_create_file
            return await execute_create_file(arguments.get("filename", "file.txt"), arguments.get("content", ""))
        if name == "create_zip":
            from services.file_tools import execute_create_zip
            return await execute_create_zip(arguments.get("archive_name", "archive.zip"), arguments.get("files") or [])
        if name == "generate_image":
            img_res = await execute_generate_image(
                arguments.get("prompt", "landscape"), arguments.get("size", "1024x1024")
            )
            return img_res[0], img_res[1], None
        return f"Unknown tool: {name}", None, None
    except Exception as e:
        return f"Tool error ({name}): {e}", None, None
