# LLM Portfolio Agent - 完全由LLM驱动的投资组合管理

## 📖 设计理念

### 传统方式 vs LLM驱动方式

#### ❌ 传统方式（Rule-Based）

```python
# 硬编码规则
TARGET_POSITIONS = 5
TARGET_PERCENTAGE = 18.0
REBALANCE_THRESHOLD = 3.0

# 固定逻辑
if position_percentage > TARGET_PERCENTAGE + REBALANCE_THRESHOLD:
    sell_to_target()
elif position_percentage < TARGET_PERCENTAGE - REBALANCE_THRESHOLD:
    buy_to_target()
```

**问题**：
- ❌ 规则僵化，无法适应市场变化
- ❌ 需要不断调整参数
- ❌ 无法处理复杂情况
- ❌ 缺乏灵活性

#### ✅ LLM驱动方式（AI-Driven）

```python
# 无硬编码规则！
llm_agent = LLMPortfolioAgent()

# LLM自主决策
result = await llm_agent.run_workflow({
    "trigger": "daily_analysis"
})

# LLM会：
# 1. 调用tools获取市场数据、新闻、组合状态
# 2. 综合分析所有信息
# 3. 自主决定是否需要调整
# 4. 决定目标配置（可能5只、6只、7只...）
# 5. 调用rebalance_portfolio执行
# 6. 提供决策理由
```

**优势**：
- ✅ 完全灵活，LLM基于实际情况决策
- ✅ 自适应，无需调参
- ✅ 处理复杂情况（多因素综合分析）
- ✅ 可解释，LLM说明决策理由

---

## 🛠️ Tools提供给LLM

LLM可以调用以下6个tools：

### 1. `get_portfolio_status()`
获取当前组合状态

**返回信息**：
- 总资产、现金、市值
- 每个持仓的详细信息
- 盈亏情况

**LLM使用场景**：
- 了解当前组合配置
- 检查持仓盈亏
- 评估是否需要调整

### 2. `get_market_data()`
获取市场概况

**返回信息**：
- 主要指数（SPY, QQQ, IWM, DIA）
- 最新价格、涨跌幅
- 市场整体趋势

**LLM使用场景**：
- 判断大盘走势
- 评估市场风险
- 决定进攻/防守策略

### 3. `get_latest_news(limit=20)`
获取最新市场新闻

**返回信息**：
- 新闻标题、来源
- 发布时间
- 相关股票

**LLM使用场景**：
- 识别突发事件
- 评估新闻对持仓的影响
- 发现投资机会

### 4. `get_position_analysis()`
分析持仓分布

**返回信息**：
- 各持仓占比
- 集中度指标
- 风险分析

**LLM使用场景**：
- 评估组合平衡性
- 识别过度集中风险
- 决定是否需要分散

### 5. `get_stock_info(symbol)`
获取个股详细信息

**参数**：
- `symbol`: 股票代码（如"AAPL"）

**返回信息**：
- 最新价格、成交量
- 公司信息
- 历史数据

**LLM使用场景**：
- 评估个股质量
- 决定是否买入/卖出
- 选择替代股票

### 6. `rebalance_portfolio(target_allocations, reason)`
执行组合重新平衡

**参数**：
- `target_allocations`: 目标配置，如 `{"AAPL": 25.0, "MSFT": 25.0, "GOOGL": 25.0, "AMZN": 25.0}`
- `reason`: 重新平衡原因

**执行操作**：
- 计算需要的交易
- 生成买卖订单
- 执行交易
- 发送通知

**LLM使用场景**：
- 基于分析决定调整组合
- 执行rebalance操作
- 记录决策理由

---

## 🔄 工作流程

### 1. 触发分析

系统会在以下情况触发LLM分析：

```python
# 定时触发（如每天9:30）
context = {"trigger": "daily_rebalance"}

# 突发新闻触发
context = {
    "trigger": "breaking_news",
    "news_event": {
        "title": "Apple announces new product",
        "symbol": "AAPL"
    }
}

# 价格变动触发
context = {
    "trigger": "price_change",
    "market_event": {
        "symbol": "TSLA",
        "change_percentage": 7.5
    }
}

# 手动触发
context = {"trigger": "manual"}
```

### 2. LLM分析过程

```
用户/系统触发
    ↓
LLM收到任务提示
    ↓
LLM决定使用哪些tools
    ↓
调用get_portfolio_status ← LLM想了解当前状态
    ↓
调用get_market_data ← LLM想了解市场情况
    ↓
调用get_latest_news ← LLM想查看新闻
    ↓
调用get_position_analysis ← LLM想分析持仓
    ↓
LLM综合分析所有信息
    ↓
LLM决策：需要调整？
    ├─ No → 报告"组合良好，无需调整"
    └─ Yes → 继续
            ↓
        LLM确定目标配置
            ↓
        调用rebalance_portfolio
            ↓
        执行完成
```

### 3. LLM决策示例

#### 示例1：市场平稳，组合良好

```
触发：daily_rebalance

LLM分析过程：
1. get_portfolio_status → 发现持有5只股票，分布均匀
2. get_market_data → 市场平稳
3. get_latest_news → 无重大新闻
4. get_position_analysis → 集中度合理

LLM决策：
"经过分析，当前组合配置良好：
- 5只优质科技股，分布均衡
- 市场环境平稳
- 无重大新闻影响
- 风险分散充分

建议：保持现有配置，继续监控。"

结果：无操作
```

#### 示例2：检测到风险，主动调整

```
触发：breaking_news
新闻：某科技公司遭到监管调查

LLM分析过程：
1. get_latest_news → 发现重大负面新闻
2. get_portfolio_status → 发现该股票占仓30%
3. get_position_analysis → 确认风险集中
4. get_stock_info(替代股票) → 寻找替代选择

LLM决策：
"检测到重大风险事件：
- XYZ公司面临监管调查
- 当前持仓占比30%，风险过高
- 建议降低至15%或完全退出
- 可考虑配置到ABC公司作为替代

执行rebalance..."

结果：调用rebalance_portfolio({
    "XYZ": 0.0,    # 清仓
    "ABC": 20.0,   # 新增
    "其他": 各20.0
}, reason="监管风险，降低暴露")
```

#### 示例3：发现机会，优化配置

```
触发：daily_rebalance

LLM分析过程：
1. get_market_data → 发现某板块大幅下跌
2. get_latest_news → 确认只是短期情绪，基本面未变
3. get_portfolio_status → 现有配置保守
4. get_stock_info(机会股票) → 评估质量

LLM决策：
"发现投资机会：
- 生物科技板块短期超跌
- ABC公司基本面优秀，估值合理
- 当前组合缺少医疗健康板块
- 建议适度增配

建议配置：
- 减少金融股至15%
- 增加ABC生物科技20%
- 其他维持..."

结果：执行rebalance
```

---

## 🎯 LLM System Prompt

LLM会收到以下系统提示：

```
你是一位专业的AI投资组合经理，负责管理美股投资组合。

## 你的职责
1. 持续分析市场状况、新闻事件和组合配置
2. 基于分析自主决定是否需要调整组合
3. 决定目标仓位配置（不需要遵循固定规则）
4. 执行组合重新平衡

## 可用工具
（6个tools说明...）

## 决策原则
1. **自主分析**: 你可以自由决定何时调整组合，无需遵循固定规则
2. **风险分散**: 考虑适当分散风险，但具体配置由你决定
3. **响应市场**: 关注重大新闻、市场变化，及时调整策略
4. **理性决策**: 基于数据和分析，避免情绪化决策
5. **成本意识**: 避免过度频繁交易

## 重要提示
- 你完全自主决策，没有固定的仓位要求（如18%）
- 你可以持有2-10只股票，具体数量由你决定
- 你可以根据市场情况灵活调整配置
- 充分利用工具获取信息，做出明智决策
```

---

## 💡 使用建议

### 1. 让LLM充分发挥

```bash
# ✅ 推荐：让LLM自主决策
WORKFLOW_TYPE=llm_portfolio

# ❌ 不推荐：添加额外规则约束
# 让LLM自己决定，不要限制它
```

### 2. 监控LLM决策

LLM会通过Telegram发送：
- 分析过程
- 决策理由
- 执行结果

定期查看确保决策合理。

### 3. 成本考虑

LLM Portfolio Agent会调用多次LLM API：
- 每次分析：2-5次API调用（取决于LLM需要多少信息）
- 每天触发：1-3次
- 实时触发：根据市场事件

**成本估算**（以GPT-4为例）：
- 每次分析：$0.01-0.05
- 每天：$0.02-0.15
- 每月：$0.60-4.50

建议使用**DeepSeek**降低成本（便宜10倍以上）。

### 4. 与实时监控结合

```python
# 系统会自动：
1. WebSocket监控实时数据
2. 检测重大事件（价格变动、新闻）
3. 触发LLM分析
4. LLM自主决定是否rebalance
```

---

## 🔧 技术实现

### ReAct Agent架构

```python
from langgraph.prebuilt import create_react_agent

# 创建ReAct agent
agent = create_react_agent(
    llm,                    # LLM模型
    tools,                  # 6个tools
    state_modifier=prompt   # System prompt
)

# 运行
result = await agent.ainvoke({
    "messages": [HumanMessage(content="分析组合")]
})
```

### Tool实现

```python
from langchain.tools import tool

@tool
async def get_portfolio_status() -> str:
    """获取当前投资组合状态"""
    portfolio = await broker_api.get_portfolio()
    return json.dumps(portfolio_data)

# LLM会看到工具描述，自主决定何时调用
```

---

## 📊 对比总结

| 特性 | Rule-Based | LLM-Driven |
|------|-----------|-----------|
| **决策方式** | 固定规则 | LLM自主 |
| **灵活性** | ❌ 僵化 | ✅ 高度灵活 |
| **适应性** | ❌ 需调参 | ✅ 自适应 |
| **处理复杂情况** | ❌ 有限 | ✅ 优秀 |
| **可解释性** | ⚠️ 规则透明 | ✅ LLM说明理由 |
| **成本** | ✅ 低 | ⚠️ 较高（但可用DeepSeek） |
| **可靠性** | ✅ 可预测 | ⚠️ 依赖LLM质量 |

**推荐**：对于希望最大化AI能力的用户，`llm_portfolio`是最佳选择！

---

## 🚀 Quick Start

```bash
# 1. 配置.env
WORKFLOW_TYPE=llm_portfolio
LLM_PROVIDER=deepseek  # 或 openai
DEEPSEEK_API_KEY=your_key
TIINGO_API_KEY=your_key
ALPACA_API_KEY=your_key

# 2. 启动系统
python main.py

# 3. 观察LLM的决策
# 系统会通过Telegram发送LLM的分析过程和决策

# 4. 手动触发分析（可选）
# Telegram: /analyze
```

---

## ❓ FAQ

### Q: LLM会不会做出错误决策？
A: 
- LLM基于大量数据训练，决策通常合理
- 建议先用paper trading测试
- 可设置资金上限
- 定期审查LLM的决策

### Q: 成本会不会很高？
A:
- 使用DeepSeek：~$0.60-4.50/月
- 使用OpenAI GPT-4：~$6-45/月
- 可通过降低触发频率控制成本

### Q: 能否限制LLM的决策？
A:
- 可通过修改system prompt添加约束
- 例如："持仓数量应在3-7只之间"
- 但不建议过多限制，会降低LLM灵活性

### Q: 与balanced_portfolio有什么区别？
A:
- `balanced_portfolio`: 18%固定规则，LLM只选股
- `llm_portfolio`: LLM完全自主，决定一切
- 后者更智能、更灵活

---

完全解放LLM的决策能力，让AI真正成为你的投资组合经理！🌟
