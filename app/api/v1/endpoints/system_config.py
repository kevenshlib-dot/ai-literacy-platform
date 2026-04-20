"""System configuration API — admin only.

Two config keys in system_configs:
  • model_providers  → list of provider definitions
  • module_assignments → module key → provider id
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.database import get_db
from app.core.llm_config import refresh_providers_cache, refresh_assignments_cache, check_llm_status
from app.models.system_config import SystemConfig
from app.models.user import User

router = APIRouter(prefix="/system", tags=["系统管理"])

PROVIDERS_KEY   = "model_providers"
ASSIGNMENTS_KEY = "module_assignments"

MODULE_KEYS = [
    "question_generation",
    "paper_generation",
    "paper_import",
    "scoring",
    "interactive",
    "annotation",
    "review",
    "indicator",
]


# ── Schemas ───────────────────────────────────────────────────────────────────

class ProviderIn(BaseModel):
    name: str
    provider_type: str          # openai / anthropic / google / deepseek / doubao / qwen / vllm / ollama / lmstudio / custom
    api_key: str = ""
    base_url: str = ""
    model: str = ""
    enabled: bool = True


class ProviderOut(ProviderIn):
    id: str
    has_api_key: bool = False


class AssignmentsPayload(BaseModel):
    question_generation: Optional[str] = None
    paper_generation: Optional[str] = None
    paper_import: Optional[str] = None
    scoring: Optional[str] = None
    interactive: Optional[str] = None
    annotation: Optional[str] = None
    review: Optional[str] = None
    indicator: Optional[str] = None


class TestPayload(BaseModel):
    api_key: str = ""
    base_url: str = ""
    model: str = ""


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _get_row(db: AsyncSession, key: str) -> SystemConfig:
    result = await db.execute(select(SystemConfig).where(SystemConfig.key == key))
    row = result.scalar_one_or_none()
    if row is None:
        default = {"providers": []} if key == PROVIDERS_KEY else {}
        row = SystemConfig(key=key, value=default)
        db.add(row)
        await db.flush()
    return row


async def _get_providers(db: AsyncSession) -> list[dict]:
    row = await _get_row(db, PROVIDERS_KEY)
    return row.value.get("providers", [])


async def _save_providers(db: AsyncSession, providers: list[dict], username: str):
    row = await _get_row(db, PROVIDERS_KEY)
    row.value = {"providers": providers}
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = username
    await db.commit()
    refresh_providers_cache(providers)


def _mask_api_key(api_key: str) -> str:
    if not api_key:
        return ""
    if len(api_key) <= 8:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * 8}{api_key[-4:]}"


def _provider_out(provider: dict) -> dict:
    api_key = provider.get("api_key", "") or ""
    return {
        **provider,
        "api_key": _mask_api_key(api_key),
        "has_api_key": bool(api_key),
    }


def _provider_payload_with_existing_key(payload: ProviderIn, existing: dict) -> dict:
    data = payload.model_dump()
    existing_key = existing.get("api_key", "") or ""
    submitted_key = data.get("api_key", "") or ""
    if not submitted_key or submitted_key == _mask_api_key(existing_key):
        data["api_key"] = existing_key
    return data


def _payload_for_provider(provider: dict, payload: TestPayload | None = None) -> TestPayload:
    payload_data = payload.model_dump() if payload else {}
    api_key = payload_data.get("api_key") or provider.get("api_key", "") or ""
    base_url = payload_data.get("base_url") or provider.get("base_url", "") or ""
    model = payload_data.get("model") or provider.get("model", "") or ""
    return TestPayload(api_key=api_key, base_url=base_url, model=model)


async def _get_provider_or_404(db: AsyncSession, provider_id: str) -> dict:
    providers = await _get_providers(db)
    provider = next((p for p in providers if p["id"] == provider_id), None)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


# ── Provider endpoints ────────────────────────────────────────────────────────

@router.get("/providers", response_model=list[ProviderOut])
async def list_providers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    return [_provider_out(p) for p in await _get_providers(db)]


@router.post("/providers", response_model=ProviderOut)
async def create_provider(
    payload: ProviderIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    providers = await _get_providers(db)
    new_provider = {"id": str(uuid.uuid4()), **payload.model_dump()}
    providers.append(new_provider)
    await _save_providers(db, providers, current_user.username)
    return _provider_out(new_provider)


@router.put("/providers/{provider_id}", response_model=ProviderOut)
async def update_provider(
    provider_id: str,
    payload: ProviderIn,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    providers = await _get_providers(db)
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    providers[idx] = {
        "id": provider_id,
        **_provider_payload_with_existing_key(payload, providers[idx]),
    }
    await _save_providers(db, providers, current_user.username)
    return _provider_out(providers[idx])


@router.delete("/providers/{provider_id}")
async def delete_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    providers = await _get_providers(db)
    providers = [p for p in providers if p["id"] != provider_id]
    await _save_providers(db, providers, current_user.username)
    # Also remove from assignments
    row = await _get_row(db, ASSIGNMENTS_KEY)
    assignments = dict(row.value)
    changed = False
    for k, v in list(assignments.items()):
        if v == provider_id:
            assignments[k] = None
            changed = True
    if changed:
        row.value = assignments
        await db.commit()
        refresh_assignments_cache(assignments)
    return {"ok": True}


# ── Module assignments endpoints ──────────────────────────────────────────────

@router.get("/assignments", response_model=AssignmentsPayload)
async def get_assignments(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    row = await _get_row(db, ASSIGNMENTS_KEY)
    return AssignmentsPayload(**{k: row.value.get(k) for k in MODULE_KEYS})


@router.put("/assignments", response_model=AssignmentsPayload)
async def update_assignments(
    payload: AssignmentsPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(["admin"])),
):
    row = await _get_row(db, ASSIGNMENTS_KEY)
    row.value = payload.model_dump()
    row.updated_at = datetime.now(timezone.utc)
    row.updated_by = current_user.username
    await db.commit()
    refresh_assignments_cache(row.value)
    return payload


# ── Test connection ───────────────────────────────────────────────────────────

async def _test_provider_connection(payload: TestPayload):
    if not payload.base_url or not payload.model:
        raise HTTPException(status_code=400, detail="base_url 和 model 不能为空")
    base_url = payload.base_url.rstrip("/") + "/"
    try:
        import httpx
        from openai import OpenAI
        from app.core.llm_config import _is_local_url
        local = _is_local_url(payload.base_url)
        client = OpenAI(
            api_key=payload.api_key or "no-key",
            base_url=base_url,
            http_client=httpx.Client(trust_env=not local, timeout=30),
        )
        resp = client.chat.completions.create(
            model=payload.model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=20,
        )
        # Qwen3 thinking models may return content=None with reasoning field — still a success
        content = None
        if resp.choices:
            msg = resp.choices[0].message
            content = getattr(msg, "content", None) or getattr(msg, "reasoning", None)
        return {"success": True, "model": resp.model, "reply": content}
    except Exception as e:
        err = str(e)
        hint = ""
        if "Connection refused" in err or "connect" in err.lower():
            hint = " — 请确认服务地址和端口是否正确，服务是否已启动"
        elif "404" in err or "Not Found" in err:
            hint = " — 路径不存在，请确认 base_url 末尾包含 /v1"
        elif "model" in err.lower() and ("not found" in err.lower() or "does not exist" in err.lower()):
            hint = " — 模型名称与服务端不匹配，请用「获取模型列表」确认名称"
        raise HTTPException(status_code=502, detail=f"连接失败：{err}{hint}")


@router.post("/providers/test")
async def test_provider(
    payload: TestPayload,
    _: User = Depends(require_role(["admin"])),
):
    return await _test_provider_connection(payload)


@router.post("/providers/{provider_id}/test")
async def test_saved_provider(
    provider_id: str,
    payload: TestPayload | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    provider = await _get_provider_or_404(db, provider_id)
    return await _test_provider_connection(_payload_for_provider(provider, payload))


class ModelsPayload(BaseModel):
    api_key: str = ""
    base_url: str


async def _list_models_for_provider(payload: ModelsPayload):
    try:
        import httpx
        from openai import OpenAI
        from app.core.llm_config import _is_local_url
        local = _is_local_url(payload.base_url)
        client = OpenAI(
            api_key=payload.api_key or "no-key",
            base_url=payload.base_url.rstrip("/") + "/",
            http_client=httpx.Client(trust_env=not local, timeout=15),
        )
        models = client.models.list()
        names = sorted(m.id for m in models.data)
        return {"models": names}
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"获取模型列表失败：{e}")


@router.post("/providers/models")
async def list_provider_models(
    payload: ModelsPayload,
    _: User = Depends(require_role(["admin"])),
):
    """Fetch available models from an OpenAI-compatible server."""
    return await _list_models_for_provider(payload)


@router.post("/providers/{provider_id}/models")
async def list_saved_provider_models(
    provider_id: str,
    payload: ModelsPayload | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_role(["admin"])),
):
    provider = await _get_provider_or_404(db, provider_id)
    payload_data = payload.model_dump() if payload else {}
    models_payload = ModelsPayload(
        api_key=payload_data.get("api_key") or provider.get("api_key", "") or "",
        base_url=payload_data.get("base_url") or provider.get("base_url", "") or "",
    )
    return await _list_models_for_provider(models_payload)


@router.get("/llm-status")
async def get_llm_status(
    current_user: User = Depends(require_role(["admin", "organizer"])),
):
    """Check LLM configuration status for all modules.

    Returns which modules have LLM configured and which are using rule-based fallback.
    No authentication needed beyond login — any logged-in user can check.
    """
    return check_llm_status()
