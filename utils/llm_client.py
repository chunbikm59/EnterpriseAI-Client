import os
from dotenv import load_dotenv
from openai import AsyncOpenAI, OpenAI

# 載入 .env
load_dotenv()

def get_model_setting():
    # 可根據需求擴充
    return {
        "model": "gpt-4o-mini",
        "temperature": 1,
        "stream": True,
    }

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
