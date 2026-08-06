# Obra feature checklist

## Core AI
- Multi-provider LLM fallback + BYOK-ready settings
- Auto agent routing (coder / researcher / writer / solver / summarizer)
- Dynamic max tokens (up to 16k on big requests)
- Tool calling with retries / self-check
- Vector memory + key-value memory + auto facts
- Group shared brain

## Telegram Bot API 9.4–10.2
- Rich Messages (sendRichMessage, drafts, thinking)
- Button styles primary / success / danger
- WELCOME style animation every 3s
- Ephemeral group whispers (rate limit / quota)
- Polls (auto-detect + tool)
- Reactions
- Documents / photos / voice pipeline

## Tools
- web_search, fetch_url, wikipedia, weather
- calculator, translate, current_time
- create_file / create_zip
- run_python sandbox
- GitHub list / read / issue
- Gmail / Calendar (optional keys)
- save_skill / list_skills / scheduler

## UX
- Minimal commands: start help clear skill lang memory
- Styled /start banner + buttons
- Continue / Retry on long answers
- Multi-language /lang
- Admin stats block unblock
- Inbound webhooks
- Dashboard / Mini App templates

## Verify after deploy
1. `/start` — photo + colored buttons
2. Chat “explain X with a table” — rich formatting
3. `/skill every 1 minutes: send me hi` — keep process alive
4. “create hello.py …” — document file
5. “wiki Alan Turing” — wikipedia tool
