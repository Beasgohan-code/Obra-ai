"""Vision, voice transcription, document text extraction."""

from typing import Optional, Tuple
import io
import logging
from config.settings import settings
from services.llm import get_primary_client, chat_completion, AGENTS

logger = logging.getLogger("obra.media")


async def describe_image(image_bytes: bytes, prompt: str = "Describe this image in detail.") -> str:
    """Vision: send image to multimodal model if provider supports it."""
    try:
        import base64
        b64 = base64.b64encode(image_bytes).decode()
        client = get_primary_client()
        # Try OpenAI-style vision message
        model = settings.MODEL
        # Prefer a vision-capable model if configured
        vision_model = getattr(settings, "VISION_MODEL", "") or model
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                    },
                ],
            }
        ]
        resp = await client.chat.completions.create(
            model=vision_model,
            messages=messages,
            max_tokens=1500,
            temperature=0.4,
        )
        return resp.choices[0].message.content or "No description."
    except Exception as e:
        # Fallback: no vision
        return f"Vision not available on current provider/model: {e}"


async def transcribe_voice(audio_bytes: bytes, filename: str = "voice.ogg") -> str:
    """Speech-to-text via OpenAI-compatible audio transcriptions API."""
    try:
        client = get_primary_client()
        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        resp = await client.audio.transcriptions.create(
            model=getattr(settings, "WHISPER_MODEL", None) or "whisper-1",
            file=buf,
        )
        return getattr(resp, "text", None) or str(resp)
    except Exception as e:
        return f"[transcription failed: {e}]"


async def extract_document_text(file_bytes: bytes, filename: str) -> str:
    """Best-effort text from txt/md/json/csv/pdf (pdf if pypdf available)."""
    name = (filename or "").lower()
    try:
        if name.endswith((".txt", ".md", ".csv", ".json", ".log", ".py", ".js", ".ts", ".html")):
            return file_bytes.decode("utf-8", errors="replace")[:15000]
        if name.endswith(".pdf"):
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(file_bytes))
                parts = []
                for page in reader.pages[:30]:
                    parts.append(page.extract_text() or "")
                return "\n".join(parts)[:15000] or "[empty pdf text]"
            except ImportError:
                return "[install pypdf for PDF support: pip install pypdf]"
            except Exception as e:
                return f"[pdf error: {e}]"
        return f"[unsupported file type: {filename}]"
    except Exception as e:
        return f"[extract error: {e}]"


async def summarize_text(text: str, style: str = "brief") -> str:
    result = await chat_completion(
        messages=[{"role": "user", "content": f"Summarize ({style}):\n\n{text[:12000]}"}],
        system=AGENTS["summarizer"],
        temperature=0.3,
        max_tokens=1500,
    )
    return result.get("content") or "..."


async def translate_text(text: str, target_lang: str = "English") -> str:
    result = await chat_completion(
        messages=[{"role": "user", "content": f"Translate to {target_lang}. Only output the translation.\n\n{text[:8000]}"}],
        system="You are a precise translator.",
        temperature=0.2,
        max_tokens=2000,
    )
    return result.get("content") or "..."


async def extract_facts_for_memory(user_text: str, assistant_text: str) -> Optional[str]:
    """Return a short fact to store, or None."""
    try:
        result = await chat_completion(
            messages=[{
                "role": "user",
                "content": (
                    "From this exchange, extract ONE durable fact about the user "
                    "(preference, name, goal, location) if any. "
                    "If none, reply exactly NONE.\n\n"
                    f"User: {user_text[:500]}\nAssistant: {assistant_text[:500]}"
                ),
            }],
            system="Extract only stable personal facts. No fluff.",
            temperature=0.1,
            max_tokens=100,
        )
        fact = (result.get("content") or "").strip()
        if not fact or fact.upper() == "NONE" or len(fact) < 5:
            return None
        return fact[:300]
    except Exception:
        return None


async def text_to_speech(text: str, voice: str = "alloy") -> Optional[bytes]:
    """TTS via OpenAI-compatible audio.speech API. Returns mp3 bytes or None."""
    try:
        client = get_primary_client()
        resp = await client.audio.speech.create(
            model=getattr(settings, "TTS_MODEL", None) or "tts-1",
            voice=voice,
            input=text[:4000],
        )
        # openai SDK may return stream or content
        if hasattr(resp, "content") and isinstance(resp.content, (bytes, bytearray)):
            return bytes(resp.content)
        if hasattr(resp, "read"):
            return await resp.read()
        # newer SDK: resp is binary
        data = getattr(resp, "content", None)
        if data:
            return data
        return None
    except Exception as e:
        logger.warning("TTS failed: %s", e)
        return None
