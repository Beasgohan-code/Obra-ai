# Keep Obra awake on Render

## Health URLs
- https://YOUR-APP.onrender.com/health
- /uptime /ping /healthz

## UptimeRobot
1. Monitor type: HTTP(s)
2. URL: https://obra-ai.onrender.com/health
3. Interval: 5 minutes

## Self-ping
Render sets RENDER_EXTERNAL_URL automatically on Web Services.
Or set PUBLIC_URL=https://obra-ai.onrender.com

## Deploy
- Type: Web Service
- Start: python -m bot.main
- Health path: /health
