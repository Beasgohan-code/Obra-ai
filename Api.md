# Free LLM APIs for Obra

Source: [awesome-freellm-apis](https://github.com/open-free-llm-api/awesome-freellm-apis) · [freellm.net](https://freellm.net)

Obra tries providers **in order** until one works. Set keys in `.env` / Render. Empty keys are skipped.

## Recommended (no credit card)

| Env key | Base URL | Get key | Default model |
|---------|----------|---------|---------------|
| `GROQ_API_KEY` | api.groq.com/openai/v1 | https://console.groq.com/keys | llama-3.3-70b-versatile |
| `CEREBRAS_API_KEY` | api.cerebras.ai/v1 | https://cloud.cerebras.ai/ | llama-3.3-70b |
| `MISTRAL_API_KEY` | api.mistral.ai/v1 | https://console.mistral.ai/api-keys | mistral-small-latest |
| `GEMINI_API_KEY` | Google OpenAI-compat | https://aistudio.google.com/app/apikey | gemini-2.0-flash |
| `LLM7_API_KEY` | api.llm7.io/v1 | https://token.llm7.io | gpt-4o-mini |
| `GITHUB_MODELS_TOKEN` | models.github.ai/inference | https://github.com/marketplace/models | openai/gpt-4o-mini |
| `HF_TOKEN` | router.huggingface.co/v1 | https://huggingface.co/settings/tokens | Meta-Llama-3.1-8B |
| `ZHIPU_API_KEY` | open.bigmodel.cn/api/paas/v4 | https://open.bigmodel.cn/usercenter/apikeys | glm-4-flash |

## Registration / phone free tiers

| Env key | Get key |
|---------|---------|
| `NVIDIA_API_KEY` | https://build.nvidia.com/settings/api-keys |
| `SAMBANOVA_API_KEY` | https://cloud.sambanova.ai/apis |
| `OPENROUTER_API_KEY` | https://openrouter.ai/workspaces/default/keys |
| `DEEPSEEK_API_KEY` | https://platform.deepseek.com/api_keys |
| `XAI_API_KEY` | https://console.x.ai |
| `SILICONFLOW_API_KEY` | https://cloud.siliconflow.cn/account/ak |
| `OLLAMA_API_KEY` | https://ollama.com/settings/keys |
| `MODELSCOPE_API_KEY` | https://modelscope.cn/my/myaccesstoken |
| `ALIBABA_API_KEY` | Alibaba Model Studio |
| `OVH_API_KEY` | OVH AI Endpoints |
| `CHUTES_API_KEY` | https://chutes.ai/ |
| `GLHF_API_KEY` | https://glhf.chat/ |
| `NEBIUS_API_KEY` | https://studio.nebius.com/settings/api-keys |
| `NSCALE_API_KEY` | https://console.nscale.com/ |
| `AGNES_API_KEY` | https://platform.agnes-ai.com/settings/apiKeys |
| `AION_API_KEY` | https://www.aionlabs.ai |
| `AI21_API_KEY` | https://studio.ai21.com/account/api-key |
| `TOGETHER_API_KEY` | Together AI |

## Custom

```env
FREE_FALLBACKS=[{"name":"myproxy","base_url":"https://example.com/v1","api_key":"sk-...","model":"gpt-4o-mini"}]
```

## Minimal free setup

```env
BOT_TOKEN=...
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=...
OPENROUTER_API_KEY=sk-or-v1-...
```

Cloudflare Workers AI and Cohere v2 are **not** auto-wired (different API shape). Use FREE_FALLBACKS with a proxy if needed.
