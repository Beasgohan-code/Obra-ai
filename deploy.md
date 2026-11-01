# Deploy obra (polling or webhook + HTTPS)

## 1. Server basics

```bash
git clone / copy obra_full
cd obra_full
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit secrets
```

## 2. Polling (simplest)

```bash
python -m bot.main
# or: docker compose up -d --build
```

Dashboard: `http://SERVER_IP:8080`

## 3. Webhook mode (recommended for production)

`.env`:
```env
MODE=webhook
WEBHOOK_URL=https://bot.example.com
WEBHOOK_PATH=/webhook
WEBHOOK_SECRET=long-random-string
DASHBOARD_PORT=8080
```

Bot webhook server listens on **:8081**. Dashboard on **:8080**.

### Caddy example

```caddyfile
bot.example.com {
  handle /webhook* {
    reverse_proxy 127.0.0.1:8081
  }
  handle /app* {
    reverse_proxy 127.0.0.1:8080
  }
  handle {
    reverse_proxy 127.0.0.1:8080
  }
}
```

### nginx example

```nginx
server {
  listen 443 ssl;
  server_name bot.example.com;
  # ssl_certificate ...;

  location /webhook {
    proxy_pass http://127.0.0.1:8081;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  }
  location / {
    proxy_pass http://127.0.0.1:8080;
  }
}
```

Set `WEBAPP_URL=https://bot.example.com/app`

## 4. Checklist

- [ ] BOT_TOKEN from @BotFather  
- [ ] At least one LLM key (see Api.md)  
- [ ] ADMIN_IDS set  
- [ ] DASHBOARD_SECRET strong  
- [ ] Firewall: 80/443 public; 8080/8081 localhost only if reverse-proxied  
- [ ] For inline mode: BotFather → Bot Settings → Inline Mode → Enable  
- [ ] HTTPS required for Mini App & webhook  

## 5. Docker

```bash
docker compose up -d --build
docker compose logs -f
```

Map ports 8080 (and 8081 if webhook) or put Caddy in front on the host.

## 6. Security extras

- Set `DASHBOARD_SECRET` to a long random string; dashboard login is rate-limited and CSRF-protected.
- Set `GITHUB_WEBHOOK_SECRET` to enforce `X-Hub-Signature-256` on `POST /inbound/{WEBHOOK_INBOUND_SECRET}`.
- Mini App: open `https://YOUR-HOST/app` in Telegram; initData is verified server-side.
- Keep 8080/8081 bound to localhost when reverse-proxying (see above).
