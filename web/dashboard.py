from fastapi import FastAPI, Request, HTTPException
from config.settings import settings
app = FastAPI(title="Obra")

@app.get("/health")
async def health():
    return {"ok": True, "service": "obra"}

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
