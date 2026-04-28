import os
import logging

logger = logging.getLogger(__name__)

_PROVIDER_REGISTRY = {
    "foobar": ("chainlit_app.foobar_provider", "FooBarProvider"),
}


def _is_provider_configured(provider_class) -> bool:
    required_envs = getattr(provider_class, "env", [])
    return all(os.environ.get(e) for e in required_envs)


def _setup_providers() -> None:
    import importlib
    from chainlit_app.inject_custom_auth import add_custom_oauth_provider

    env_value = os.environ.get("OAUTH_CUSTOM_PROVIDERS", "").strip()
    requested = (
        [p.strip() for p in env_value.split(",") if p.strip()]
        if env_value
        else list(_PROVIDER_REGISTRY.keys())
    )

    for provider_id in requested:
        if provider_id not in _PROVIDER_REGISTRY:
            logger.warning(f"[oauth_setup] 未知的 provider: {provider_id!r}，略過")
            continue
        module_path, class_name = _PROVIDER_REGISTRY[provider_id]
        try:
            ProviderClass = getattr(importlib.import_module(module_path), class_name)
            if _is_provider_configured(ProviderClass):
                add_custom_oauth_provider(provider_id, ProviderClass())
                logger.info(f"[oauth_setup] 已註冊 OAuth provider: {provider_id!r}")
            else:
                logger.debug(f"[oauth_setup] Provider {provider_id!r} 缺少環境變數，略過")
        except Exception as e:
            logger.error(f"[oauth_setup] 載入 provider {provider_id!r} 失敗: {e}")


_setup_providers()
