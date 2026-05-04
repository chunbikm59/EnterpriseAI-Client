import os
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

load_dotenv(override=True)

_MODEL_CONFIGS: dict[str, dict] = {
    "Qwen 3.5": {
        "display_name": "Qwen 3.5 122B",
        "model": "qwen/qwen3.5-122b-a10b",
        "temperature": 0.7,
        "stream": True,
        "thinking_budget_tokens_enabled": True,
    },
    "Qwen 3.6": {
        "display_name": "Qwen 3.6 27B",
        "model": "qwen/qwen3.6-27b",
        "temperature": 0.7,
        "stream": True,
        "thinking_budget_tokens_enabled": True,
    },
}

_DEFAULT_PROFILE = "Qwen 3.5"

def get_all_model_configs() -> dict[str, dict]:
    return _MODEL_CONFIGS

def get_model_config(profile_name: str | None = None) -> dict:
    if profile_name and profile_name in _MODEL_CONFIGS:
        return _MODEL_CONFIGS[profile_name]
    return _MODEL_CONFIGS[_DEFAULT_PROFILE]

def get_model_setting() -> dict:
    """向後相容 shim，供背景模組（overseer、memory 等）使用。"""
    cfg = get_model_config(None)
    return {"model": cfg["model"], "temperature": cfg["temperature"], "stream": cfg["stream"]}

def get_llm_client(provider: str = None, mode: str = "async", base_url: str = None, api_key: str = None):
    """
    provider: "openai" (預設), 之後可擴充其他
    mode: "async" 或 "sync"
    """
    provider = provider or os.getenv("LLM_PROVIDER", "openai")
    base_url = base_url or os.getenv("BASE_URL", None)
    api_key = api_key or os.getenv("LLM_API_KEY", None)

    if provider == "openai":
        if mode == "async":
            return AsyncOpenAI(base_url=base_url, api_key=api_key)
        else:
            return OpenAI(base_url=base_url, api_key=api_key)
        
    raise ValueError(f"Unknown provider: {provider}")
