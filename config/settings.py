from pydantic_settings import BaseSettings
from typing import List, Dict, Any
import json


class Settings(BaseSettings):
    BOT_TOKEN: str
    WEBAPP_URL: str = ""
    WELCOME_PHOTO_URL: str = "https://picsum.photos/seed/obra-ai/800/450"
    CHANNEL_URL: str = ""

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    MODEL: str = "openai/gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    MODEL_CODER: str = ""
    MODEL_RESEARCHER: str = ""
    MODEL_WRITER: str = ""

    # JSON list of extra providers
    FREE_FALLBACKS: str = "[]"

    GROQ_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""

    MAX_HISTORY_TURNS: int = 20
    ADMIN_IDS: str = ""
    GROUP_MENTION_ONLY: bool = True
    USE_RICH_MESSAGES: bool = True
    AUTO_REMEMBER: bool = True

    RATE_LIMIT_MESSAGES: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    DAILY_QUOTA: int = 200
    MAX_TOKENS_SMALL: int = 2048
    MAX_TOKENS_MEDIUM: int = 6144
    MAX_TOKENS_BIG: int = 16384
    AUTO_REACT: bool = True
    AUTO_PROJECT_TITLE: bool = True

    SERPER_API_KEY: str = ""
    TAVILY_API_KEY: str = ""
    IMAGE_MODEL: str = "dall-e-3"
    VISION_MODEL: str = ""  # e.g. openai/gpt-4o — empty uses MODEL
    WHISPER_MODEL: str = "whisper-1"
    TTS_MODEL: str = "tts-1"
    ENABLE_AUTO_FACTS: bool = True
    OPENWEATHER_API_KEY: str = ""
    GITHUB_TOKEN: str = ""
    WEBHOOK_INBOUND_SECRET: str = "obra-inbound"
    TOOL_MAX_RETRIES: int = 2
    ENABLE_SANDBOX: bool = True

    # Google (optional — Gmail / Calendar tools)
    GOOGLE_ACCESS_TOKEN: str = ""
    GOOGLE_REFRESH_TOKEN: str = ""
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""

    # Scheduler
    ENABLE_SCHEDULER: bool = True
    SKILL_CHECK_MINUTES: int = 1

    DASHBOARD_SECRET: str = "change-me"
    DASHBOARD_HOST: str = "0.0.0.0"
    DASHBOARD_PORT: int = 8080

    MODE: str = "polling"
    WEBHOOK_URL: str = ""
    WEBHOOK_PATH: str = "/webhook"
    WEBHOOK_SECRET: str = ""

    DB_PATH: str = "data/obra.db"
    CHROMA_PATH: str = "data/chroma"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"

    @property
    def admin_list(self) -> List[int]:
        if not self.ADMIN_IDS.strip():
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip().isdigit()]

    def model_for(self, agent: str) -> str:
        m = {
            "coder": self.MODEL_CODER or self.MODEL,
            "researcher": self.MODEL_RESEARCHER or self.MODEL,
            "writer": self.MODEL_WRITER or self.MODEL,
            "summarizer": self.MODEL,
        }.get(agent, self.MODEL)
        return m or self.MODEL

    def provider_chain(self) -> List[Dict[str, Any]]:
        chain: List[Dict[str, Any]] = []
        primary_key = self.OPENAI_API_KEY or self.OPENROUTER_API_KEY
        if primary_key:
            chain.append({
                "name": "primary",
                "base_url": self.OPENAI_BASE_URL,
                "api_key": primary_key,
                "model": self.MODEL,
            })
        if self.GROQ_API_KEY:
            chain.append({
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": self.GROQ_API_KEY,
                "model": "llama-3.3-70b-versatile",
            })
        if self.DEEPSEEK_API_KEY:
            chain.append({
                "name": "deepseek",
                "base_url": "https://api.deepseek.com/v1",
                "api_key": self.DEEPSEEK_API_KEY,
                "model": "deepseek-chat",
            })
        if self.TOGETHER_API_KEY:
            chain.append({
                "name": "together",
                "base_url": "https://api.together.xyz/v1",
                "api_key": self.TOGETHER_API_KEY,
                "model": "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",
            })
        if self.OPENROUTER_API_KEY and self.OPENROUTER_API_KEY != primary_key:
            chain.append({
                "name": "openrouter_free",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": self.OPENROUTER_API_KEY,
                "model": "google/gemini-2.0-flash-exp:free",
            })
        try:
            extra = json.loads(self.FREE_FALLBACKS or "[]")
            if isinstance(extra, list):
                for item in extra:
                    if item.get("api_key") and item.get("base_url"):
                        chain.append({
                            "name": item.get("name", "fallback"),
                            "base_url": item["base_url"],
                            "api_key": item["api_key"],
                            "model": item.get("model", self.MODEL),
                        })
        except Exception:
            pass
        seen = set()
        unique = []
        for p in chain:
            key = (p["base_url"], p["api_key"][:12])
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique


settings = Settings()
