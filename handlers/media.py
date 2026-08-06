from aiogram import Router, F, Bot
from aiogram.types import Message
router = Router()

@router.message(F.photo)
async def on_photo(message: Message, bot: Bot):
    await message.answer("Photo received. Describe what you need (vision models depend on your LLM provider).")

@router.message(F.voice | F.audio)
async def on_voice(message: Message, bot: Bot):
    await message.answer("Voice received. STT needs Whisper-capable provider config.")

@router.message(F.document)
async def on_doc(message: Message, bot: Bot):
    await message.answer(f"Document: {message.document.file_name if message.document else 'file'}")
