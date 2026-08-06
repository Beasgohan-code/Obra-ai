from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
import hashlib
from services.llm import chat_completion, AGENTS
from services.db import db

router = Router()


@router.inline_query()
async def inline_search(query: InlineQuery):
    text = (query.query or "").strip()
    if len(text) < 2:
        await query.answer(
            [
                InlineQueryResultArticle(
                    id="help",
                    title="Type a question for obra",
                    input_message_content=InputTextMessageContent(
                        message_text="Ask me something via inline: @your_bot your question"
                    ),
                )
            ],
            cache_time=5,
            is_personal=True,
        )
        return

    user_id = query.from_user.id if query.from_user else 0
    us = await db.get_user_settings(user_id)
    provider = None
    if us.get("api_key"):
        provider = {"api_key": us["api_key"], "api_base": us.get("api_base"), "api_model": us.get("api_model")}

    try:
        result = await chat_completion(
            messages=[{"role": "user", "content": text}],
            system=AGENTS["default"] + "\nKeep the answer under 800 characters for inline mode.",
            temperature=0.5,
            max_tokens=500,
            user_provider=provider,
        )
        answer = (result.get("content") or "...")[:900]
    except Exception as e:
        answer = f"Error: {e}"

    rid = hashlib.md5(text.encode()).hexdigest()[:16]
    await query.answer(
        [
            InlineQueryResultArticle(
                id=rid,
                title=answer[:60] + ("…" if len(answer) > 60 else ""),
                description="Tap to send obra's answer",
                input_message_content=InputTextMessageContent(message_text=f"🤖 {answer}"),
            )
        ],
        cache_time=10,
        is_personal=True,
    )
