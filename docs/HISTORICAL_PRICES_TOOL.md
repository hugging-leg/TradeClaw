# 📈 LLM Agent Historical Prices Tool

**Date**: 2025-10-03  
**Feature**: LLM Agent Technical Analysis Capability  
**Status**: ✅ IMPLEMENTED

---

## 🎯 Overview

Added `get_historical_prices` tool to LLM Portfolio Agent, enabling the LLM to autonomously fetch and analyze historical price data with full control over timeframe and data range.

### User Request
> "agent应该也可以调用broker_api的get_market_data，自行决定time frame和历史获取price历史信息"

---

## ✅ Implementation

### New Tool: `get_historical_prices`

**Function Signature**:
```python
async def get_historical_prices(
    symbol: str,
    timeframe: str = "1Day",
    limit: int = 100
) -> str:
```

**Parameters**:
- `symbol`: Stock symbol (e.g., AAPL, MSFT, SPY, QQQ)
- `timeframe`: Time interval for bars
  - `"1Day"` - Daily bars (default)
  - `"1Hour"` - Hourly bars
  - `"30Min"` - 30-minute bars
  - `"15Min"` - 15-minute bars
  - `"5Min"` - 5-minute bars
  - `"1Min"` - 1-minute bars
  - `"1Week"` - Weekly bars
  - `"1Month"` - Monthly bars
- `limit`: Number of bars to return (1-1000)

**API Used**: `broker_api.get_market_data()` (Alpaca)

---

## 📊 Supported Timeframes

| Timeframe | Description | Best For | Recommended Limit |
|-----------|-------------|----------|-------------------|
| `1Day` | Daily bars | Trend analysis, support/resistance | 30-200 |
| `1Hour` | Hourly bars | Short-term trends, intraday | 50-300 |
| `30Min` | 30-minute bars | Intraday analysis | 100-500 |
| `15Min` | 15-minute bars | Entry point identification | 100-500 |
| `5Min` | 5-minute bars | Short-term trading | 200-1000 |
| `1Min` | 1-minute bars | Scalping, precise entry | 200-1000 |
| `1Week` | Weekly bars | Long-term trends | 52-200 |
| `1Month` | Monthly bars | Macro analysis | 12-100 |

---

## 💡 Usage Examples

### Trend Analysis
```python
# Get 100 daily bars for AAPL
get_historical_prices("AAPL", "1Day", 100)

# Analyze long-term trend with weekly bars
get_historical_prices("SPY", "1Week", 52)
```

### Intraday Analysis
```python
# Get 200 15-minute bars for entry point
get_historical_prices("SPY", "15Min", 200)

# Short-term trading with 5-minute bars
get_historical_prices("TSLA", "5Min", 300)
```

### Short-term Trading
```python
# Hourly bars for swing trading
get_historical_prices("QQQ", "1Hour", 100)

# 1-minute bars for scalping
get_historical_prices("NVDA", "1Min", 500)
```

---

## 📦 Return Data Structure

```json
{
  "success": true,
  "symbol": "AAPL",
  "timeframe": "1Day",
  "total_bars": 100,
  "returned_bars": 50,
  "time_range": {
    "start": "2024-07-01 09:30:00",
    "end": "2024-10-03 16:00:00"
  },
  "summary": {
    "latest_close": 178.25,
    "oldest_close": 165.30,
    "price_change_pct": 7.84,
    "avg_close": 172.45,
    "period_high": 180.50,
    "period_low": 162.80,
    "avg_volume": 58650000
  },
  "bars": [
    {
      "timestamp": "2024-10-03 16:00:00",
      "open": 177.50,
      "high": 178.80,
      "low": 176.90,
      "close": 178.25,
      "volume": 65432100
    }
  ]
}
```

### Data Fields

**Summary Statistics**:
- `latest_close`: Most recent closing price
- `oldest_close`: Oldest closing price in the range
- `price_change_pct`: Percentage change from oldest to latest
- `avg_close`: Average closing price
- `period_high`: Highest price in the period
- `period_low`: Lowest price in the period
- `avg_volume`: Average trading volume

**Bar Data** (OHLCV):
- `timestamp`: Bar time
- `open`: Opening price
- `high`: Highest price
- `low`: Lowest price
- `close`: Closing price
- `volume`: Trading volume

**Note**: Returns maximum 50 detailed bars to avoid overwhelming the LLM context, but `summary` includes statistics from all bars.

---

## 🤖 LLM Capabilities

With this tool, the LLM can:

1. **Choose Appropriate Timeframe**: Select timeframe based on analysis goal
2. **Control Data Range**: Request 1-1000 bars as needed
3. **Analyze Price Trends**: Identify trends, support/resistance levels
4. **Calculate Indicators**: Compute moving averages, volatility from data
5. **Identify Patterns**: Spot chart patterns and price formations
6. **Make Informed Decisions**: Combine technical analysis with news and fundamentals
7. **Compare Multiple Stocks**: Analyze and compare different securities

---

## 📈 Technical Analysis Workflow

```
1. LLM receives trigger (news, schedule, manual)
   ↓
2. LLM calls get_historical_prices() for relevant stocks
   ↓
3. LLM analyzes:
   - Price trends (uptrend/downtrend/sideways)
   - Support and resistance levels
   - Volatility and volume patterns
   - Recent price action
   ↓
4. LLM combines with:
   - Current portfolio status
   - Market news and sentiment
   - Market overview (indices)
   ↓
5. LLM makes rebalance decision
   ↓
6. LLM executes via rebalance_portfolio()
```

---

## 🔧 Technical Details

### API Choice: broker_api vs market_data_api

**Why broker_api?**
- ✅ Single unified API (Alpaca)
- ✅ Simpler parameters (timeframe + limit)
- ✅ No date calculation needed
- ✅ Consistent with trading operations
- ✅ Real-time data access

**broker_api.get_market_data()**:
```python
async def get_market_data(
    symbol: str, 
    timeframe: str = "1Day", 
    limit: int = 100
) -> List[Dict[str, Any]]:
```

**market_data_api (not used)**:
```python
async def get_eod_prices(
    symbol: str,
    start_date: datetime,
    end_date: datetime
) -> List[Dict[str, Any]]:
```

---

## 💭 LLM System Prompt Updates

Added technical analysis guidance:

```markdown
## 技术分析建议
- 使用get_historical_prices获取历史价格数据进行技术分析
- 时间框架选择（timeframe参数）：
  * "1Day": 日线 - 适合看中长期趋势、支撑阻力位、均线系统（建议30-200条）
  * "1Hour": 小时线 - 适合短期趋势、日内波动分析（建议50-300条）
  * "15Min": 15分钟 - 适合寻找入场点、观察短期波动（建议100-500条）
  * "5Min": 5分钟 - 适合精确入场、日内交易（建议200-1000条）
  * "1Week": 周线 - 适合长期趋势分析（建议52-200条）
- K线数量建议（limit参数）：
  * 短期分析: 50-100条K线
  * 中期分析: 100-300条K线
  * 长期分析: 200-500条K线
  * 最大支持: 1000条K线
- 可结合价格走势、成交量、均价、高低点等进行综合判断
- 返回数据包含summary（统计信息）和bars（最近50条K线详情）
```

---

## ✨ Benefits

### For LLM
- **Full Autonomy**: LLM decides timeframe and data range
- **Flexible Analysis**: Can perform technical analysis at any timescale
- **Rich Context**: Statistics + detailed bar data
- **Informed Decisions**: Technical + fundamental + news analysis

### For System
- **Consistent API**: All data from broker (Alpaca)
- **Efficient**: Limit parameter prevents over-fetching
- **Simple**: No date calculations, straightforward parameters
- **Real-time**: Access to latest market data

### For Trading
- **Better Entries**: Precise timing with 15min/5min data
- **Trend Following**: Identify trends with daily/weekly data
- **Risk Management**: Understand volatility and support levels
- **Informed Decisions**: Data-driven trading strategies

---

## 📂 Files Modified

| File | Changes |
|------|---------|
| `src/agents/llm_portfolio_agent.py` | • Added `get_historical_prices` tool<br>• Updated system prompt with technical analysis guidance<br>• Updated tool list documentation |

---

## 🧪 Testing Scenarios

### Test 1: Daily Trend Analysis
```python
# LLM request
get_historical_prices("AAPL", "1Day", 90)

# Expected: 90 daily bars, trend statistics
# LLM can identify: uptrend/downtrend, support/resistance
```

### Test 2: Intraday Entry Point
```python
# LLM request
get_historical_prices("SPY", "15Min", 200)

# Expected: 200 15-minute bars
# LLM can identify: recent price action, entry points
```

### Test 3: Long-term Trend
```python
# LLM request
get_historical_prices("QQQ", "1Week", 52)

# Expected: 52 weekly bars (1 year)
# LLM can identify: long-term trend, major support/resistance
```

---

## 🎓 Example LLM Usage

### Scenario: News-driven Analysis

```
1. LLM sees breaking news: "Apple announces new product"

2. LLM thinks: "I need to check AAPL's recent trend"

3. LLM calls:
   get_historical_prices("AAPL", "1Day", 30)

4. LLM analyzes:
   - Price has been in uptrend for 20 days
   - Recent consolidation near $175
   - Strong volume on up days
   
5. LLM decides: "Positive news + uptrend + consolidation = good entry"

6. LLM calls:
   rebalance_portfolio({"AAPL": 15, ...}, "Positive news with technical confirmation")
```

---

## 📊 Comparison: Before vs After

### Before (No Historical Data Tool)
```
LLM Decision Process:
├─ News: ✅ Available
├─ Current prices: ✅ Available
├─ Portfolio status: ✅ Available
└─ Historical trends: ❌ Not available

Result: Decisions based on current data only
```

### After (With Historical Data Tool)
```
LLM Decision Process:
├─ News: ✅ Available
├─ Current prices: ✅ Available
├─ Portfolio status: ✅ Available
└─ Historical trends: ✅ Available (1min to monthly)

Result: Informed decisions with technical analysis
```

---

## 🚀 Future Enhancements

Potential additions:
1. **Technical Indicators**: Built-in RSI, MACD, Bollinger Bands
2. **Multi-symbol Analysis**: Compare multiple stocks
3. **Pattern Recognition**: Automatic pattern detection
4. **Volatility Metrics**: ATR, standard deviation
5. **Volume Analysis**: Volume profile, OBV
6. **Market Breadth**: Advance/decline indicators

---

## ✅ Summary

**What**: LLM can now fetch and analyze historical price data

**Why**: Enable technical analysis and informed trading decisions

**How**: New `get_historical_prices` tool using `broker_api.get_market_data()`

**Impact**: LLM can now:
- Perform comprehensive technical analysis
- Make data-driven trading decisions
- Time entries and exits more precisely
- Understand market trends and patterns

**Result**: More sophisticated, informed trading strategies! 🎯


