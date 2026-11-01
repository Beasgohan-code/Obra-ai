"""
obra admin dashboard + Mini App backend (FastAPI).

Security:
- Secret compared in constant time; per-IP login rate limit.
- Sessions: random token, httponly + samesite cookie, server-side expiry.
- CSRF: double-submit token — login sets a csrf cookie+hidden field; every POST
  (login and authenticated) must present a matching token.
- Security headers on every response; no caching of authenticated pages.
- GitHub inbound webhook: X-Hub-Signature-256 verified when GITHUB_WEBHOOK_SECRET set.
- Mini App: Telegram WebApp initData HMAC-SHA256 ("WebAppData") verification,
  then short-lived HMAC-signed tokens for read-only user APIs.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, HTTPException, Depends, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from config.settings import settings
from services.db import db

logger = logging.getLogger("obra.dashboard")

app = FastAPI(title="obra dashboard")
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "web" / "templates"))
static_dir = BASE / "web" / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.on_event("startup")
async def _startup():
    """Ensure the schema exists even if the dashboard runs standalone."""
    try:
        await db.init()
    except Exception as e:
        logger.warning("db init on startup: %s", e)

_START = time.time()
_START_ISO = datetime.now(timezone.utc).isoformat()

# sessions: token -> {"created": float, "seen": float, "csrf": str}
_sessions: dict[str, dict] = {}
SESSION_MAX_AGE = 12 * 3600  # 12h absolute
# login attempts: ip -> [timestamps]
_login_attempts: dict[str, list[float]] = {}
LOGIN_WINDOW = 300
LOGIN_MAX = 8

MINIAPP_TOKEN_TTL = 6 * 3600  # 6h


# ---------------------------------------------------------------- helpers
def _now() -> float:
    return time.time()


def _sign(payload: str) -> str:
    return hmac.new(settings.DASHBOARD_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()


def issue_miniapp_token(user_id: int) -> str:
    exp = int(_now()) + MINIAPP_TOKEN_TTL
    payload = f"{user_id}:{exp}"
    return f"{payload}:{_sign(payload)}"


def verify_miniapp_token(token: str) -> int:
    try:
        uid_s, exp_s, sig = token.rsplit(":", 2)
        payload = f"{uid_s}:{exp_s}"
        if not hmac.compare_digest(sig, _sign(payload)):
            raise ValueError("bad sig")
        if int(exp_s) < _now():
            raise ValueError("expired")
        return int(uid_s)
    except Exception:
        raise HTTPException(status_code=401, detail="invalid or expired token")


def verify_telegram_initdata(init_data: str) -> Optional[dict]:
    """Verify Telegram WebApp initData per official docs. Returns user dict or None."""
    if not init_data or not settings.BOT_TOKEN:
        return None
    try:
        pairs = parse_qsl(init_data, keep_blank_values=True)
        data = dict(pairs)
        received_hash = data.pop("hash", "")
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        secret_key = hmac.new(b"WebAppData", settings.BOT_TOKEN.encode(), hashlib.sha256).digest()
        calc = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, received_hash):
            return None
        # freshness check (24h)
        try:
            auth_date = int(data.get("auth_date", "0"))
            if _now() - auth_date > 86400:
                return None
        except Exception:
            return None
        user_raw = data.get("user")
        if not user_raw:
            return None
        user = json.loads(user_raw)
        if not isinstance(user, dict) or "id" not in user:
            return None
        return user
    except Exception as e:
        logger.warning("initData verify failed: %s", e)
        return None


def _session_from(request: Request) -> Optional[dict]:
    token = request.cookies.get("obra_admin")
    if not token:
        return None
    sess = _sessions.get(token)
    if not sess:
        return None
    if _now() - sess["created"] > SESSION_MAX_AGE:
        _sessions.pop(token, None)
        return None
    sess["seen"] = _now()
    return sess


def require_auth(request: Request) -> dict:
    sess = _session_from(request)
    if not sess:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return sess


def require_csrf(request: Request, sess: dict, form_token: Optional[str] = None):
    """Double-submit: token must match the session's csrf (header or form field)."""
    header = request.headers.get("x-csrf-token", "")
    token = form_token or header
    if not token or not hmac.compare_digest(token, sess["csrf"]):
        raise HTTPException(status_code=403, detail="CSRF token missing/invalid")


def client_ip(request: Request) -> str:
    return (request.headers.get("x-forwarded-for") or "").split(",")[0].strip() or (request.client.host if request.client else "?")


# ---------------------------------------------------------------- middleware
@app.middleware("http")
async def security_headers(request: Request, call_next):
    resp = await call_next(request)
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' https://telegram.org; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self'"
    )
    if request.url.path.startswith(("/dashboard", "/api/")):
        resp.headers["Cache-Control"] = "no-store"
    return resp


# ---------------------------------------------------------------- health
@app.get("/health")
@app.get("/uptime")
@app.get("/ping")
async def health_uptime():
    return {
        "ok": True,
        "service": "obra",
        "status": "up",
        "uptime_seconds": int(time.time() - _START),
        "started_at": _START_ISO,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/healthz")
async def healthz():
    return PlainTextResponse("ok")


# ---------------------------------------------------------------- auth pages
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if _session_from(request):
        return RedirectResponse("/dashboard")
    csrf = secrets.token_urlsafe(24)
    resp = templates.TemplateResponse(request, "login.html", {"csrf": csrf})
    resp.set_cookie("obra_csrf", csrf, httponly=True, samesite="lax", max_age=600)
    return resp


@app.post("/login")
async def login(request: Request, secret: str = Form(...), csrf: str = Form("")):
    ip = client_ip(request)
    now = _now()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < LOGIN_WINDOW]
    if len(attempts) >= LOGIN_MAX:
        raise HTTPException(429, "Too many login attempts. Try again later.")
    # CSRF: form token must match the pre-session csrf cookie
    cookie_csrf = request.cookies.get("obra_csrf", "")
    if not csrf or not cookie_csrf or not hmac.compare_digest(csrf, cookie_csrf):
        _login_attempts.setdefault(ip, []).append(now)
        raise HTTPException(403, "CSRF check failed")
    if not settings.DASHBOARD_SECRET or not hmac.compare_digest(secret, settings.DASHBOARD_SECRET):
        _login_attempts.setdefault(ip, []).append(now)
        raise HTTPException(403, "Wrong secret")
    _login_attempts.pop(ip, None)
    token = secrets.token_urlsafe(32)
    _sessions[token] = {"created": now, "seen": now, "csrf": secrets.token_urlsafe(24)}
    resp = RedirectResponse("/dashboard", status_code=303)
    secure = request.headers.get("x-forwarded-proto") == "https" or request.url.scheme == "https"
    resp.set_cookie("obra_admin", token, httponly=True, samesite="lax", secure=secure, max_age=SESSION_MAX_AGE)
    resp.delete_cookie("obra_csrf")
    return resp


@app.get("/logout")
async def logout(request: Request):
    token = request.cookies.get("obra_admin")
    if token:
        _sessions.pop(token, None)
    resp = RedirectResponse("/", status_code=303)
    resp.delete_cookie("obra_admin")
    return resp


# ---------------------------------------------------------------- dashboard page
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, sess: dict = Depends(require_auth)):
    stats = await db.get_stats(24)
    return templates.TemplateResponse(
        request, "dashboard.html",
        {"stats": stats, "model": settings.MODEL, "csrf": sess["csrf"]},
    )


# ---------------------------------------------------------------- JSON APIs (session auth + CSRF on writes)
@app.get("/api/stats")
async def api_stats(_=Depends(require_auth)):
    return await db.get_stats(24)


@app.get("/api/overview")
async def api_overview(_=Depends(require_auth)):
    stats = await db.get_stats(24)
    from services.llm import pool
    from services.tools import TOOLS
    chain = settings.provider_chain()
    return {
        "stats": stats,
        "usage_series": await db.usage_series(7),
        "uptime_seconds": int(time.time() - _START),
        "started_at": _START_ISO,
        "model": settings.MODEL,
        "mode": settings.MODE,
        "rich": bool(getattr(settings, "USE_RICH_MESSAGES", True)),
        "tools": len(TOOLS),
        "providers": [{"name": p["name"], "model": p.get("model", "")} for p in chain],
        "provider_stats": pool.provider_stats(),
    }


@app.get("/api/users")
async def api_users(_=Depends(require_auth)):
    return {"users": await db.recent_users(24)}


@app.get("/api/conversations")
async def api_conversations(_=Depends(require_auth)):
    return {"conversations": await db.conversations()}


@app.get("/api/skills")
async def api_skills(_=Depends(require_auth)):
    return {"skills": await db.all_skills()}


@app.get("/api/logs")
async def api_logs(_=Depends(require_auth)):
    return {"events": await db.recent_events()}


@app.get("/api/blocked")
async def api_blocked(_=Depends(require_auth)):
    return {"blocked": await db.list_blocked()}


@app.get("/api/providers")
async def api_providers(_=Depends(require_auth)):
    from services.llm import pool
    return {
        "chain": [{"name": p["name"], "model": p.get("model", ""), "base_url": p["base_url"]} for p in settings.provider_chain()],
        "stats": pool.provider_stats(),
    }


@app.post("/api/block")
async def api_block(request: Request, user_id: int = Form(...), reason: str = Form(""), sess: dict = Depends(require_auth)):
    require_csrf(request, sess, (await request.form()).get("csrf"))
    if user_id <= 0:
        raise HTTPException(400, "bad user_id")
    await db.block_user(user_id, reason or "dashboard")
    return {"ok": True}


@app.post("/api/unblock")
async def api_unblock(request: Request, user_id: int = Form(...), sess: dict = Depends(require_auth)):
    require_csrf(request, sess, (await request.form()).get("csrf"))
    if user_id <= 0:
        raise HTTPException(400, "bad user_id")
    await db.unblock_user(user_id)
    return {"ok": True}


# ---------------------------------------------------------------- Mini App backend
@app.post("/api/miniapp/verify")
async def miniapp_verify(request: Request):
    """Verify Telegram WebApp initData; returns a signed token + user profile."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "expected JSON {initData}")
    user = verify_telegram_initdata(body.get("initData") or "")
    if not user:
        raise HTTPException(401, "initData verification failed")
    uid = int(user["id"])
    return {"ok": True, "token": issue_miniapp_token(uid), "user": user}


def _miniapp_user(request: Request) -> int:
    auth = request.headers.get("authorization", "")
    token = auth[7:] if auth.lower().startswith("bearer ") else request.query_params.get("token", "")
    return verify_miniapp_token(token)


@app.get("/api/miniapp/me")
async def miniapp_me(request: Request):
    uid = _miniapp_user(request)
    prem = await db.is_premium(uid)
    d_u, d_l = await db.usage_today(uid)
    m_u, m_l = await db.usage_month(uid)
    us = await db.get_user_settings(uid)
    return {
        "user_id": uid,
        "premium": prem,
        "usage": {"today": [d_u, d_l], "month": [m_u, m_l]},
        "language": us.get("language") or "en",
        "tts": bool(us.get("tts_enabled")),
        "has_byok": bool(us.get("api_key")),
    }


@app.get("/api/miniapp/memory")
async def miniapp_memory(request: Request):
    uid = _miniapp_user(request)
    mem = await db.get_user_memory(uid) or {}
    return {"memory": mem}


@app.get("/api/miniapp/projects")
async def miniapp_projects(request: Request):
    uid = _miniapp_user(request)
    return {"projects": await db.list_projects(uid)}


@app.get("/api/miniapp/skills")
async def miniapp_skills(request: Request):
    uid = _miniapp_user(request)
    return {"skills": await db.list_skills(uid)}


@app.get("/app", response_class=HTMLResponse)
async def mini_app(request: Request):
    return templates.TemplateResponse(request, "miniapp.html", {})


# ---------------------------------------------------------------- inbound webhook (e.g. GitHub)
@app.post("/inbound/{secret}")
async def inbound_webhook(secret: str, request: Request):
    expected = getattr(settings, "WEBHOOK_INBOUND_SECRET", "") or "obra-inbound"
    if not hmac.compare_digest(secret, expected):
        raise HTTPException(403, "bad secret")

    # GitHub signature verification (optional but recommended)
    gh_secret = getattr(settings, "GITHUB_WEBHOOK_SECRET", "") or ""
    if gh_secret:
        sig = request.headers.get("x-hub-signature-256", "")
        body = await request.body()
        if not sig.startswith("sha256="):
            raise HTTPException(403, "missing signature")
        calc = "sha256=" + hmac.new(gh_secret.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calc, sig):
            raise HTTPException(403, "bad signature")
        try:
            payload = json.loads(body.decode("utf-8", errors="replace") or "{}")
        except Exception:
            payload = {"raw": body.decode("utf-8", errors="replace")[:2000]}
    else:
        try:
            payload = await request.json()
        except Exception:
            payload = {"raw": (await request.body()).decode("utf-8", errors="replace")[:2000]}

    if isinstance(payload, dict) and payload.get("zen"):
        return {"ok": True, "telegram": None, "ping": True}

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
        text = "📥 Inbound webhook:\n<code>" + json.dumps(payload, ensure_ascii=False)[:1500] + "</code>"

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
