"""Obra tools registry."""
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
from services.db import db
import logging

logger = logging.getLogger("obra.tools")

TOOLS = [
    {"type":"function","function":{"name":"web_search","description":"Search the web","parameters":{"type":"object","properties":{"query":{"type":"string"},"num_results":{"type":"integer","default":5}},"required":["query"]}}},
    {"type":"function","function":{"name":"wikipedia","description":"Wikipedia summary","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
    {"type":"function","function":{"name":"fetch_url","description":"Fetch URL text","parameters":{"type":"object","properties":{"url":{"type":"string"}},"required":["url"]}}},
    {"type":"function","function":{"name":"weather","description":"Weather by city","parameters":{"type":"object","properties":{"city":{"type":"string"}},"required":["city"]}}},
    {"type":"function","function":{"name":"remember","description":"Save key-value memory","parameters":{"type":"object","properties":{"key":{"type":"string"},"value":{"type":"string"}},"required":["key","value"]}}},
    {"type":"function","function":{"name":"calculator","description":"Math expression","parameters":{"type":"object","properties":{"expression":{"type":"string"}},"required":["expression"]}}},
    {"type":"function","function":{"name":"save_skill","description":"Save scheduled skill e.g. every 1 minutes: send me hi","parameters":{"type":"object","properties":{"name":{"type":"string"},"instruction":{"type":"string"}},"required":["name","instruction"]}}},
    {"type":"function","function":{"name":"list_skills","description":"List user skills","parameters":{"type":"object","properties":{}}}},
    {"type":"function","function":{"name":"create_file","description":"ALWAYS use this to deliver complete code/scripts as a downloadable .py/.txt/.html/.md file. Prefer this over pasting long code in chat. For bots/apps send the full source.","parameters":{"type":"object","properties":{"filename":{"type":"string"},"content":{"type":"string"}},"required":["filename","content"]}}},
    {"type":"function","function":{"name":"create_zip","description":"Package multi-file projects (bot + requirements + README) as a downloadable .zip. Required for full apps/bots with multiple files.","parameters":{"type":"object","properties":{"archive_name":{"type":"string"},"files":{"type":"array","items":{"type":"object","properties":{"filename":{"type":"string"},"content":{"type":"string"}}}}},"required":["files"]}}},
    {"type":"function","function":{"name":"run_python","description":"Run restricted Python","parameters":{"type":"object","properties":{"code":{"type":"string"}},"required":["code"]}}},
    {"type":"function","function":{"name":"create_poll","description":"Create Telegram poll","parameters":{"type":"object","properties":{"question":{"type":"string"},"options":{"type":"array","items":{"type":"string"}},"is_anonymous":{"type":"boolean","default":True}},"required":["question","options"]}}},
    {"type":"function","function":{"name":"current_time","description":"Current UTC time","parameters":{"type":"object","properties":{}}}},
]

async def run_tool(name: str, arguments: Dict[str, Any], user_id: int = None) -> Tuple[str, Optional[bytes], Optional[Tuple[str, bytes]]]:
    try:
        args = arguments or {}
        if name == "web_search":
            import aiohttp
            from urllib.parse import quote
            q = args.get("query") or ""
            lines = []
            try:
                url = f"https://api.duckduckgo.com/?q={quote(q)}&format=json&no_html=1&skip_disambig=1"
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=15) as r:
                        data = await r.json(content_type=None)
                        if data.get("AbstractText"):
                            lines.append(data["AbstractText"][:1200])
                        if data.get("AbstractURL"):
                            lines.append(data["AbstractURL"])
                        for t in (data.get("RelatedTopics") or [])[:5]:
                            if isinstance(t, dict) and t.get("Text"):
                                lines.append("- " + t["Text"][:200])
            except Exception as e:
                lines.append(f"(search partial: {e})")
            if not lines:
                # fallback wiki
                try:
                    wurl = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(q.replace(' ','_'))}"
                    async with aiohttp.ClientSession() as s:
                        async with s.get(wurl, timeout=12) as r:
                            if r.status == 200:
                                d = await r.json()
                                lines.append(d.get("extract") or d.get("description") or "")
                except Exception:
                    pass
            return ("\n".join(lines) if lines else f"No results for {q}"), None, None
        if name == "wikipedia":
            import aiohttp
            from urllib.parse import quote
            q = args.get("query","")
            url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{quote(q.replace(' ','_'))}"
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=15) as r:
                    if r.status == 404:
                        return f"No page for {q}", None, None
                    data = await r.json()
                    return f"**{data.get('title',q)}**\n{(data.get('extract') or '')[:2000]}", None, None
        if name == "fetch_url":
            import aiohttp
            url = args.get("url","")
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=20) as r:
                    text = await r.text()
                    return text[:8000], None, None
        if name == "weather":
            import aiohttp
            city = args.get("city","")
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://wttr.in/{city}?format=3", timeout=15) as r:
                    return await r.text(), None, None
        if name == "remember":
            if not user_id:
                return "No user", None, None
            await db.set_memory_kv(user_id, args.get("key",""), args.get("value",""))
            return f"Saved {args.get('key')}", None, None
        if name == "calculator":
            import ast, operator as op
            ops = {ast.Add:op.add,ast.Sub:op.sub,ast.Mult:op.mul,ast.Div:op.truediv,ast.Pow:op.pow,ast.USub:op.neg}
            def ev(n):
                if isinstance(n, ast.Constant): return n.value
                if isinstance(n, ast.BinOp): return ops[type(n.op)](ev(n.left), ev(n.right))
                if isinstance(n, ast.UnaryOp): return ops[type(n.op)](ev(n.operand))
                raise ValueError("bad expr")
            return str(ev(ast.parse(args.get("expression","0"), mode="eval").body)), None, None
        if name == "save_skill":
            if not user_id:
                return "No user", None, None
            await db.add_skill(user_id, args.get("name","skill"), args.get("instruction",""))
            try:
                from services.scheduler import reload_skills_now
                await reload_skills_now()
            except Exception:
                pass
            return f"Skill saved & scheduled: {args.get('instruction','')[:120]}", None, None
        if name == "list_skills":
            if not user_id:
                return "No user", None, None
            skills = await db.list_skills(user_id)
            if not skills:
                return "No skills", None, None
            return "\n".join(f"#{s['id']} {s['instruction']}" for s in skills), None, None
        if name == "create_file":
            from services.file_tools import execute_create_file
            return await execute_create_file(args.get("filename","file.txt"), args.get("content",""))
        if name == "create_zip":
            from services.file_tools import execute_create_zip
            return await execute_create_zip(args.get("archive_name","archive.zip"), args.get("files") or [])
        if name == "run_python":
            from services.sandbox import run_python
            out, ok = run_python(args.get("code",""))
            return f"{'OK' if ok else 'ERR'}:\n{out}", None, None
        if name == "create_poll":
            import json
            payload = {
                "question": args.get("question","Poll"),
                "options": [str(o)[:100] for o in (args.get("options") or [])][:10],
                "is_anonymous": bool(args.get("is_anonymous", True)),
            }
            return "POLL_REQUIRED::" + json.dumps(payload, ensure_ascii=False), None, None
        if name == "current_time":
            from datetime import datetime, timezone
            return datetime.now(timezone.utc).isoformat(), None, None
        return f"Unknown tool: {name}", None, None
    except Exception as e:
        logger.exception("tool %s", name)
        return f"Tool error ({name}): {e}", None, None
