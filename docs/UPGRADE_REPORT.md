# Obra-ai upgrade report

Branch: `arena/6f3c6463-obra-ai` (session branch; the requested
`upgrade/obra-premium-ai` could not be created — Arena sessions are locked to
their own branch, so all work was committed here in logical stages).

Base commit: `d7ff491` ("Idk why its not working")

## Audit findings (what was broken)

1. **Bot could not start without chromadb** — `services/vector_memory.py`
   imported chromadb at module import time; any install failure (heavy
   onnxruntime dep) crashed `bot.main` before it began.
2. **Double replies on greetings** — `handlers/chat.py` quick-reply branch was
   missing `return`, so "hi" got an instant reply AND a full LLM reply.
3. **Advertised commands did nothing** — README/FEATURES listed `/clear /lang
   /memory /skill /setkey /project /tts` but no handlers existed (slash messages
   were silently swallowed by the chat handler). `/ping /about /status`
   (extras router) were never registered at all.
4. **`/start bizChat` deep-link unreachable** — aiogram stops at the first
   matching handler, and `Command("start")` shadowed the secretary router.
5. **Embeddings used only OPENAI_* keys** — with only e.g. a Groq key, all
   vector memory silently failed.
6. **Sandbox could hang the whole bot** — in-process `exec` with no timeout
   (`while True: pass` would freeze the event loop).
7. **SSRF in fetch_url** — no private-IP/scheme/redirect checks.
8. **Payments not validated** — no currency/amount/payload/duplicate checks.
9. **Dashboard**: plain-text secret compare, no CSRF, no session expiry, no
   security headers, no rate limit on login; template API outdated for
   Starlette 1.x (crashed page renders); static mount pointed at wrong dir.
10. **Mini App** never verified `initData`; no backend APIs; prompts sent via
    `sendData` had no handler on the bot side.
11. **Provider pool** had no cooldown/retry/stats; one bad provider slowed
    every message.
12. History ordering by timestamp only (ties unstable); no input size cap;
    no token-budget clipping of long history messages.

## What was implemented

See commit log. Highlights per area:

### Stability & startup
- Lazy chromadb + sqlite keyword fallback memory; embeddings via provider
  chain + deterministic local hashed embedding fallback.
- Fixed double-reply; fixed router order (secretary → extras → commands →
  chat → media → inline → callbacks → payments → webapp); resilient
  polling/dashboard loops with auto-restart; `BOT_TOKEN` sanity check with a
  clear error message; duplicate `allowed_updates` removed.

### Security
- `services/ssrf.py`: scheme allowlist, credential-URL block, hostname
  blocklist, raw/encoded IP-literal blocking, DNS re-resolution (all A/AAAA
  must be public), redirect re-validation, 512 KB read cap.
- `services/sandbox.py`: subprocess `python -I` + timeout + rlimits +
  banned-pattern pre-check.
- Payments: XTR check, min-amount check, payload check, duplicate
  `telegram_payment_charge_id` via `processed_payments`.
- Pending actions: 15-min TTL; ownership check retained.
- Dashboard: constant-time compare, per-IP login throttle, 12 h expiring
  sessions, double-submit CSRF (cookie+field on login, header/field on
  writes), httponly/samesite/(secure) cookies, CSP + security headers,
  `/logout`, input validation, GitHub `X-Hub-Signature-256` when
  `GITHUB_WEBHOOK_SECRET` set.
- Mini App: `POST /api/miniapp/verify` (initData HMAC-SHA256 "WebAppData" +
  24 h freshness) issuing HMAC-signed 6 h tokens for `/api/miniapp/me|memory|projects|skills`.
- sqlite: WAL, busy_timeout, foreign_keys, migration runner
  (`schema_migrations`).

### AI architecture
- `ProviderPool`: per-provider failure cooldown (`PROVIDER_COOLDOWN_SECONDS`),
  healthy-first ordering, `LLM_TIMEOUT_SECONDS`, `PROVIDER_RETRIES` with
  backoff, automatic tools→no-tools fallback, stats (`/api/providers`).
- Input cap (`MAX_MESSAGE_CHARS`), per-message history clipping
  (`MAX_HISTORY_MSG_CHARS`).
- New commands incl. `/search` (chat history + memory), `/forget`, `/cancel`,
  `/usage`; unknown commands get a helpful reply instead of silence.
- `web_app_data` router: Mini App prompts run through the chat pipeline
  (with rate limit/quota/block checks, agent override).

### Dashboard (redesigned)
- Dark-first theme with light toggle, sidebar nav, stat cards, 7-day usage
  bar chart, provider health table, conversations, users (block/unblock),
  skills, event logs, security section — all wired to real JSON APIs.

### Mini App (upgraded)
- Premium chat composer with agent selector (`sendData`), usage meters,
  memory/projects/skills views — backed by verified endpoints.

### Tests
- `tests/` — 71 unittest tests (no network): agent routing, poll intent, rich
  formatting, calculator, sandbox (incl. hang timeout), SSRF, payments
  idempotency, pending TTL, initData verify (valid/tampered/stale), dashboard
  auth/CSRF/headers/inbound, provider cooldown, DB layer, memory fallback,
  dispatcher wiring.
- `BOT_TOKEN=... python -m unittest discover -s tests` → **71 passed**.

## How to run

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # BOT_TOKEN + ≥1 LLM key (Api.md)
python -m bot.main          # polling; set MODE=webhook for webhook mode
# dashboard: http://localhost:8080  (DASHBOARD_SECRET) · mini app: /app
BOT_TOKEN=123:xxx python -m unittest discover -s tests   # tests
```

Docker: `docker compose up -d --build` (ports 8080; add 8081 for webhook mode).

## Remaining TODOs / ideas

- True streaming token-by-token replies (Bot API) — currently thinking drafts.
- Multi-turn sub-agent orchestration (agent hand-offs) beyond routing.
- richer dashboard: per-user drill-down, log streaming (SSE), provider key editing UI.
- Mini App: file upload + voice record inside WebApp, streaming answers.
- Optional: move sessions/rate-limits to Redis for multi-instance deploys.
- chromadb remains in requirements for production vector quality, but is now optional at runtime.
