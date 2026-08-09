"""Obra web layer — health/uptime for Render + optional inbound webhook."""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, JSONResponse

from config.settings import settings

app = FastAPI(title="Obra", docs_url=None, redoc_url=None)

_START = time.time()
_START_ISO = datetime.now(timezone.utc).isoformat()


def _uptime_seconds() -> int:
    return int(time.time() - _START)


@app.get("/")
async def root():
    return {
        "service": "obra",
        "ok": True,
        "uptime_seconds": _uptime_seconds(),
        "started_at": _START_ISO,
    }


@app.get("/health")
@app.get("/uptime")
@app.get("/ping")
async def health():
    """UptimeRobot / Render health checks — keep free tier awake."""
    return {
        "ok": True,
        "service": "obra",
        "status": "up",
        "uptime_seconds": _uptime_seconds(),
        "started_at": _START_ISO,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/healthz")
async def healthz():
    """Plain 200 for strict monitors."""
    return PlainTextResponse("ok", status_code=200)


@app.post("/inbound/{secret}")
async def inbound(secret: str, request: Request):
    expected = getattr(settings, "WEBHOOK_INBOUND_SECRET", "") or "obra-inbound"
    if secret != expected:
        raise HTTPException(403, "bad secret")
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": (await request.body()).decode("utf-8", errors="replace")[:1500]}
    return {"ok": True, "received": True}
