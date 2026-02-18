"""
Agent API — workflows, config, tools, executions, decisions, analyses, messages, SSE events
"""

import asyncio
import json

from fastapi import APIRouter, Body, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Any, Dict, Optional

from agent_trader.api.deps import get_trading_system
from agent_trader.trading_system import TradingSystem
from agent_trader.db.repository import TradingRepository
from agent_trader.agents.workflow_factory import WorkflowFactory, reload_external_workflows
from agent_trader.agents.workflow_base import event_broadcaster

router = APIRouter()

# SSE 独立 router — 不带 router 级别的 require_auth 依赖
# （EventSource 不支持 Authorization header，SSE endpoint 内部自行验证 query param token）
sse_router = APIRouter()


# ========== Workflows ==========

@router.get("/agent/workflows")
async def get_workflows():
    """获取所有已注册的 workflow 信息"""
    return WorkflowFactory.get_available_workflows()


@router.post("/agent/workflows/reload")
async def reload_workflows():
    """热重载外部 workflow 插件（user_data/agents/）"""
    result = reload_external_workflows()
    return {
        **result,
        "workflows": WorkflowFactory.get_available_workflows(),
    }


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
        "is_running": wf.is_running or ts._workflow_lock.locked(),
        "pending_triggers": len(ts._pending_triggers),
        "chat_queue_size": wf.chat_queue_size,
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


# ========== Chat (追加 / 新建) ==========

class ChatRequest(BaseModel):
    message: str


@router.post("/agent/chat")
async def agent_chat(
    body: ChatRequest,
    ts: TradingSystem = Depends(get_trading_system),
):
    """
    向 Agent 发送消息。

    - Agent 正在运行 → 消息追加到队列，当前 ReAct 循环结束后处理
    - Agent 空闲 → 触发新的 workflow 执行
    """
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")
    result = await ts.send_chat_message(body.message.strip())
    return result


@router.get("/agent/chat/queue")
async def get_chat_queue(ts: TradingSystem = Depends(get_trading_system)):
    """获取当前消息队列中的待处理消息"""
    wf = ts.trading_workflow
    messages = wf.get_queued_messages()
    return {
        "queue_size": len(messages),
        "messages": [
            {"index": i, "text": msg, "preview": msg[:100]}
            for i, msg in enumerate(messages)
        ],
    }


@router.delete("/agent/chat/queue/{index}")
async def cancel_queued_message(
    index: int,
    ts: TradingSystem = Depends(get_trading_system),
):
    """取消队列中指定位置的消息"""
    wf = ts.trading_workflow
    removed = wf.cancel_queued_message(index)
    if removed is None:
        raise HTTPException(status_code=404, detail=f"No message at index {index}")
    return {
        "success": True,
        "removed": removed,
        "queue_size": wf.chat_queue_size,
    }


@router.delete("/agent/chat/queue")
async def clear_chat_queue(ts: TradingSystem = Depends(get_trading_system)):
    """清空消息队列"""
    wf = ts.trading_workflow
    count = wf.clear_message_queue()
    return {
        "success": True,
        "cleared": count,
        "queue_size": 0,
    }


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
    offset: int = Query(default=0, ge=0),
):
    """获取 workflow 执行历史（来自 DB analysis_history），支持分页"""
    analyses = await TradingRepository.get_recent_analyses(
        trigger=trigger, limit=limit, offset=offset
    )
    total = await TradingRepository.count_analyses(trigger=trigger)
    return {
        "items": [a.to_dict() for a in analyses],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ========== Decisions ==========

@router.get("/agent/decisions")
async def get_decisions(
    symbol: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """获取交易决策历史，支持分页"""
    decisions = await TradingRepository.get_recent_decisions(
        symbol=symbol, limit=limit, offset=offset
    )
    total = await TradingRepository.count_decisions(symbol=symbol)
    return {
        "items": [d.to_dict() for d in decisions],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


# ========== Export (no limit cap) ==========

@router.get("/agent/executions/export")
async def export_executions(
    trigger: Optional[str] = Query(default=None),
    workflow_id: Optional[str] = Query(default=None),
    backtest_id: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)"),
):
    """导出分析历史（不限数量），支持按 trigger / workflow_id / backtest_id / 时间范围 过滤"""
    # 如果指定了 backtest_id，自动设置 trigger=backtest
    effective_trigger = trigger or ("backtest" if backtest_id else None)
    analyses = await TradingRepository.export_analyses(
        trigger=effective_trigger,
        workflow_id=workflow_id,
        backtest_id=backtest_id,
        date_from=date_from,
        date_to=date_to,
    )
    return [a.to_dict() for a in analyses]


@router.get("/agent/decisions/export")
async def export_decisions(
    symbol: Optional[str] = Query(default=None),
    date_from: Optional[str] = Query(default=None, description="Start date (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(default=None, description="End date (YYYY-MM-DD)"),
):
    """导出交易决策（不限数量），支持按 symbol / 时间范围 过滤"""
    decisions = await TradingRepository.export_decisions(
        symbol=symbol, date_from=date_from, date_to=date_to,
    )
    return [d.to_dict() for d in decisions]


@router.get("/agent/executions/triggers")
async def get_execution_triggers():
    """获取所有不同的 trigger 值（用于前端过滤选择）"""
    triggers = await TradingRepository.get_distinct_triggers()
    return triggers


@router.get("/agent/executions/backtests")
async def get_backtest_summaries():
    """获取回测摘要列表（用于导出时选择特定回测）"""
    return await TradingRepository.get_backtest_summaries()


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


# ========== SSE — 实时事件流 ==========
# 注意：此 endpoint 注册在 sse_router 上，不受 router 级别的 require_auth 保护。
# 鉴权在 endpoint 内部通过 query param token 手动验证。

@sse_router.get("/agent/events")
async def agent_events(
    request: Request,
    token: Optional[str] = Query(default=None),
    ts: TradingSystem = Depends(get_trading_system),
):
    """
    SSE endpoint — 实时推送 workflow 执行事件。

    EventSource 不支持自定义 header，因此通过 query param 传递 token。
    当鉴权启用时，必须提供有效的 token。

    **连接时自动 replay**: 如果有正在运行的 workflow，会先发送 workflow_start
    和所有已完成的 step 事件，让新连接的客户端能看到当前执行状态。

    事件类型:
    - workflow_start: workflow 开始执行
    - step: 新的执行步骤（由 Agent ReAct 循环动态产生）
    - step_update: 步骤状态更新
    - llm_token: LLM 输出 token（增量推送，前端可做打字机效果）
    - workflow_complete: workflow 执行完成
    - heartbeat: 心跳（每 15 秒）
    """
    from agent_trader.api.auth import is_auth_enabled, decode_access_token

    # 手动验证 token（因为 EventSource 无法使用 Authorization header）
    if is_auth_enabled():
        if not token:
            raise HTTPException(status_code=401, detail="Token required for SSE")
        decode_access_token(token)  # 无效则抛 401

    # 获取当前运行中的 workflow 快照（用于 replay）
    snapshot = ts.trading_workflow.get_live_execution_snapshot() if ts.trading_workflow else None

    queue = event_broadcaster.subscribe()

    async def event_stream():
        try:
            # ---- Replay: 如果有正在运行的 workflow，先发送当前状态 ----
            if snapshot:
                # 1. 发送 workflow_start
                start_data = json.dumps({
                    "workflow_id": snapshot["workflow_id"],
                    "workflow_type": snapshot["workflow_type"],
                    "trigger": snapshot["trigger"],
                    "timestamp": snapshot["started_at"],
                }, ensure_ascii=False, default=str)
                yield f"event: workflow_start\ndata: {start_data}\n\n"

                # 2. 发送所有已有的 steps
                for step in snapshot["steps"]:
                    step_data = json.dumps({
                        "workflow_id": snapshot["workflow_id"],
                        **step,
                    }, ensure_ascii=False, default=str)
                    yield f"event: step\ndata: {step_data}\n\n"

            # ---- 正常事件流 ----
            while True:
                # 检查客户端是否断开
                if await request.is_disconnected():
                    break

                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    event_type = event.get("event", "message")
                    data = json.dumps(event.get("data", event), ensure_ascii=False, default=str)
                    yield f"event: {event_type}\ndata: {data}\n\n"
                except asyncio.TimeoutError:
                    # 心跳
                    yield f"event: heartbeat\ndata: {{}}\n\n"
        finally:
            event_broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
