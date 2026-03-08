---
name: scheduling
description: 自主调度（at/every/cron）— 安排一次性、周期性或 cron 触发的分析任务
---

# Scheduling — 自主调度

使用 `schedule_next_analysis` 工具安排未来的分析任务。支持三种模式。

## 使用时机

- 预期有重要事件（FOMC、财报发布、经济数据公布）→ 提前安排分析
- 市场波动剧烈 → 安排更频繁的检查
- 需要盘前/盘后定期监控 → 使用 cron 模式

**注意**：每日例行分析由系统自动调度，不需要手动安排。

## 三种模式

### 1. `at` — 一次性延迟

```
schedule_next_analysis(
    schedule_kind="at",
    reason="FOMC 会议结果公布后分析",
    hours_from_now=2.5,
)
```

### 2. `every` — 周期重复

```
schedule_next_analysis(
    schedule_kind="every",
    reason="高波动期间频繁检查",
    interval_minutes=30,
    require_market_open=True,
)
```

### 3. `cron` — Cron 表达式

```
schedule_next_analysis(
    schedule_kind="cron",
    reason="每个交易日盘前分析",
    cron_expression="30 9 * * mon-fri",
    require_trading_day=True,
)
```

## 重要规则

1. **先查后建**：安排前先调用 `get_scheduled_events` 查看已有调度，避免重复
2. **避免冗余**：如果已有类似时间或原因的调度，不要重复创建
3. **可取消**：使用 `cancel_scheduled_analysis` 取消不再需要的调度
4. **有上限**：系统限制最大待执行 LLM 任务数（`max_pending_llm_jobs`）
5. **最小间隔**：周期任务有最小间隔限制（`llm_min_interval_minutes`）

## 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `schedule_kind` | str | `"at"` / `"every"` / `"cron"` |
| `reason` | str | 调度原因（人类可读） |
| `hours_from_now` | float | `at` 模式：延迟小时数 |
| `interval_minutes` | float | `every` 模式：间隔分钟数 |
| `cron_expression` | str | `cron` 模式：标准 5 段 cron 表达式 |
| `require_trading_day` | bool | 仅在交易日触发（默认 True） |
| `require_market_open` | bool | 仅在开盘时间触发（默认 False） |
| `priority` | int | 优先级（0=普通，越大越优先） |
