# Obra — feature checklist

## Commands
- /start · /help only

## Agents (auto)
coder · researcher · writer · solver · summarizer · terminal

## Rich Messages
Thinking drafts · headings · tables · 32k · direct Bot API

## Coding
Full projects · create_file / create_zip · auto-export · up to 32k tokens

## Premium (Telegram Stars)
Daily + monthly quotas · upgrade via Stars invoice

## Skills
Natural schedule · reply to .md "make skill" · list/delete via AI tools

## Memory
remember / forget · vector memory · group brain · set_language

## Terminal
run_python sandbox · `run: ...`

## Secretary Mode
business_message auto-reply · /secretary via natural language settings

## Free LLMs
Groq, Gemini 3.6, Cerebras, Mistral, OpenRouter, NVIDIA, … (Api.md)

## Ops
Uptime /health · self-ping · rate limits · dashboard

## Upgrade pass (branch arena/6f3c6463-obra-ai)
- ✅ Startup without chromadb (sqlite memory fallback) · double-reply fix
- ✅ All advertised commands working (/clear /lang /memory /forget /skill /setkey /project /tts /usage /search /cancel) + /ping /about /status
- ✅ Security: SSRF guard · subprocess sandbox · payment validation + dedupe · pending TTL · dashboard CSRF/sessions/headers · initData verify · GitHub webhook HMAC
- ✅ Provider failover: cooldown + retries + timeouts + stats
- ✅ Premium dashboard (dark/light) wired to live APIs
- ✅ Mini App workspace with verified initData + sendData bridge
- ✅ 71 unittest tests: python -m unittest discover -s tests
