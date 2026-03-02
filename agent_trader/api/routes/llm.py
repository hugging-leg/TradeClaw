"""
LLM 配置 API — Provider/Model 管理、角色绑定、连通性测试
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

from agent_trader.api.deps import get_trading_system
from agent_trader.config.llm_config import get_llm_config_manager
from agent_trader.utils.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter()


def _notify_workflow_llm_changed() -> None:
    """Notify the running workflow that LLM config has changed."""
    try:
        ts = get_trading_system()
        ts.rebuild_workflow_llm()
    except Exception as e:
        # TradingSystem may not be initialized yet (e.g. during startup)
        logger.debug("Could not notify workflow of LLM config change: %s", e)


# ========== Providers ==========

@router.get("/llm/providers")
async def get_providers():
    """获取所有 LLM Provider 和 Model 列表（api_key 脱敏）"""
    mgr = get_llm_config_manager()
    return {
        "providers": mgr.get_providers_sanitized(),
        "models": mgr.get_all_model_names(),
    }


class UpdateProvidersRequest(BaseModel):
    """更新完整的 LLM 配置"""
    providers: List[Dict[str, Any]]
    roles: Optional[Dict[str, str]] = None


@router.put("/llm/providers")
async def update_providers(body: UpdateProvidersRequest):
    """更新完整的 LLM Provider 配置（持久化到 YAML）"""
    mgr = get_llm_config_manager()
    current = mgr.get_config()

    # Restore masked API keys: the frontend receives sanitized keys (e.g. "sk-a****xyz").
    # If the user didn't change a key, it comes back still masked.  We must replace
    # masked keys with the real values from the current config to avoid overwriting
    # real keys with masked strings.
    current_keys: Dict[str, str] = {
        p.id: p.api_key for p in current.providers
    }
    for provider_data in body.providers:
        incoming_key = provider_data.get("api_key", "")
        provider_id = provider_data.get("id", "")
        if "*" in incoming_key and provider_id in current_keys:
            # Key was not changed by the user — restore the real key
            provider_data["api_key"] = current_keys[provider_id]

    # 构建新配置
    data: Dict[str, Any] = {"providers": body.providers}
    if body.roles is not None:
        data["roles"] = body.roles
    else:
        data["roles"] = current.roles.model_dump()

    try:
        config = mgr.update_config(data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid config: {e}")

    # Rebuild the running workflow's LLM client so new API keys take effect immediately
    _notify_workflow_llm_changed()

    return {
        "providers": mgr.get_providers_sanitized(),
        "models": mgr.get_all_model_names(),
        "roles": config.roles.model_dump(),
    }


# ========== Roles ==========

@router.get("/llm/roles")
async def get_roles():
    """获取角色绑定"""
    mgr = get_llm_config_manager()
    return mgr.get_roles()


class UpdateRolesRequest(BaseModel):
    """更新角色绑定"""
    roles: Dict[str, str]


@router.patch("/llm/roles")
async def update_roles(body: UpdateRolesRequest):
    """更新角色绑定（持久化到 YAML）"""
    mgr = get_llm_config_manager()
    result = mgr.update_roles(body.roles)

    # Role binding change may point to a different model — rebuild LLM client
    _notify_workflow_llm_changed()

    return result


# ========== Model List (flat) ==========

@router.get("/llm/models")
async def get_models():
    """获取所有已注册的 model 列表（扁平化，用于下拉选择）"""
    mgr = get_llm_config_manager()
    return mgr.get_all_model_names()


# ========== Test Connectivity ==========

class TestModelRequest(BaseModel):
    model_name: str


@router.post("/llm/test")
async def test_model(body: TestModelRequest):
    """测试指定 model name 的连通性"""
    mgr = get_llm_config_manager()
    resolved = mgr.resolve_model(body.model_name)
    if resolved is None:
        raise HTTPException(
            status_code=404,
            detail=f"Model '{body.model_name}' not found in config"
        )

    base_url, api_key, model_id, temperature = resolved

    try:
        from agent_trader.utils.llm_utils import create_llm_client
        llm = create_llm_client(
            base_url=base_url,
            api_key=api_key,
            model=model_id,
            temperature=temperature,
        )
        # 简单测试：发送一个短消息
        response = await llm.ainvoke("Say 'OK' in one word.")
        return {
            "success": True,
            "model_name": body.model_name,
            "model_id": model_id,
            "base_url": base_url,
            "response": str(response.content)[:200],
        }
    except Exception as e:
        return {
            "success": False,
            "model_name": body.model_name,
            "model_id": model_id,
            "base_url": base_url,
            "error": str(e),
        }
