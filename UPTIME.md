# Keep Obra awake on Render (Uptime)

Render **free Web Services** sleep after ~15 min with no HTTP traffic.
Telegram polling then stops until the next request.

## Option A — UptimeRobot (recommended)

1. Deploy Obra as a **Web Service** on Render (not only Background Worker).
2. Start command: `python -m bot.main`
3. After deploy, open: `https://YOUR-APP.onrender.com/health`
   - Should return `{"ok": true, "status": "up", ...}`
4. Create free monitor at https://uptimerobot.com
   - **Monitor type:** HTTP(s)
   - **URL:** `https://YOUR-APP.onrender.com/health`
   - **Interval:** 5 minutes
5. Alternative paths (same result): `/uptime` `/ping` `/healthz`

## Option B — Built-in self-ping

On Render Web Service, `RENDER_EXTERNAL_URL` is set automatically.
Obra pings `/health` every 4 minutes by itself.

Or set in Render env:
```
PUBLIC_URL=https://YOUR-APP.onrender.com
```

## Option C — Background Worker

Background Workers on Render do **not** sleep the same way, but:
- No public HTTP URL
- Still need a paid/free worker slot
- UptimeRobot cannot ping them

For free tier + Telegram bot, **Web Service + UptimeRobot** is the usual setup.

## Render settings checklist

| Setting | Value |
|---------|--------|
| Type | Web Service |
| Runtime | Python |
| Build | `pip install -r requirements.txt` |
| Start | `python -m bot.main` |
| Health check path | `/health` (optional) |
| Env | `BOT_TOKEN`, LLM keys, `USE_RICH_MESSAGES=true` |

Port: Obra reads `PORT` from Render automatically.
