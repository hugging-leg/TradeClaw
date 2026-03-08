---
name: web_research
description: 网络搜索与新闻 — 搜索市场新闻、研报、经济数据和公司信息
---

# Web Research — 网络搜索与新闻

## 搜索工具

### `search_news`
搜索市场相关新闻。
- 支持关键词搜索
- 返回标题、摘要、来源、时间

```
search_news(query="Federal Reserve interest rate decision 2025")
search_news(query="NVDA earnings report Q4")
```

### `web_search`
通用网络搜索（通过 SearXNG）。
- 适合搜索更广泛的信息
- 支持多语言

### `browser_navigate` / `browser_click` / `browser_extract`
浏览器工具，可以：
- 导航到特定网页
- 点击页面元素
- 提取页面内容

**使用时机**：当搜索结果不够详细，需要阅读原文时。

## 搜索策略

### 宏观经济
```
search_news(query="Fed monetary policy decision")
search_news(query="US employment data nonfarm payrolls")
search_news(query="CPI inflation data")
```

### 个股研究
```
search_news(query="AAPL Apple earnings revenue guidance")
search_news(query="NVDA AI chip demand supply")
```

### 行业动态
```
search_news(query="semiconductor industry outlook 2025")
search_news(query="AI technology stocks market trend")
```

## 最佳实践

1. **用英文搜索**：金融新闻以英文为主，英文搜索结果更全面
2. **具体关键词**：避免过于宽泛的搜索词
3. **多角度搜索**：同一主题用不同关键词搜索，获取更全面的信息
4. **验证时效**：注意新闻的发布时间，确保信息是最新的
5. **并行搜索**：多个不同主题的搜索可以用子 Agent 并行执行
