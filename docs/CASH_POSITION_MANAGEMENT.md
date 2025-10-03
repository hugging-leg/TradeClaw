# 💵 现金仓位管理

**日期**: 2025-09-30  
**问题**: LLM可能返回"CASH"作为股票代码，但CASH实际上是一个真实公司的代码

---

## 🎯 问题说明

### 之前的问题
```python
# LLM可能这样调用
rebalance_portfolio({
    "AAPL": 30,
    "MSFT": 30,
    "CASH": 40  # ❌ 问题：CASH是一个真实的公司股票代码！
}, reason="...")
```

**Meta Platforms Payment Inc (CASH)** 是一个真实存在的美股代码，这会导致：
- 系统尝试买入CASH股票
- 无法区分"保留现金"和"买入CASH股票"
- 混淆资金管理

---

## ✅ 解决方案

### 1. 明确规则：不要在配置中包含现金

```python
# ✅ 正确方式
rebalance_portfolio({
    "AAPL": 30,
    "MSFT": 30,
    "GOOGL": 20
    # 剩余20%自动为现金，不需要指定
}, reason="...")
```

### 2. 自动过滤现金关键词

系统会自动过滤以下关键词：
- `CASH`
- `USD`
- `DOLLAR`
- `现金`
- `美元`

```python
# LLM如果错误地包含了现金
target_allocations = {
    "AAPL": 30,
    "MSFT": 30,
    "CASH": 40  # 会被自动移除
}

# 系统自动处理后
filtered_allocations = {
    "AAPL": 30,
    "MSFT": 30
    # CASH被移除，40%自动成为现金
}
```

### 3. 百分比总和可以小于100%

```python
# 灵活配置现金比例

# 全仓配置（几乎0%现金）
{"AAPL": 33, "MSFT": 33, "GOOGL": 34}  # 0%现金

# 保留小额现金
{"AAPL": 30, "MSFT": 30, "GOOGL": 30}  # 10%现金

# 保留较多现金（市场不确定时）
{"AAPL": 25, "MSFT": 25}  # 50%现金

# 几乎全现金（等待机会）
{"SPY": 10}  # 90%现金
```

---

## 📊 功能改进

### 1. `get_portfolio_status` 增强

现在返回详细的持仓百分比和现金比例：

```json
{
  "total_equity": 100000.00,
  "cash": 20000.00,
  "cash_percentage": 20.0,  // ← 新增：现金占比
  "positions": [
    {
      "symbol": "AAPL",
      "market_value": 30000.00,
      "percentage": 30.0,      // ← 新增：持仓占比
      ...
    },
    {
      "symbol": "MSFT",
      "market_value": 30000.00,
      "percentage": 30.0,
      ...
    },
    {
      "symbol": "GOOGL",
      "market_value": 20000.00,
      "percentage": 20.0,
      ...
    }
  ]
}
```

### 2. `rebalance_portfolio` 工具说明更新

```python
@tool
async def rebalance_portfolio(
    target_allocations: Dict[str, float],
    reason: str
) -> str:
    """
    执行组合重新平衡
    
    Args:
        target_allocations: 目标配置
                           - 只需指定股票/ETF的百分比，不要包含现金
                           - 百分比总和可以小于100%，剩余部分自动为现金
                           - 例如: {"AAPL": 30, "MSFT": 30} 表示30%+30%+40%现金
    """
```

### 3. System Prompt 新增章节

```markdown
## 现金仓位管理
- **重要**: 调用rebalance_portfolio时，只指定股票/ETF的目标百分比，不要包含"CASH"或"现金"
- 百分比总和可以小于100%，剩余部分会自动保留为现金
- 例如：{"AAPL": 30, "MSFT": 30, "GOOGL": 20} 表示30%+30%+20%+20%现金
- 如果想全仓，就让百分比总和接近100%；如果想保留现金，就让总和小于100%
- 可以根据市场情况灵活调整现金比例，如市场不确定时可以增加现金占比
```

### 4. Telegram通知改进

```
🔄 LLM发起组合重新平衡

原因: 市场不确定性增加，增加现金占比

目标配置:
- AAPL: 25.0%
- MSFT: 25.0%
- 💵 现金: 50.0%  ← 新增：显示现金比例
```

---

## 🔍 实现细节

### 代码位置
**文件**: `src/agents/llm_portfolio_agent.py`

### 1. 现金关键词过滤

```python
# 过滤掉可能的现金关键词
cash_keywords = ['CASH', 'USD', 'DOLLAR', '现金', '美元']
filtered_allocations = {
    k: v for k, v in target_allocations.items() 
    if k.upper() not in cash_keywords
}

if len(filtered_allocations) != len(target_allocations):
    removed = set(target_allocations.keys()) - set(filtered_allocations.keys())
    logger.info(f"移除了现金关键词: {removed}")
    target_allocations = filtered_allocations
```

### 2. 验证逻辑更新

```python
# 验证配置：总和应该≤100%（之前要求接近100%）
total_pct = sum(target_allocations.values())
if total_pct > 100:
    return f"错误: 目标配置总和为{total_pct}%，不能超过100%"

# 计算现金比例
cash_pct = 100 - total_pct
```

### 3. 通知消息增强

```python
# 在配置中显示现金比例
allocation_lines = [f"- {sym}: {pct:.1f}%" for sym, pct in target_allocations.items()]
if cash_pct > 0:
    allocation_lines.append(f"- 💵 现金: {cash_pct:.1f}%")
```

---

## 📝 使用示例

### 场景1: 正常市场，适度投资

```python
# LLM决策
rebalance_portfolio({
    "AAPL": 25,
    "MSFT": 25,
    "GOOGL": 20,
    "AMZN": 20
}, reason="市场平稳，分散投资科技股")

# 结果：10%现金
```

### 场景2: 市场不确定，增加现金

```python
# LLM决策
rebalance_portfolio({
    "SPY": 30,    # 防御性配置
    "GLD": 20     # 避险资产
}, reason="市场波动加大，保留50%现金等待机会")

# 结果：50%现金
```

### 场景3: 发现机会，几乎全仓

```python
# LLM决策
rebalance_portfolio({
    "NVDA": 35,
    "MSFT": 33,
    "GOOGL": 32
}, reason="科技股大跌，全仓买入")

# 结果：0%现金（几乎）
```

### 场景4: 极度谨慎，大量现金

```python
# LLM决策
rebalance_portfolio({
    "GLD": 10    # 仅保留少量黄金
}, reason="市场崩盘风险高，保留90%现金")

# 结果：90%现金
```

---

## ✅ 测试验证

### 测试1: 过滤CASH关键词

```python
# 输入
target_allocations = {
    "AAPL": 30,
    "MSFT": 30,
    "CASH": 40
}

# 处理后
filtered = {
    "AAPL": 30,
    "MSFT": 30
}
# CASH被移除，日志记录：移除了现金关键词: {'CASH'}
```

### 测试2: 现金比例计算

```python
# 配置
{"AAPL": 30, "MSFT": 30, "GOOGL": 20}

# 计算
total = 30 + 30 + 20 = 80%
cash = 100 - 80 = 20%  ✅

# Telegram显示
- AAPL: 30.0%
- MSFT: 30.0%
- GOOGL: 20.0%
- 💵 现金: 20.0%
```

### 测试3: 持仓百分比显示

```python
# get_portfolio_status 返回
{
  "cash": 20000,
  "cash_percentage": 20.0,
  "positions": [
    {
      "symbol": "AAPL",
      "market_value": 30000,
      "percentage": 30.0  // 每个持仓都显示占比
    },
    ...
  ]
}
```

---

## 🎯 优势总结

| 方面 | 改进前 | 改进后 |
|-----|--------|--------|
| **现金处理** | 可能被当成股票代码 | 自动过滤，隐式处理 ⭐ |
| **配置灵活性** | 必须总和100% | 可以小于100% ⭐ |
| **现金可见性** | 不直观 | 明确显示占比 ⭐ |
| **错误防护** | 容易出错 | 自动过滤关键词 ⭐ |
| **LLM理解** | 容易混淆 | System Prompt明确说明 ⭐ |

---

## 🔐 安全机制

1. **关键词过滤**: 自动移除CASH、USD等关键词
2. **百分比验证**: 总和不能超过100%
3. **日志记录**: 记录被过滤的关键词
4. **明确提示**: System Prompt中详细说明

---

## 📚 相关文件

- `src/agents/llm_portfolio_agent.py` - 核心实现
- `TIMEZONE_IMPROVEMENT.md` - 时区自动转换
- `TIMEZONE_AND_MARKET_CLOSE_FIX_V2.md` - 休市保护

---

**现在LLM可以安全、灵活地管理现金仓位了！** 💵✨
