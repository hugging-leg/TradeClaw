# 📰 News API Architecture

## Overview

本文档说明了新闻接口的架构设计，该设计使用适配器模式将新闻功能从Tiingo API解耦，提供了一个独立且可扩展的新闻接口系统。

## 🏗️ Architecture

### Before (紧耦合)
```
TradingSystem → TiingoAPI (新闻 + 市场数据)
```

### After (适配器模式)
```
TradingSystem → NewsAPI (抽象接口) ← TiingoNewsAdapter → Tiingo API
                    ↑
            NewsFactory (工厂模式)
```

## 📁 文件结构

```
src/apis/
├── news_api.py              # 抽象新闻接口和工厂
├── tiingo_news_adapter.py   # Tiingo新闻适配器
└── tiingo_api.py           # Tiingo市场数据API（已移除新闻功能）
```

## 🔧 核心组件

### 1. NewsAPI (抽象接口)

定义了所有新闻提供者必须实现的标准接口：

```python
from abc import ABC, abstractmethod
from typing import List, Optional
from src.models.trading_models import NewsItem

class NewsAPI(ABC):
    @abstractmethod
    async def get_news(self, symbols=None, tags=None, sources=None, 
                      start_date=None, end_date=None, limit=100) -> List[NewsItem]:
        """获取新闻文章"""
        pass
    
    @abstractmethod
    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        """获取特定股票的新闻"""
        pass
    
    @abstractmethod
    async def get_sector_news(self, sector: str, limit: int = 50) -> List[NewsItem]:
        """获取特定行业的新闻"""
        pass
    
    @abstractmethod
    async def get_market_overview_news(self, limit: int = 50) -> List[NewsItem]:
        """获取市场综述新闻"""
        pass
    
    @abstractmethod
    async def search_news(self, query: str, limit: int = 50) -> List[NewsItem]:
        """搜索新闻"""
        pass
```

### 2. NewsProvider (枚举)

支持的新闻提供者类型：

```python
class NewsProvider(Enum):
    TIINGO = "tiingo"
    ALPHA_VANTAGE = "alpha_vantage"
    NEWS_API = "news_api"
    CUSTOM = "custom"
```

### 3. NewsFactory (工厂模式)

管理新闻提供者的创建和注册：

```python
class NewsFactory:
    @classmethod
    def create_news_api(cls, provider=None) -> NewsAPI:
        """根据配置创建新闻API实例"""
        pass
    
    @classmethod
    def register_provider(cls, provider: NewsProvider, provider_class: type):
        """注册新的新闻提供者"""
        pass
    
    @classmethod
    def get_available_providers(cls) -> List[str]:
        """获取可用的新闻提供者列表"""
        pass
```

### 4. TiingoNewsAdapter (适配器实现)

将Tiingo API适配到NewsAPI接口：

```python
class TiingoNewsAdapter(NewsAPI):
    def __init__(self):
        self.base_url = "https://api.tiingo.com"
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Token {settings.tiingo_api_key}'
        }
    
    async def get_news(self, **kwargs) -> List[NewsItem]:
        """实现新闻获取逻辑"""
        pass
    
    def get_provider_info(self) -> Dict[str, Any]:
        """返回提供者信息"""
        return {
            'name': 'Tiingo',
            'provider': 'tiingo',
            'configured': bool(settings.tiingo_api_key),
            'features': [...],
            'rate_limits': {...}
        }
```

## ⚙️ 配置

### 环境变量

```bash
# 新闻提供者配置
NEWS_PROVIDER=tiingo  # 选项: tiingo, alpha_vantage, news_api, custom

# Tiingo配置
TIINGO_API_KEY=your_tiingo_api_key_here
```

### config.py

```python
class Settings(BaseSettings):
    # 新闻提供者配置
    news_provider: str = "tiingo"  # 选项: "tiingo", "alpha_vantage", "news_api", "custom"
    tiingo_api_key: str = "test_key"
```

## 🔌 使用方法

### 1. 基本使用

```python
from src.apis.news_api import get_news_api

# 获取新闻API实例（使用默认配置）
news_api = get_news_api()

# 获取新闻
news_items = await news_api.get_market_overview_news(limit=20)
symbol_news = await news_api.get_symbol_news("AAPL", limit=10)
search_results = await news_api.search_news("earnings", limit=15)
```

### 2. 指定提供者

```python
from src.apis.news_api import get_news_api

# 使用特定提供者
tiingo_api = get_news_api("tiingo")
# alpha_vantage_api = get_news_api("alpha_vantage")  # 未来实现
```

### 3. 在Workflow中使用

```python
class WorkflowBase:
    def __init__(self, alpaca_api, tiingo_api, telegram_bot=None):
        self.alpaca_api = alpaca_api
        self.tiingo_api = tiingo_api  # 仅用于市场数据
        self.news_api = get_news_api()  # 使用新闻工厂
        self.telegram_bot = telegram_bot
    
    async def get_news(self, limit: int = 20) -> List[Dict[str, Any]]:
        """获取新闻数据"""
        news_items = await self.news_api.get_market_overview_news(limit=limit)
        return [
            {
                "title": item.title,
                "description": item.description or "",
                "source": item.source,
                "published_at": item.published_at.isoformat(),
                "symbols": item.symbols
            }
            for item in news_items
        ]
```

## 🔧 添加新的新闻提供者

### 1. 创建适配器类

```python
from src.apis.news_api import NewsAPI, NewsProvider, NewsFactory
from src.models.trading_models import NewsItem

class CustomNewsAdapter(NewsAPI):
    async def get_news(self, **kwargs) -> List[NewsItem]:
        # 实现您的新闻获取逻辑
        pass
    
    async def get_symbol_news(self, symbol: str, limit: int = 50) -> List[NewsItem]:
        # 实现符号新闻获取逻辑
        pass
    
    # ... 实现其他必需方法
    
    def get_provider_name(self) -> str:
        return "Custom Provider"
    
    def get_provider_info(self) -> Dict[str, Any]:
        return {
            'name': 'Custom Provider',
            'provider': NewsProvider.CUSTOM.value,
            'configured': True,
            'features': [...]
        }

# 注册新提供者
NewsFactory.register_provider(NewsProvider.CUSTOM, CustomNewsAdapter)
```

### 2. 更新配置

```python
# config.py
class Settings(BaseSettings):
    news_provider: str = "custom"  # 使用新提供者
```

### 3. 更新枚举（如需要）

```python
class NewsProvider(Enum):
    TIINGO = "tiingo"
    ALPHA_VANTAGE = "alpha_vantage"
    NEWS_API = "news_api"
    CUSTOM = "custom"
    YOUR_PROVIDER = "your_provider"  # 添加新的提供者
```

## 🧪 测试

### 1. 单元测试

```bash
# 测试新闻API核心功能
python -m pytest tests/test_news_api.py -v

# 测试工厂模式
python -m pytest tests/test_workflow_factory.py -v
```

### 2. 集成测试

```python
import pytest
from src.apis.news_api import get_news_api

@pytest.mark.asyncio
async def test_news_integration():
    news_api = get_news_api()
    news_items = await news_api.get_market_overview_news(limit=5)
    
    assert len(news_items) <= 5
    assert all(hasattr(item, 'title') for item in news_items)
    assert all(hasattr(item, 'source') for item in news_items)
```

## 📊 系统监控

### 1. 提供者信息

```python
from src.apis.news_api import get_news_api

news_api = get_news_api()
provider_info = news_api.get_provider_info()

print(f"Provider: {provider_info['name']}")
print(f"Configured: {provider_info['configured']}")
print(f"Features: {provider_info['features']}")
print(f"Rate Limits: {provider_info['rate_limits']}")
```

### 2. 日志监控

系统会记录以下信息：
- 新闻提供者的创建和注册
- API调用的成功/失败状态
- 获取的新闻数量
- 错误和异常情况

## 🚀 迁移指南

### 从旧系统迁移

**之前的代码：**
```python
# 直接使用TiingoAPI
news_items = await self.tiingo_api.get_news(limit=20)
symbol_news = await self.tiingo_api.get_symbol_news("AAPL")
```

**新的代码：**
```python
# 使用NewsAPI接口
news_items = await self.news_api.get_market_overview_news(limit=20)
symbol_news = await self.news_api.get_symbol_news("AAPL")
```

### 配置更新

添加到 `.env` 文件：
```bash
NEWS_PROVIDER=tiingo
```

## 🎯 优势

1. **解耦**: 新闻功能与特定API解耦
2. **可扩展**: 轻松添加新的新闻提供者
3. **一致性**: 统一的接口标准
4. **可测试**: 独立的测试和模拟
5. **可配置**: 运行时切换新闻提供者
6. **向后兼容**: 现有功能无需修改

## 🔮 未来扩展

- Alpha Vantage News API适配器
- NewsAPI.org适配器
- 自定义RSS源适配器
- 新闻情感分析集成
- 新闻缓存和去重
- 多提供者聚合功能 