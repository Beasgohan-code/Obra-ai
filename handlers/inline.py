from aiogram import Router
from aiogram.types import InlineQuery, InlineQueryResultArticle, InputTextMessageContent
router = Router()

@router.inline_query()
async def on_inline(q: InlineQuery):
    text = q.query or "obra"
    results = [InlineQueryResultArticle(id="1", title="obra", description=text[:60], input_message_content=InputTextMessageContent(message_text=f"obra: {text}"))]
    await q.answer(results, cache_time=1)
