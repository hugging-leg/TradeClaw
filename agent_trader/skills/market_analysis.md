---
name: market_analysis
description: 市场数据与分析工具 — 获取行情、持仓、历史数据和技术分析
---

# Market Analysis — 市场数据与分析

## 数据获取工具

### `get_portfolio_status`
获取当前投资组合状态，包括：
- 总权益、现金、购买力
- 所有持仓（股票、数量、市值、盈亏）
- 日内盈亏

**使用时机**：每次分析开始时首先调用，了解当前持仓。

### `get_stock_prices`
获取一只或多只股票的当前/历史价格数据。
- 支持实时报价和历史 OHLCV 数据
- 可指定时间范围

### `get_market_status`
检查市场当前状态（开盘/收盘/盘前/盘后）。

### `check_market_status`
检查当前是否为交易时间。

## 分析工具

### `analyze_portfolio_risk`
分析投资组合风险指标：
- 集中度（单股占比）
- 行业分布
- Beta 暴露
- 相关性矩阵

### `calculate_technical_indicators`
计算技术指标：
- RSI（相对强弱指数）
- MACD（移动平均收敛散度）
- 布林带
- 移动平均线

## 分析模式

### 日常检查流程
1. `get_portfolio_status` — 了解当前持仓
2. `get_market_status` — 确认市场状态
3. 搜索新闻 — 了解市场动态
4. 技术分析 — 评估趋势
5. 综合判断 — 决定是否调整

### 深度分析（建议使用子Agent并行）
- 技术面分析子Agent
- 基本面分析子Agent
- 新闻情绪子Agent
- 宏观环境子Agent
