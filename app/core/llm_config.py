"""Runtime LLM configuration.

Priority (highest → lowest):
  1. DB module assignment → provider config  (UI 配置，优先级最高)
  2. .env  LLM_API_KEY / LLM_BASE_URL / LLM_MODEL  (兜底默认值)
  3. Fallback: returns empty config (agent will degrade gracefully)
"""
from dataclasses import dataclass

from app.core.config import settings

# ── In-memory caches ──────────────────────────────────────────────────────────
_providers_cache: list[dict] = []     # list of provider dicts
_assignments_cache: dict = {}         # module_key → provider_id


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str


def get_llm_config_sync(module: str) -> LLMConfig:
    """Return LLM config for the given module (sync, reads from in-memory cache).

    Priority:
      1. DB module assignment → provider  (UI 界面配置，优先级最高)
      2. .env explicit values (LLM_BASE_URL + LLM_MODEL 均有值时生效)
      3. Empty config (agent degrades to rule-based fallback)
    """
    # 1. UI-configured DB assignment has highest priority
    provider_id = _assignments_cache.get(module)
    if provider_id:
        provider = next(
            (p for p in _providers_cache if p.get("id") == provider_id and p.get("enabled", True)),
            None,
        )
        if provider:
            return LLMConfig(
                api_key=provider.get("api_key", "") or "no-key",
                base_url=provider.get("base_url", ""),
                model=provider.get("model", ""),
            )

    # 2. Fall back to .env when explicitly configured (both base_url and model set)
    if settings.LLM_API_KEY != "your-api-key" and settings.LLM_BASE_URL and settings.LLM_MODEL:
        return LLMConfig(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
            model=settings.LLM_MODEL,
        )

    # 3. Degrade — agents will use rule-based fallback
    return LLMConfig(api_key="your-api-key", base_url="", model="")


def _is_local_url(url: str) -> bool:
    """Return True if the URL points to a local/LAN address."""
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    return host in ("localhost", "127.0.0.1", "::1") or host.startswith(("192.168.", "10.", "172."))


def make_openai_client(cfg: "LLMConfig"):
    """Return a synchronous OpenAI client configured for the given LLMConfig.

    Local/LAN addresses: trust_env=False to bypass proxy.
    Cloud APIs: trust_env=True so HTTP_PROXY/HTTPS_PROXY can be used.
    """
    import httpx
    from openai import OpenAI
    local = _is_local_url(cfg.base_url) if cfg.base_url else False
    return OpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url.rstrip("/") + "/" if cfg.base_url else None,
        http_client=httpx.Client(trust_env=not local, timeout=60),
    )


def refresh_providers_cache(providers: list[dict]) -> None:
    global _providers_cache
    _providers_cache = providers


def refresh_assignments_cache(assignments: dict) -> None:
    global _assignments_cache
    _assignments_cache = assignments


async def load_cache_from_db(db) -> None:
    """Load both caches from DB on app startup."""
    from sqlalchemy import select
    from app.models.system_config import SystemConfig

    result = await db.execute(select(SystemConfig))
    rows = result.scalars().all()

    for row in rows:
        if row.key == "model_providers":
            refresh_providers_cache(row.value.get("providers", []))
        elif row.key == "module_assignments":
            refresh_assignments_cache(row.value)
