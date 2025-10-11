# LLM Agent 新闻工具改进

## 📋 改进概述

增强了 `get_latest_news` 工具的功能，使其支持按股票代码或行业过滤新闻，并在 Telegram 中显示新闻标题预览。

## 🎯 改进内容

### 1. 新增过滤参数

**之前**:
```python
@tool
async def get_latest_news(limit: int = 20) -> str:
    """获取最新市场新闻"""
```

**现在**:
```python
@tool
async def get_latest_news(
    limit: int = 20,
    symbol: str = None,      # 新增：按股票代码过滤
    sector: str = None       # 新增：按行业过滤
) -> str:
    """获取最新市场新闻，支持按股票代码或行业过滤"""
```

### 2. 智能路由到不同的新闻 API

根据参数自动调用相应的 API 方法：

```python
if symbol:
    news = await self.news_api.get_symbol_news(symbol, limit=limit)
elif sector:
    news = await self.news_api.get_sector_news(sector, limit=limit)
else:
    news = await self.get_news(limit=limit)
```

### 3. 新闻标题预览

在 Telegram 中显示前 5 条新闻标题（截断过长标题）：

```
✅ 已获取20条新闻 (股票: AAPL):

• Apple announces new product line in Q4 earnings call
• Tech giant sees strong iPhone sales despite market concerns
• Apple's services revenue reaches all-time high
• Analysts raise price targets following quarterly results
• Supply chain improvements boost Apple production
... 还有 15 条
```

### 4. 兼容性处理

统一处理 NewsItem 对象和字典两种返回格式：

```python
if isinstance(item, dict):
    title = item["title"]
    # ...
else:
    # 处理 NewsItem 对象
    title = item.title
    # ...
```

## 📝 使用示例

### LLM 可以这样调用

1. **获取通用市场新闻**:
```python
get_latest_news(limit=20)
```

2. **获取特定股票新闻**:
```python
get_latest_news(limit=15, symbol="AAPL")
get_latest_news(limit=10, symbol="TSLA")
```

3. **获取特定行业新闻**:
```python
get_latest_news(limit=20, sector="Technology")
get_latest_news(limit=15, sector="Finance")
```

## 🎨 用户体验改进

### 之前
```
📰 正在获取最新20条新闻...
✅ 已获取20条新闻
```

### 现在

**通用新闻**:
```
📰 正在获取最新20条新闻...
✅ 已获取20条新闻:

• Federal Reserve announces interest rate decision
• Tech stocks rally on strong earnings reports
• Market volatility continues amid geopolitical tensions
• Energy sector shows signs of recovery
• Cryptocurrency market faces regulatory scrutiny
... 还有 15 条
```

**股票新闻**:
```
📰 正在获取最新15条新闻 (股票: AAPL)...
✅ 已获取15条新闻 (股票: AAPL):

• Apple announces new product line in Q4 earnings call
• Tech giant sees strong iPhone sales despite market concerns
• Apple's services revenue reaches all-time high
• Analysts raise price targets following quarterly results
• Supply chain improvements boost Apple production
... 还有 10 条
```

**行业新闻**:
```
📰 正在获取最新20条新闻 (行业: Technology)...
✅ 已获取20条新闻 (行业: Technology):

• AI revolution drives tech sector growth
• Major tech companies announce Q4 earnings
• Semiconductor shortage shows signs of easing
• Cloud computing revenues surge across industry
• Cybersecurity concerns prompt new regulations
... 还有 15 条
```

## 🔧 技术细节

### 标题截断逻辑
```python
# 超过 80 字符的标题会被截断
titles.append(f"• {title[:80]}..." if len(title) > 80 else f"• {title}")
```

### 显示限制
```python
# 最多显示前 5 条标题，避免消息过长
preview = "\n".join(titles[:5])
more_text = f"\n... 还有 {len(titles)-5} 条" if len(titles) > 5 else ""
```

### 过滤描述
```python
# 根据参数构建描述文本
filter_desc = ""
if symbol:
    filter_desc = f" (股票: {symbol})"
elif sector:
    filter_desc = f" (行业: {sector})"
```

## 📊 System Prompt 更新

更新了 LLM 的 system prompt，告知这个新功能：

**之前**:
```
- get_latest_news: 获取最新市场新闻
```

**现在**:
```
- get_latest_news: 获取最新市场新闻（可按股票代码或行业过滤，如 symbol="AAPL" 或 sector="Technology"）
```

## ✅ 优势

1. **更精准的信息获取**
   - LLM 可以获取特定股票的新闻
   - LLM 可以获取特定行业的新闻
   - 减少无关信息，提高分析效率

2. **更好的用户体验**
   - 直观的新闻标题预览
   - 清晰的过滤标记
   - 合理的信息展示（前5条+总数）

3. **更智能的决策**
   - LLM 可以在持有某只股票时主动查询其相关新闻
   - LLM 可以在考虑某个行业时先查看行业新闻
   - 支持更精细的投资分析流程

4. **灵活的调用方式**
   - 保持向后兼容（无参数=通用新闻）
   - 支持多种过滤维度
   - 参数可选，使用简单

## 🎯 实际应用场景

### 场景 1: 持仓股票监控
```
LLM: "我看到持有 AAPL 仓位，让我先看看最新的苹果新闻"
→ get_latest_news(symbol="AAPL", limit=10)
```

### 场景 2: 行业分析
```
LLM: "考虑增加科技股配置，先了解一下科技行业的最新动态"
→ get_latest_news(sector="Technology", limit=15)
```

### 场景 3: 整体市场扫描
```
LLM: "先获取整体市场的最新新闻，了解大盘情况"
→ get_latest_news(limit=20)
```

### 场景 4: 特定股票研究
```
LLM: "TSLA 今天有大幅波动，查一下相关新闻"
→ get_latest_news(symbol="TSLA", limit=5)
```

## 📈 改进统计

| 项目 | 数值 |
|------|------|
| 新增参数 | 2 个 (symbol, sector) |
| 新增代码行 | ~30 行 |
| 支持的过滤方式 | 3 种 (无过滤/股票/行业) |
| 标题预览数量 | 最多 5 条 |
| 标题截断长度 | 80 字符 |
| API 路由 | 3 个不同的 news API |

## 🎉 总结

通过这次改进：
- ✅ **功能增强** - 支持按股票/行业过滤
- ✅ **体验提升** - 显示新闻标题预览
- ✅ **智能路由** - 自动调用合适的 API
- ✅ **兼容处理** - 支持多种数据格式
- ✅ **零错误** - 通过所有 linter 检查

LLM 现在可以更精准地获取所需新闻，做出更明智的投资决策！🚀

