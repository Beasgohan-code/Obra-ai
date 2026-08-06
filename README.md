**Package:** `Obra-ai.zip`

# Obra AI — self-hosted multi-language AI agent

## Features

- Multi-agent + tools + Rich Messages + vector memory + auto-facts  
- **Multi-language** (`/lang en|hi|es|…`) — replies follow user language  
- **TTS** (`/tts on|off`) — voice note replies  
- **Inline mode** — `@bot your question`  
- **BYOK** — `/setkey` personal LLM key  
- **Projects** — `/project title` named chats  
- **Confirm-before-send** for Gmail  
- Skills + cron, vision, voice STT, documents, Gmail/Calendar  
- Rate limits, dashboard, Mini App, webhook  
- **deploy.md** + **Api.md**

## Quick start

```bash
unzip obra_full.zip && cd obra_full
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m bot.main
```

Just chat with the bot. Commands: `/start` `/help` `/clear` `/skill` `/lang` `/memory`.