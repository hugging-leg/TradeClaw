"""
Agent API — workflows, config, tools, executions, decisions, analyses, messages
"""

from fastapi import APIRouter, Body, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import Any, Dict, Optional

from src.api.deps import get_trading_system
from src.trading_system import TradingSystem
from src.db.repository import TradingRepository
from src.agents.workflow_factory import WorkflowFactory

router = APIRouter()


# ========== Workflows ==========

@router.get("/agent/workflows")
async def get_workflows():
    """获取所有已注册的 workflow 信息"""
    return WorkflowFactory.get_available_workflows()


# ========== Active Workflow & Switching ==========

@router.get("/agent/active")
async def get_active_workflow(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前活跃的 workflow 类型及基本信息"""
    wf = ts.trading_workflow
    wf_type = wf.get_workflow_type()
    meta = getattr(wf, "_workflow_metadata", {})
    return {
        "workflow_type": wf_type,
        "name": meta.get("description", wf_type),
        "is_running": wf.is_running,
        "stats": wf.stats,
    }


class SwitchWorkflowRequest(BaseModel):
    workflow_type: str


@router.post("/agent/switch")
async def switch_workflow(
    body: SwitchWorkflowRequest,
    ts: TradingSystem = Depends(get_trading_system),
):
    """切换到不同的 workflow"""
    try:
        result = await ts.switch_workflow(body.workflow_type)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ========== Agent Config ==========

@router.get("/agent/config")
async def get_agent_config(ts: TradingSystem = Depends(get_trading_system)):
    """
    获取当前 workflow 的可编辑配置。

    返回的字段完全由 workflow 自身声明，不同 workflow 返回不同的字段。
    """
    return ts.get_workflow_config()


@router.patch("/agent/config")
async def update_agent_config(
    updates: Dict[str, Any] = Body(...),
    ts: TradingSystem = Depends(get_trading_system),
):
    """
    更新当前 workflow 的配置（运行时，不持久化到 .env）。

    接受任意 key-value，由 workflow 自身决定哪些字段可更新。
    """
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    result = ts.update_workflow_config(updates)
    return {"updated": list(updates.keys()), "config": result}


# ========== Tools ==========

@router.get("/agent/tools")
async def get_tools(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前 workflow 的 tools 元数据（含 enabled 状态）"""
    registry = getattr(ts.trading_workflow, "tool_registry", None)
    if registry is None:
        return []
    return registry.get_metadata()


class ToolToggleRequest(BaseModel):
    enabled: bool


@router.patch("/agent/tools/{tool_name}")
async def toggle_tool(
    tool_name: str,
    body: ToolToggleRequest,
    ts: TradingSystem = Depends(get_trading_system),
):
    """启用/禁用指定 tool，并重建 agent"""
    registry = getattr(ts.trading_workflow, "tool_registry", None)
    if registry is None:
        raise HTTPException(status_code=404, detail="当前 workflow 不支持 tool 管理")

    ok = registry.set_enabled(tool_name, body.enabled)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' 不存在")

    # 重建 agent 以应用新的 tool 列表
    rebuild = getattr(ts.trading_workflow, "rebuild_agent", None)
    if rebuild:
        rebuild()

    return {"name": tool_name, "enabled": body.enabled}


# ========== Workflow Execution History ==========

@router.get("/agent/executions")
async def get_executions(
    trigger: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取 workflow 执行历史（来自 DB analysis_history）"""
    analyses = await TradingRepository.get_recent_analyses(
        trigger=trigger, limit=limit
    )
    return [a.to_dict() for a in analyses]


# ========== Decisions ==========

@router.get("/agent/decisions")
async def get_decisions(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    """获取交易决策历史"""
    decisions = await TradingRepository.get_recent_decisions(
        symbol=symbol, limit=limit
    )
    return [d.to_dict() for d in decisions]


# ========== Agent Messages ==========

@router.get("/agent/messages")
async def get_messages(
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
):
    """获取 Agent 消息历史"""
    if session_id:
        messages = await TradingRepository.get_agent_messages(
            session_id=session_id, limit=limit
        )
    else:
        messages = []
    return [m.to_dict() for m in messages]


# ========== Workflow Stats ==========

@router.get("/agent/stats")
async def get_workflow_stats(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前 workflow 的运行统计"""
    workflow = ts.trading_workflow
    return {
        "workflow_type": workflow.get_workflow_type(),
        "is_running": workflow.is_running,
        "stats": workflow.stats,
    }
