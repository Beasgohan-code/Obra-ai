# Obra AI

Telegram AI agent (aiogram 3.30+, Bot API 10.x Rich Messages).

## Run
```bash
cd Obra-ai
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set BOT_TOKEN + LLM keys
python -m bot.main
```

## Scheduler
```
/skill every 1 minutes: send me hi
/skill list
```
User must have started the bot in **private chat**. Keep process running (Render: Background Worker).

## Commands
/start /help /clear /skill /lang /memory
