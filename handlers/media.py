"""Handle photos, voice, documents with AI."""

from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.enums import ChatAction, ContentType

from config.settings import settings
from services.db import db
from services.media_ai import describe_image, transcribe_voice, extract_document_text, summarize_text
from services import vector_memory

router = Router()


@router.message(F.photo)
async def on_photo(message: Message, bot: Bot):
    user = message.from_user
    if not user:
        return
    if await db.is_blocked(user.id):
        return
    if user.id not in settings.admin_list:
        ok, _ = await db.check_rate_limit(user.id)
        if not ok:
            await message.answer("⏳ Rate limit.")
            return
        ok_q, reason = await db.check_quotas(user.id)
        if not ok_q:
            await message.answer(f"🚫 {reason}")
            return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    photo = message.photo[-1]
    file = await bot.get_file(photo.file_id)
    buf = await bot.download_file(file.file_path)
    data = buf.read() if hasattr(buf, "read") else bytes(buf)

    prompt = message.caption or "Describe this image in detail. If there is text, OCR it."
    await message.answer("🖼️ Analyzing image…")
    desc = await describe_image(data, prompt)
    from services.telegram_send import send_rich
    await send_rich(bot, message.chat.id, desc[:4000] or "No description.", reply_to=message.message_id)
    await db.add_message(message.chat.id, "user", f"[photo] {prompt}")
    await db.add_message(message.chat.id, "assistant", desc[:2000])
    await db.log_event(user.id, message.chat.id, "vision", {})


@router.message(F.voice | F.audio)
async def on_voice(message: Message, bot: Bot):
    user = message.from_user
    if not user:
        return
    if await db.is_blocked(user.id):
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    media = message.voice or message.audio
    file = await bot.get_file(media.file_id)
    buf = await bot.download_file(file.file_path)
    data = buf.read() if hasattr(buf, "read") else bytes(buf)
    fname = "voice.ogg" if message.voice else (media.file_name or "audio.mp3")

    await message.answer("🎤 Transcribing…")
    text = await transcribe_voice(data, fname)
    if text.startswith("[transcription failed"):
        await message.answer(text)
        return
    await message.answer(f"<b>You said:</b>\n{text[:3500]}", parse_mode="HTML")
    # Feed into normal chat pipeline by storing as user text and answering via LLM
    from handlers.chat import process_user_text
    await process_user_text(message, bot, text)


@router.message(F.document)
async def on_document(message: Message, bot: Bot):
    user = message.from_user
    if not user:
        return
    if await db.is_blocked(user.id):
        return

    doc = message.document
    if not doc:
        return
    if user.id not in settings.admin_list:
        ok, _ = await db.check_rate_limit(user.id)
        if not ok:
            await message.answer("⏳ Rate limit.")
            return
        ok_q, reason = await db.check_quotas(user.id)
        if not ok_q:
            await message.answer(f"🚫 {reason}")
            return
    # size limit ~15MB for safety
    if doc.file_size and doc.file_size > 15 * 1024 * 1024:
        await message.answer("File too large (max ~15MB).")
        return

    await bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    file = await bot.get_file(doc.file_id)
    buf = await bot.download_file(file.file_path)
    data = buf.read() if hasattr(buf, "read") else bytes(buf)

    await message.answer(f"📄 Reading <code>{doc.file_name}</code>…", parse_mode="HTML")
    text = await extract_document_text(data, doc.file_name or "file.txt")
    if text.startswith("["):
        await message.answer(text)
        return
    summary = await summarize_text(text, style="structured key points")
    await message.answer(f"<b>Document summary</b>\n\n{summary[:4000]}", parse_mode="HTML")
    await db.add_message(message.chat.id, "user", f"[document {doc.file_name}]")
    await db.add_message(message.chat.id, "assistant", summary[:2000])
    try:
        await vector_memory.add_memory(
            user.id,
            f"Document {doc.file_name}: {summary[:400]}",
            metadata={"type": "document"},
        )
    except Exception:
        pass
    await db.log_event(user.id, message.chat.id, "document", {"name": doc.file_name})
