"""
Simple FastAPI admin dashboard + Mini App static host.
Run together with the bot or separately.
"""

from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path
import secrets

from config.settings import settings
from services.db import db
import hashlib

app = FastAPI(title="obra dashboard")
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "web" / "templates"))
static_dir = BASE / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# very simple session token (in-memory)
_sessions: set[str] = set()


def require_auth(request: Request):
    token = request.cookies.get("obra_admin")
    if not token or token not in _sessions:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return True


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if request.cookies.get("obra_admin") in _sessions:
        return RedirectResponse("/dashboard")
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(secret: str = Form(...)):
    if secret != settings.DASHBOARD_SECRET:
        raise HTTPException(403, "Wrong secret")
    token = secrets.token_urlsafe(32)
    _sessions.add(token)
    resp = RedirectResponse("/dashboard", status_code=303)
    resp.set_cookie("obra_admin", token, httponly=True, max_age=86400)
    return resp


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, _=Depends(require_auth)):
    stats = await db.get_stats(24)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "model": settings.MODEL},
    )


@app.get("/api/stats")
async def api_stats(_=Depends(require_auth)):
    return await db.get_stats(24)


@app.post("/api/block")
async def api_block(user_id: int = Form(...), reason: str = Form(""), _=Depends(require_auth)):
    await db.block_user(user_id, reason or "dashboard")
    return {"ok": True}


@app.post("/api/unblock")
async def api_unblock(user_id: int = Form(...), _=Depends(require_auth)):
    await db.unblock_user(user_id)
    return {"ok": True}


# ---------- Mini App page ----------
@app.get("/app", response_class=HTMLResponse)
async def mini_app(request: Request):
    return templates.TemplateResponse("miniapp.html", {"request": request})


@app.post("/inbound/{secret}")
async def inbound_webhook(secret: str, request: Request):
    """
    Generic inbound webhook → DMs ADMIN_IDS[0] or optional chat_id.
    GitHub: point a repo webhook to https://host/inbound/<WEBHOOK_INBOUND_SECRET>
    """
    expected = getattr(settings, "WEBHOOK_INBOUND_SECRET", "") or "obra-inbound"
    if secret != expected:
        raise HTTPException(403, "bad secret")
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")[:2000]}

    # GitHub push summary
    text = None
    if isinstance(payload, dict) and payload.get("repository") and payload.get("commits"):
        repo = payload["repository"].get("full_name", "repo")
        commits = payload.get("commits") or []
        lines = [f"📦 GitHub push on <b>{repo}</b> ({len(commits)} commits)"]
        for c in commits[:5]:
            lines.append(f"• {c.get('message','').split(chr(10))[0][:80]}")
        text = "\n".join(lines)
    else:
        import json
        text = "📥 Inbound webhook:\n<code>" + json.dumps(payload, ensure_ascii=False)[:1500] + "</code>"

    # Prefer notifying first admin via Telegram HTTP API
    import aiohttp
    admins = settings.admin_list
    if not admins:
        return {"ok": False, "error": "no ADMIN_IDS"}
    chat_id = admins[0]
    url = f"https://api.telegram.org/bot{settings.BOT_TOKEN}/sendMessage"
    async with aiohttp.ClientSession() as s:
        async with s.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"}) as r:
            data = await r.json()
    return {"ok": True, "telegram": data.get("ok")}
