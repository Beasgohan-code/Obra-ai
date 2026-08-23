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

    # JSON list of extra providers (any OpenAI-compatible endpoint)
    FREE_FALLBACKS: str = "[]"

    # --- Free / fallback keys (awesome-freellm-apis) ---
    GROQ_API_KEY: str = ""
    TOGETHER_API_KEY: str = ""
    DEEPSEEK_API_KEY: str = ""
    OPENROUTER_API_KEY: str = ""
    NVIDIA_API_KEY: str = ""
    CEREBRAS_API_KEY: str = ""
    MISTRAL_API_KEY: str = ""
    SAMBANOVA_API_KEY: str = ""
    GITHUB_MODELS_TOKEN: str = ""  # or reuse GITHUB_TOKEN
    LLM7_API_KEY: str = ""
    HF_TOKEN: str = ""
    SILICONFLOW_API_KEY: str = ""
    XAI_API_KEY: str = ""
    ZHIPU_API_KEY: str = ""
    OLLAMA_API_KEY: str = ""
    CHUTES_API_KEY: str = ""
    GLHF_API_KEY: str = ""
    AI21_API_KEY: str = ""
    NEBIUS_API_KEY: str = ""
    NSCALE_API_KEY: str = ""
    AGNES_API_KEY: str = ""
    AION_API_KEY: str = ""
    MODELSCOPE_API_KEY: str = ""
    OVH_API_KEY: str = ""
    ALIBABA_API_KEY: str = ""
    GEMINI_API_KEY: str = ""
    # Optional model overrides per provider
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    NVIDIA_MODEL: str = "meta/llama-3.3-70b-instruct"
    CEREBRAS_MODEL: str = "llama-3.3-70b"
    MISTRAL_MODEL: str = "mistral-small-latest"
    SAMBANOVA_MODEL: str = "Meta-Llama-3.3-70B-Instruct"
    GITHUB_MODELS_MODEL: str = "openai/gpt-4o-mini"
    LLM7_MODEL: str = "gpt-4o-mini"
    HF_MODEL: str = "meta-llama/Meta-Llama-3.1-8B-Instruct"
    SILICONFLOW_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"
    XAI_MODEL: str = "grok-2-latest"
    ZHIPU_MODEL: str = "glm-4-flash"
    OLLAMA_MODEL: str = "llama3.2"
    CHUTES_MODEL: str = "deepseek-ai/DeepSeek-V3"
    GLHF_MODEL: str = "hf:meta-llama/Meta-Llama-3.1-70B-Instruct"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    GEMINI_MODEL: str = "gemini-3.6-flash"
    MODELSCOPE_MODEL: str = "Qwen/Qwen2.5-72B-Instruct"
    ALIBABA_MODEL: str = "qwen-turbo"
    OVH_MODEL: str = "Meta-Llama-3_3-70B-Instruct"
    NEBIUS_MODEL: str = "meta-llama/Meta-Llama-3.1-70B-Instruct"
    NSCALE_MODEL: str = "meta-llama/Llama-3.3-70B-Instruct"
    AGNES_MODEL: str = "agnes-default"
    AION_MODEL: str = "aion-1.0"
    AI21_MODEL: str = "jamba-mini"

    MAX_HISTORY_TURNS: int = 20
    ADMIN_IDS: str = ""
    GROUP_MENTION_ONLY: bool = True
    USE_RICH_MESSAGES: bool = True
    AUTO_REMEMBER: bool = True

    RATE_LIMIT_MESSAGES: int = 30
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    DAILY_QUOTA: int = 50
    DAILY_QUOTA_PREMIUM: int = 500
    MONTHLY_QUOTA: int = 500
    MONTHLY_QUOTA_PREMIUM: int = 10000
    PREMIUM_STARS_PRICE: int = 50
    PREMIUM_DAYS: int = 30
    PREMIUM_TITLE: str = "Obra Premium"
    PREMIUM_DESC: str = "Higher limits, priority, full coding power for 30 days"
    MAX_TOKENS_CODE: int = 32000
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
        """
        Ordered LLM fallbacks. Prefer reliable free tiers first.
        Groq → OpenAI/OpenRouter → others → Gemini last (strict quotas).
        """
        chain: List[Dict[str, Any]] = []

        def add(name: str, base_url: str, api_key: str, model: str):
            if not (api_key or "").strip():
                return
            chain.append({
                "name": name,
                "base_url": (base_url or "").rstrip("/"),
                "api_key": api_key.strip(),
                "model": model or self.MODEL,
            })

        # 1) Groq — best free + tools
        add("groq", "https://api.groq.com/openai/v1", self.GROQ_API_KEY, self.GROQ_MODEL)

        # 2) Official OpenAI (only if key looks like sk- and base is openai OR explicit)
        openai_key = self.OPENAI_API_KEY or ""
        base = (self.OPENAI_BASE_URL or "").rstrip("/")
        is_openrouter_key = openai_key.startswith("sk-or-")
        is_openai_key = openai_key.startswith("sk-") and not is_openrouter_key
        if is_openai_key and ("api.openai.com" in base or not base or base == "https://api.openai.com/v1"):
            add("openai", "https://api.openai.com/v1", openai_key, self.MODEL if not self.MODEL.startswith("google/") else "gpt-4o-mini")
        elif openai_key and not is_openrouter_key and "openai.com" in base:
            add("openai", base or "https://api.openai.com/v1", openai_key, self.MODEL)

        # 3) OpenRouter
        or_key = self.OPENROUTER_API_KEY or (openai_key if is_openrouter_key else "")
        if or_key:
            add("openrouter", "https://openrouter.ai/api/v1", or_key,
                self.MODEL if "openrouter" in base or is_openrouter_key else "google/gemini-2.5-flash:free")

        # 4) Primary custom (if different from above)
        primary_key = self.OPENAI_API_KEY or self.OPENROUTER_API_KEY
        if primary_key and base and "openai.com" not in base and "openrouter.ai" not in base and "groq.com" not in base:
            # e.g. user pointed OPENAI_* at another proxy
            if "generativelanguage.googleapis.com" not in base:
                add("primary", base, primary_key, self.MODEL)

        # 5) Other free tiers
        add("cerebras", "https://api.cerebras.ai/v1", self.CEREBRAS_API_KEY, self.CEREBRAS_MODEL)
        add("mistral", "https://api.mistral.ai/v1", self.MISTRAL_API_KEY, self.MISTRAL_MODEL)
        add("nvidia", "https://integrate.api.nvidia.com/v1", self.NVIDIA_API_KEY, self.NVIDIA_MODEL)
        add("sambanova", "https://api.sambanova.ai/v1", self.SAMBANOVA_API_KEY, self.SAMBANOVA_MODEL)
        add("llm7", "https://api.llm7.io/v1", self.LLM7_API_KEY, self.LLM7_MODEL)
        add("github_models", "https://models.github.ai/inference",
            self.GITHUB_MODELS_TOKEN or self.GITHUB_TOKEN, self.GITHUB_MODELS_MODEL)
        add("huggingface", "https://router.huggingface.co/v1", self.HF_TOKEN, self.HF_MODEL)
        add("deepseek", "https://api.deepseek.com/v1", self.DEEPSEEK_API_KEY, self.DEEPSEEK_MODEL)
        add("together", "https://api.together.xyz/v1", self.TOGETHER_API_KEY,
            "meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo")
        add("xai", "https://api.x.ai/v1", self.XAI_API_KEY, self.XAI_MODEL)
        add("siliconflow", "https://api.siliconflow.cn/v1", self.SILICONFLOW_API_KEY, self.SILICONFLOW_MODEL)
        add("ollama_cloud", "https://api.ollama.com/v1", self.OLLAMA_API_KEY, self.OLLAMA_MODEL)
        add("zhipu", "https://open.bigmodel.cn/api/paas/v4", self.ZHIPU_API_KEY, self.ZHIPU_MODEL)
        add("modelscope", "https://api-inference.modelscope.cn/v1", self.MODELSCOPE_API_KEY, self.MODELSCOPE_MODEL)
        add("alibaba", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1", self.ALIBABA_API_KEY, self.ALIBABA_MODEL)
        add("chutes", "https://api.chutes.ai/v1", self.CHUTES_API_KEY, self.CHUTES_MODEL)
        add("glhf", "https://glhf.chat/api/openai/v1", self.GLHF_API_KEY, self.GLHF_MODEL)
        add("nebius", "https://api.studio.nebius.com/v1", self.NEBIUS_API_KEY, self.NEBIUS_MODEL)

        # 6) Gemini LAST — strict quotas / thought_signature issues
        add("gemini", "https://generativelanguage.googleapis.com/v1beta/openai/",
            self.GEMINI_API_KEY, self.GEMINI_MODEL)

        # Custom extras
        try:
            extra = json.loads(self.FREE_FALLBACKS or "[]")
            if isinstance(extra, list):
                for item in extra:
                    if item.get("api_key") and item.get("base_url"):
                        add(item.get("name", "custom"), item["base_url"], item["api_key"],
                            item.get("model") or self.MODEL)
        except Exception:
            pass

        seen = set()
        unique: List[Dict[str, Any]] = []
        for p in chain:
            key = (p["base_url"], p["api_key"][:16])
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique



settings = Settings()
