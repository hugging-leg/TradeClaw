---
name: trading
description: 交易执行与仓位管理 — 调仓、仓位调整和现金管理
---

# Trading — 交易执行与仓位管理

## 调仓工具

### `rebalance_portfolio`
根据目标配置重新平衡投资组合。

```
rebalance_portfolio(
    target_allocations={
        "AAPL": 20,   # 目标占比 20%
        "MSFT": 15,   # 目标占比 15%
        "NVDA": 10,   # 目标占比 10%
    },
    reason="基于技术面和基本面分析的季度调仓",
)
```

### `adjust_position`
调整单个持仓。

```
adjust_position(
    symbol="NVDA",
    action="increase",   # "increase" / "decrease" / "close"
    percentage=5,        # 调整幅度（占总权益百分比）
    reason="技术面突破，增加仓位",
)
```

## 现金仓位管理

- 百分比总和可以小于 100%，剩余部分自动保留为现金
- 根据市场情况灵活调整现金比例
- 市场不确定时可增加现金占比（如设置 target_allocations 总和为 70%，留 30% 现金）

## 交易规则

1. **充分分析后再交易**：必须有明确的分析依据才能执行交易
2. **记录原因**：每次交易必须提供清晰的 `reason`
3. **控制频率**：避免过度交易，除非有明确的市场信号
4. **注意滑点**：大额调整考虑分批执行
5. **Paper Trading**：系统可能处于模拟交易模式，确认后再操作

## 典型场景

### 减仓止损
```
adjust_position(symbol="XYZ", action="decrease", percentage=5,
    reason="跌破关键支撑位，减仓控制风险")
```

### 清仓退出
```
adjust_position(symbol="XYZ", action="close",
    reason="基本面恶化，完全退出")
```

### 整体调仓
```
rebalance_portfolio(
    target_allocations={"AAPL": 25, "MSFT": 20, "GOOG": 15},
    reason="季度再平衡，增加科技股配置"
)
```
