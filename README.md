# Obra AI — self-hosted multi-language AI agent for Telegram

**Package:** `Obra-ai.zip` · Python 3.11+ · aiogram 3.x

## Features

- Multi-agent (coder · researcher · writer · solver · summarizer · terminal) + tools + Rich Messages + vector memory + auto-facts
- **Multi-language** (`/lang en|hi|es|…`) — replies follow user language
- **TTS** (`/tts on|off`) — voice note replies
- **Inline mode** — `@bot your question`
- **BYOK** — `/setkey <key> [base] [model]` personal LLM key (masked in chat)
- **Projects** — `/project <title>` named chats
- **Search** — `/search <q>` searches this chat + long-term memory
- **Confirm-before-send** for Gmail (pending actions expire after 15 min)
- Skills + cron scheduler, vision, voice STT, documents, Gmail/Calendar, GitHub
- Rate limits, daily/monthly quotas, Telegram Stars premium
- **Admin dashboard** (dark/light, live stats) + **Mini App** workspace
- Webhook + polling, self-ping keep-alive, health endpoints
- Resilient provider chain: automatic failover, cooldowns, retries, per-agent models
- Memory works even without chromadb (sqlite keyword fallback) or an embeddings key

## Quick start

```bash
unzip obra_full.zip && cd obra_full
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt        # chromadb optional — memory falls back to sqlite
cp .env.example .env                   # set BOT_TOKEN + at least one LLM key (see Api.md)
python -m bot.main                     # or: ./run.sh  or  docker compose up -d --build
```

Dashboard: `http://SERVER_IP:8080` (login with `DASHBOARD_SECRET`) · Mini App: `https://your-host/app`

## Commands

`/start` `/help` `/clear` `/lang <code>` `/memory` `/forget` `/skill` `/setkey`
`/project <title>` `/tts on|off` `/usage` `/search <q>` `/cancel` `/ping` `/about` `/status`

…or just chat in plain language — agents and tools handle the rest.

## Architecture

```
bot/main.py          entrypoint: polling/webhook + dashboard + self-ping + scheduler
config/settings.py   env-based config, provider_chain() (ordered LLM fallbacks)
handlers/            commands · chat · media · inline · callbacks · payments · secretary · webapp
database: services/db.py (sqlite, WAL, migrations) · services/vector_memory.py (chroma→sqlite fallback)
services/llm.py      ProviderPool: failover, cooldown, retries, stats, BYOK
services/tools.py    tool registry (web, wiki, weather, files, github, google, sandbox…)
services/ssrf.py     URL-fetch SSRF guard
services/sandbox.py  isolated subprocess Python sandbox
web/                 FastAPI dashboard + Mini App (CSRF, sessions, initData verification)
tests/               unittest suite — run: python -m unittest discover -s tests -v
```

## Security notes

- Pending actions (e.g. Gmail send) are user-bound and expire; payments are
  validated (XTR currency, min amount, payload, duplicate charge id).
- Dashboard: constant-time secret, per-IP login rate limit, expiring sessions,
  double-submit CSRF, security headers.
- Mini App verifies Telegram `initData` (HMAC-SHA256, `WebAppData`).
- `fetch_url` blocks private/loopback/metadata IPs (incl. DNS-rebinding).
- `run_python` runs in a subprocess with timeout + rlimits + pattern blocklist.
- GitHub inbound webhooks: set `GITHUB_WEBHOOK_SECRET` to enforce `X-Hub-Signature-256`.
- Never commit `.env` (gitignored). Keys are masked in logs/chat.

## Tests

```bash
python -m unittest discover -s tests -v     # 71 tests, no network needed
```

## Docs

- `Api.md` — free LLM providers & keys
- `BOT_API.md` — Telegram Bot API feature coverage
- `deploy.md` — polling / webhook / Docker / reverse proxy
- `UPTIME.md` — Render keep-alive
- `FEATURES.md` — feature checklist
- `docs/UPGRADE_REPORT.md` — audit findings & upgrade log
