# Free & low-cost APIs for obra

Where to get keys used by this bot. Always check current free-tier limits on the provider site.

---

## Telegram

| What | URL | Notes |
|------|-----|--------|
| **Bot token** | https://t.me/BotFather | `/newbot` → copy token → `BOT_TOKEN` |
| API ID / Hash (only if you use MTProto userbots) | https://my.telegram.org | Not required for pure aiogram bots |

---

## LLM providers (chat + tools)

### OpenRouter (many models, some free)
- https://openrouter.ai/keys  
- Set `OPENAI_API_KEY` + `OPENAI_BASE_URL=https://openrouter.ai/api/v1`  
- Free examples: `google/gemini-2.0-flash-exp:free`, other `:free` models on the site  
- Optional second key: `OPENROUTER_API_KEY`

### Groq (fast free tier)
- https://console.groq.com/keys  
- `GROQ_API_KEY=gsk_...`  
- Default fallback model: `llama-3.3-70b-versatile`

### DeepSeek (very cheap)
- https://platform.deepseek.com  
- `DEEPSEEK_API_KEY=sk-...`  
- Model: `deepseek-chat`

### Together AI
- https://api.together.xyz  
- `TOGETHER_API_KEY=...`

### OpenAI
- https://platform.openai.com/api-keys  
- Paid; works as primary with `OPENAI_BASE_URL=https://api.openai.com/v1`

### Custom / self-hosted
Add JSON in `.env`:
```env
FREE_FALLBACKS=[{"name":"local","base_url":"http://127.0.0.1:8000/v1","api_key":"x","model":"local-model"}]
```

**How fallback works:** primary is tried first; on failure the next provider in the chain is used automatically (`/providers` shows order).

---

## Embeddings (vector memory)

Use the same OpenAI-compatible key when possible:

| Provider | Model example |
|----------|----------------|
| OpenAI | `text-embedding-3-small` |
| OpenRouter | route an embedding model if available |
| Local | any OpenAI-compatible embedding server |

Set `EMBEDDING_MODEL=...`

---

## Web search

| Provider | URL | Env var |
|----------|-----|---------|
| **Tavily** | https://tavily.com | `TAVILY_API_KEY` (free tier) |
| **Serper** | https://serper.dev | `SERPER_API_KEY` (free credits) |

One of them is enough for `web_search`.

---

## Weather

| Provider | URL | Env var |
|----------|-----|---------|
| OpenWeatherMap | https://openweathermap.org/api | `OPENWEATHER_API_KEY` (free tier) |

---

## Image generation

Uses the **primary** OpenAI-compatible client:

| Provider | Notes |
|----------|--------|
| OpenAI DALL·E | `IMAGE_MODEL=dall-e-3` |
| OpenRouter | set a model that supports images on that platform |

---

## Gmail + Google Calendar (optional)

Not fully free automation — you need a Google Cloud project + OAuth.

1. https://console.cloud.google.com → create project  
2. Enable **Gmail API** + **Google Calendar API**  
3. OAuth consent screen + OAuth client (Desktop or Web)  
4. Obtain access token (and refresh token) for scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/calendar`
5. Put in `.env`:
```env
GOOGLE_ACCESS_TOKEN=...
GOOGLE_REFRESH_TOKEN=...
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Tools: `gmail_unread`, `gmail_send`, `calendar_upcoming`, `calendar_create`.

---

## Mini App / Dashboard

| Item | Notes |
|------|--------|
| `WEBAPP_URL` | Public HTTPS URL to `/app` (ngrok, Cloudflare Tunnel, VPS) |
| `DASHBOARD_SECRET` | Password for http://host:8080 |

---

## Suggested minimal free stack

```env
BOT_TOKEN=...
GROQ_API_KEY=...
TAVILY_API_KEY=...
OPENWEATHER_API_KEY=...
# optional secondary
DEEPSEEK_API_KEY=...
```

Primary can be Groq-only by setting:
```env
OPENAI_API_KEY=<same as groq or leave empty and only set GROQ_API_KEY>
OPENAI_BASE_URL=https://api.groq.com/openai/v1
MODEL=llama-3.3-70b-versatile
```

Or use OpenRouter free models as primary and Groq as fallback.

---

## Security tips

- Never commit `.env`  
- Restrict `ADMIN_IDS`  
- Rotate keys if leaked  
- Google tokens can send email / change calendar — keep them private  


---

## Vision & voice

| Feature | Requirement |
|---------|-------------|
| Image understanding | Multimodal model (e.g. `gpt-4o` via OpenRouter/OpenAI). Set `VISION_MODEL` or use a vision-capable `MODEL`. |
| Voice transcription | OpenAI-compatible `/audio/transcriptions` (Whisper). Set `WHISPER_MODEL=whisper-1` when supported. Groq also offers whisper in some setups. |
| PDF summary | `pypdf` (in requirements). Send a `.pdf` document to the bot. |

