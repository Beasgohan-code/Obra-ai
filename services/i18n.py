"""Simple multi-language strings + system language hint."""

LANGS = {
    "en": "English",
    "hi": "Hindi",
    "es": "Spanish",
    "fr": "French",
    "de": "German",
    "ar": "Arabic",
    "pt": "Portuguese",
    "ru": "Russian",
    "zh": "Chinese",
    "ja": "Japanese",
    "ko": "Korean",
    "tr": "Turkish",
    "id": "Indonesian",
    "bn": "Bengali",
    "ur": "Urdu",
}

STRINGS = {
    "en": {
        "welcome": "Hey! I'm <b>obra</b> 🤖 — your AI agent.",
        "rate_limit": "⏳ Rate limit reached. Try again soon.",
        "quota": "📅 Daily quota reached. Come back tomorrow.",
        "history_cleared": "History cleared.",
        "no_memory": "No long-term notes yet.",
        "lang_set": "Language set to <b>{lang}</b>. I'll reply in this language when possible.",
        "tts_on": "TTS enabled — replies may include voice notes.",
        "tts_off": "TTS disabled.",
        "confirm_send": "⚠️ Confirm sending this email?",
        "cancelled": "Cancelled.",
        "done": "Done.",
    },
    "hi": {
        "welcome": "नमस्ते! मैं <b>obra</b> 🤖 हूँ — आपका AI एजेंट।",
        "rate_limit": "⏳ रेट लिमिट। थोड़ी देर बाद कोशिश करें।",
        "quota": "📅 आज की सीमा पूरी हो गई।",
        "history_cleared": "इतिहास साफ़ किया गया।",
        "no_memory": "अभी कोई लंबी मेमोरी नहीं।",
        "lang_set": "भाषा <b>{lang}</b> सेट हो गई।",
        "tts_on": "TTS चालू।",
        "tts_off": "TTS बंद।",
        "confirm_send": "⚠️ यह ईमेल भेजें?",
        "cancelled": "रद्द।",
        "done": "हो गया।",
    },
    "es": {
        "welcome": "¡Hola! Soy <b>obra</b> 🤖 — tu agente de IA.",
        "rate_limit": "⏳ Límite de velocidad. Inténtalo más tarde.",
        "quota": "📅 Cuota diaria agotada.",
        "history_cleared": "Historial borrado.",
        "no_memory": "Sin memoria a largo plazo aún.",
        "lang_set": "Idioma configurado a <b>{lang}</b>.",
        "tts_on": "TTS activado.",
        "tts_off": "TTS desactivado.",
        "confirm_send": "⚠️ ¿Confirmar envío de este correo?",
        "cancelled": "Cancelado.",
        "done": "Listo.",
    },
}


def t(lang_code: str, key: str, **kwargs) -> str:
    """Translate `key` for language `lang_code` with {placeholder} formatting."""
    block = STRINGS.get(lang_code) or STRINGS["en"]
    s = block.get(key) or STRINGS["en"].get(key, key)
    try:
        return s.format(**kwargs)
    except Exception:
        return s


def language_system_hint(lang: str) -> str:
    name = LANGS.get(lang, lang)
    if lang == "en":
        return ""
    return f"\n\nIMPORTANT: Reply in {name} ({lang}) unless the user clearly asks for another language."
