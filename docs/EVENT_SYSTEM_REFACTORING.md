# 📢 事件系统重构

**日期**: 2025-10-03  
**问题**: 原事件系统混杂了订单通知和workflow触发，职责不清晰

---

## 🎯 重构目标

将事件系统**专注于workflow触发和调度**，而不是订单通知。

### 之前的问题

```python
# ❌ 旧设计：事件系统做太多事
- order_created - 订单通知（应该workflow内部处理）
- order_filled - 订单通知（不需要事件系统）
- order_canceled - 订单通知（不需要）
- order_rejected - 订单通知（不需要）
- portfolio_updated - 组合更新通知（不需要）
- system_started / system_stopped - 系统状态（保留）

# 问题：
# 1. Scheduler直接调用trading_system的方法
# 2. Realtime monitor直接调用workflow
# 3. 订单通知走事件系统，但workflow内部不能拆分
# 4. 耦合度高，不易维护
```

### 新设计原则

```python
# ✅ 新设计：专注workflow触发
事件类型：
- trigger_daily_rebalance - 每日定时触发
- trigger_realtime_rebalance - 实时市场事件触发（价格波动、新闻等）
- trigger_manual_analysis - 手动触发分析
- trigger_portfolio_check - 定时组合检查
- trigger_risk_check - 风险检查
- trigger_eod_analysis - 日终分析
- schedule_next_analysis - LLM自主调度（可选，暂未实现）
- system_started / system_stopped - 系统状态事件

# 优势：
# 1. 职责单一：只负责workflow调度
# 2. 解耦：Scheduler/RealtimeMonitor发布事件，不直接调用
# 3. 可扩展：LLM可以发布事件安排下次分析
# 4. 简洁：订单通知直接在workflow内处理
```

---

## 📦 重构内容

### 1. `src/events/event_system.py` - 完全重写

**移除的功能**：
- `publish_order_event()` - 订单事件发布
- `publish_portfolio_event()` - 组合事件发布
- `publish_market_event()` - 市场事件发布（太泛化）

**新增的便捷方法**：
```python
# 专注workflow触发
async def trigger_daily_rebalance(context: Dict = None)
async def trigger_realtime_rebalance(reason: str, details: Dict)
async def trigger_manual_analysis(context: Dict = None)
async def trigger_portfolio_check()
async def trigger_risk_check()
async def trigger_eod_analysis()
```

**设计哲学**：
```python
"""
事件驱动系统 - 专注于workflow触发和调度

设计原则：
1. 只处理workflow触发相关的事件
2. 订单通知等由各组件直接处理，不走事件系统
3. 支持LLM agent自主发布事件调度下次分析
4. 保持简洁，避免过度设计
"""
```

---

### 2. `src/trading_system.py` - 简化event handlers

**移除的handlers**：
```python
# ❌ 删除
async def _handle_order_created(event)
async def _handle_order_filled(event)
async def _handle_order_canceled(event)
async def _handle_order_rejected(event)
async def _handle_portfolio_updated(event)
async def _handle_error(event)
```

**新增的handlers**：
```python
# ✅ 新增：专注workflow触发
async def _handle_daily_rebalance_trigger(event)
async def _handle_realtime_rebalance_trigger(event)
async def _handle_manual_analysis_trigger(event)
async def _handle_portfolio_check_trigger(event)
async def _handle_risk_check_trigger(event)
async def _handle_eod_analysis_trigger(event)
# 系统状态
async def _handle_system_started(event)
async def _handle_system_stopped(event)
```

**handlers职责**：
- 接收事件
- 调用对应的workflow执行方法
- 简洁、专一

**示例**：
```python
async def _handle_daily_rebalance_trigger(self, event: TradingEvent):
    """处理每日重新平衡触发事件"""
    try:
        logger.info("收到每日重新平衡触发事件")
        await self.run_daily_rebalance()
    except Exception as e:
        logger.error(f"处理每日重新平衡触发失败: {e}")

async def _handle_realtime_rebalance_trigger(self, event: TradingEvent):
    """处理实时重新平衡触发事件（价格波动、新闻等）"""
    try:
        reason = event.data.get("reason", "unknown") if event.data else "unknown"
        details = event.data.get("details", {}) if event.data else {}
        logger.info(f"收到实时重新平衡触发: {reason}")
        
        # 构建context
        context = {
            "trigger": "realtime_event",
            "reason": reason,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        
        # 运行workflow
        if hasattr(self, 'trading_workflow'):
            workflow_type = self.trading_workflow.get_workflow_type()
            if workflow_type in ["balanced_portfolio", "llm_portfolio"]:
                await self.trading_workflow.run_workflow(context)
            else:
                await self.run_manual_analysis()
        
    except Exception as e:
        logger.error(f"处理实时重新平衡触发失败: {e}")
```

---

### 3. `src/scheduler/trading_scheduler.py` - 改为发布事件

**之前**：
```python
# ❌ 直接调用
async def _daily_rebalance(self):
    await self.trading_system.run_daily_rebalance()

async def _portfolio_check(self):
    portfolio = await self.trading_system.get_portfolio()
    if self._should_alert_portfolio_change(portfolio):
        await self.trading_system.send_portfolio_alert(portfolio)
```

**现在**：
```python
# ✅ 发布事件
async def _daily_rebalance(self):
    """每日组合重新平衡 - 通过事件系统触发"""
    if not await self.trading_system.is_market_open():
        logger.info("市场未开放，跳过重新平衡")
        return
    
    # 发布事件触发workflow
    await self.trading_system.event_system.trigger_daily_rebalance({
        "trigger": "daily_rebalance",
        "timestamp": datetime.now().isoformat()
    })

async def _portfolio_check(self):
    """定期组合监控 - 通过事件系统触发"""
    # 发布事件触发检查
    await self.trading_system.event_system.trigger_portfolio_check()

async def _risk_check(self):
    """风险检查 - 通过事件系统触发"""
    if not await self.trading_system.is_market_open():
        return
    
    await self.trading_system.event_system.trigger_risk_check()

async def _market_close_analysis(self):
    """市场收盘分析 - 通过事件系统触发"""
    await self.trading_system.event_system.trigger_eod_analysis()
```

**优势**：
- Scheduler不直接依赖trading_system的内部方法
- 更好的解耦
- 更容易测试

---

### 4. `src/services/realtime_monitor.py` - 改为发布事件

**之前**：
```python
# ❌ 直接调用workflow
async def _trigger_rebalance(self, reason: str, details: Dict):
    if hasattr(self.trading_system, 'trading_workflow'):
        workflow_type = self.trading_system.trading_workflow.get_workflow_type()
        if workflow_type in ["balanced_portfolio", "llm_portfolio"]:
            asyncio.create_task(
                self.trading_system.trading_workflow.run_workflow(context)
            )
        else:
            asyncio.create_task(
                self.trading_system.run_manual_analysis()
            )
```

**现在**：
```python
# ✅ 发布事件
async def _trigger_rebalance(self, reason: str, details: Dict):
    """触发重新平衡 - 通过事件系统"""
    # 检查冷却期
    if self.last_rebalance_trigger:
        elapsed = (datetime.now() - self.last_rebalance_trigger).total_seconds()
        if elapsed < self.REBALANCE_COOLDOWN:
            logger.info(f"重新平衡冷却中（剩余{self.REBALANCE_COOLDOWN - elapsed:.0f}秒）")
            return
    
    logger.warning(f"实时监控触发重新平衡: {reason} - {details}")
    
    # 记录触发
    self.last_rebalance_trigger = datetime.now()
    
    # 通过事件系统触发重新平衡
    if self.trading_system and hasattr(self.trading_system, 'event_system'):
        await self.trading_system.event_system.trigger_realtime_rebalance(
            reason=reason,
            details=details
        )
```

**优势**：
- RealtimeMonitor不需要知道workflow类型
- 统一的触发机制
- 更容易扩展（例如添加事件日志、监控等）

---

## 🔄 事件流转示意图

### 每日定时重新平衡

```
┌─────────────┐      trigger_daily_rebalance      ┌──────────────┐
│  Scheduler  │ ──────────────────────────────────>│ EventSystem  │
└─────────────┘                                     └──────────────┘
                                                           │
                                                           │ publish event
                                                           v
                                                    ┌──────────────┐
                                                    │ Event Queue  │
                                                    └──────────────┘
                                                           │
                                                           │ process
                                                           v
                                                    ┌──────────────┐
                                                    │   Handler    │
                                                    └──────────────┘
                                                           │
                                                           │ _handle_daily_rebalance_trigger
                                                           v
                                                    ┌──────────────┐
                                                    │TradingSystem │
                                                    │ .run_daily_  │
                                                    │  rebalance() │
                                                    └──────────────┘
                                                           │
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │   Workflow   │
                                                    │ (LLM Agent)  │
                                                    └──────────────┘
```

### 实时市场事件触发

```
┌──────────────┐    trigger_realtime_rebalance    ┌──────────────┐
│   Realtime   │ ──────────────────────────────────>│ EventSystem  │
│   Monitor    │  (reason: price_change/news)      └──────────────┘
└──────────────┘                                           │
    ^                                                      │
    │                                                      v
    │ WebSocket                                    ┌──────────────┐
    │ (Tiingo)                                     │   Handler    │
                                                   └──────────────┘
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │   Workflow   │
                                                    │  (context =  │
                                                    │   reason +   │
                                                    │   details)   │
                                                    └──────────────┘
```

### 手动触发

```
┌──────────────┐    trigger_manual_analysis       ┌──────────────┐
│   Telegram   │ ──────────────────────────────────>│ EventSystem  │
│   Command    │    (/analyze)                     └──────────────┘
└──────────────┘                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │   Handler    │
                                                    └──────────────┘
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │TradingSystem │
                                                    │.run_manual_  │
                                                    │ analysis()   │
                                                    └──────────────┘
                                                           │
                                                           v
                                                    ┌──────────────┐
                                                    │   Workflow   │
                                                    └──────────────┘
```

---

## 🚀 未来扩展：LLM自主调度

**概念**：LLM agent可以基于分析结果发布事件，安排下次分析时间

```python
# 在LLM Portfolio Agent中
async def run_workflow(self, context: Dict):
    # ... LLM分析 ...
    
    # LLM决定下次分析时间
    if llm_decides_to_schedule_next_analysis:
        await self.trading_system.event_system.publish_event(
            TradingEvent(
                event_type="schedule_next_analysis",
                data={
                    "scheduled_time": "2025-10-04 14:30:00",
                    "reason": "Expected FOMC announcement",
                    "priority": "high"
                }
            )
        )
```

**Handler处理**：
```python
async def _handle_schedule_next_analysis(self, event: TradingEvent):
    """LLM自主安排下次分析"""
    scheduled_time = event.data.get("scheduled_time")
    reason = event.data.get("reason")
    
    # 添加到scheduler的自定义任务
    self.scheduler.add_custom_job(
        job_id=f"llm_scheduled_{datetime.now().timestamp()}",
        schedule_time=scheduled_time,
        job_func=self.run_manual_analysis
    )
    
    logger.info(f"LLM安排下次分析: {scheduled_time} - {reason}")
```

---

## ✅ 重构成果对比

| 方面 | 重构前 | 重构后 |
|-----|--------|--------|
| **事件类型** | 9种（混杂订单和workflow） | 7种（专注workflow触发） ⭐ |
| **Event handlers** | 9个handlers | 8个handlers（职责清晰） ⭐ |
| **Scheduler** | 直接调用trading_system方法 | 发布事件，解耦 ⭐ |
| **RealtimeMonitor** | 直接调用workflow | 发布事件，解耦 ⭐ |
| **订单通知** | 走事件系统（过度设计） | Workflow内部处理 ⭐ |
| **可扩展性** | 难以添加新触发源 | 任何组件都可发布事件 ⭐ |
| **可测试性** | 耦合度高 | 解耦，易于测试 ⭐ |
| **代码简洁度** | 混杂 | 职责单一，清晰 ⭐ |

---

## 📝 使用指南

### Scheduler发布事件

```python
# 定时任务中
await self.trading_system.event_system.trigger_daily_rebalance()
await self.trading_system.event_system.trigger_portfolio_check()
await self.trading_system.event_system.trigger_risk_check()
await self.trading_system.event_system.trigger_eod_analysis()
```

### RealtimeMonitor发布事件

```python
# 检测到市场事件时
await self.trading_system.event_system.trigger_realtime_rebalance(
    reason="price_change",  # or "high_volatility", "breaking_news"
    details={
        "symbol": "AAPL",
        "change_percentage": 5.2,
        "current_price": 182.50
    }
)
```

### Telegram命令发布事件

```python
# 手动触发分析
await self.trading_system.event_system.trigger_manual_analysis({
    "trigger": "telegram_command",
    "user_id": message.from_user.id
})
```

### 自定义事件（未来）

```python
# LLM Agent自主调度
event = TradingEvent(
    event_type="schedule_next_analysis",
    data={
        "scheduled_time": "14:30",
        "reason": "Expected earnings report"
    }
)
await event_system.publish_event(event)
```

---

## 🔍 代码清理清单

### 已移除
- ✅ `publish_order_event()` - event_system.py
- ✅ `publish_portfolio_event()` - event_system.py
- ✅ `publish_market_event()` - event_system.py
- ✅ `_handle_order_created()` - trading_system.py
- ✅ `_handle_order_filled()` - trading_system.py
- ✅ `_handle_order_canceled()` - trading_system.py
- ✅ `_handle_order_rejected()` - trading_system.py
- ✅ `_handle_portfolio_updated()` - trading_system.py
- ✅ `_should_alert_portfolio_change()` - scheduler.py（移到trading_system）

### 新增
- ✅ `trigger_daily_rebalance()` - event_system.py
- ✅ `trigger_realtime_rebalance()` - event_system.py
- ✅ `trigger_manual_analysis()` - event_system.py
- ✅ `trigger_portfolio_check()` - event_system.py
- ✅ `trigger_risk_check()` - event_system.py
- ✅ `trigger_eod_analysis()` - event_system.py
- ✅ 8个新的workflow触发handlers - trading_system.py
- ✅ `_should_alert_portfolio_change()` - trading_system.py

---

## 🎯 设计原则总结

1. **单一职责**：事件系统只负责workflow触发，不管订单通知
2. **解耦**：Scheduler/Monitor发布事件，不直接调用workflow
3. **可扩展**：新的触发源（如LLM自主调度）很容易添加
4. **简洁**：去掉不必要的抽象层，代码更清晰
5. **事件驱动**：整个系统通过事件协调，而不是直接方法调用

---

**现在事件系统职责明确，代码结构更清晰！** 📢✨
