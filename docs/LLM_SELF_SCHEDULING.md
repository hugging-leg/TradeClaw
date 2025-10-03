# 🤖 LLM Self-Scheduling - Autonomous Agent Timing

**Date**: 2025-10-03  
**Feature**: LLM can autonomously schedule its next analysis

---

## 🎯 Concept

The LLM agent can now **autonomously decide** when to run its next analysis, making it truly self-managing and adaptive to market conditions.

### Why This Matters

**Before**: Rigid schedule
```python
# Fixed schedule - always runs at 9:30 AM daily
# No flexibility based on market conditions
# Cannot anticipate important events
```

**After**: LLM decides
```python
# LLM thinks: "FOMC meeting at 2 PM, I should analyze at 2:05 PM"
# LLM thinks: "Market is calm, next check can be in 6 hours"
# LLM thinks: "Earnings report tomorrow 4 PM, schedule analysis for 4:10 PM"
```

---

## 🛠️ New Tool: schedule_next_analysis

### Tool Definition

```python
@tool
async def schedule_next_analysis(
    hours_from_now: float,
    reason: str,
    priority: int = 0
) -> str:
    """
    Schedule next portfolio analysis time (LLM autonomous scheduling)
    
    Args:
        hours_from_now: Hours from now (decimals ok: 0.5 = 30 min, 2.5 = 2.5 hours)
        reason: Reason for scheduling (e.g., "Expected FOMC announcement")
        priority: Priority 0-10 (lower = higher priority), default 0
    
    Returns:
        Scheduling result
    """
```

### How It Works

```
LLM Analysis
    ↓
LLM decides: "I need to check again in 4 hours because..."
    ↓
Calls: schedule_next_analysis(hours_from_now=4, reason="Market volatility monitoring")
    ↓
Event System schedules event for 4 hours later
    ↓
Event executes at scheduled time
    ↓
LLM analyzes again
    ↓
LLM decides next check time
    ↓
Cycle repeats ♻️
```

---

## 📋 Use Cases

### 1. Event-Based Scheduling
```python
# LLM sees FOMC meeting scheduled for 2 PM
schedule_next_analysis(
    hours_from_now=2.5,  # 2:30 PM
    reason="FOMC meeting结果分析",
    priority=1  # High priority
)
```

### 2. Volatility-Based Scheduling
```python
# High volatility detected
schedule_next_analysis(
    hours_from_now=2,
    reason="高波动市场监控",
    priority=2
)

# Low volatility, market calm
schedule_next_analysis(
    hours_from_now=12,
    reason="市场平稳，例行检查",
    priority=5
)
```

### 3. Earnings/News Scheduling
```python
# AAPL earnings at market close
schedule_next_analysis(
    hours_from_now=0.25,  # 15 minutes
    reason="AAPL财报发布后分析",
    priority=1
)
```

### 4. Weekend/Holiday Handling
```python
# Friday evening, market closed for weekend
schedule_next_analysis(
    hours_from_now=60,  # Monday morning
    reason="周末休市，下周一开市检查",
    priority=5
)
```

---

## 🧠 LLM System Prompt

The LLM is instructed with:

```markdown
## 自主调度
- 分析完成后，你可以使用schedule_next_analysis安排下一次分析时间
- 例如：预期有重要新闻（如FOMC会议、财报发布），可以提前安排分析
- 例如：市场波动剧烈，可以安排更频繁的检查（如2-4小时后）
- 例如：市场平稳，可以安排较晚的检查（如明天或后天）
- 你可以根据市场情况和自己的判断，灵活安排下一次分析的时间
```

---

## 💡 Example LLM Reasoning

### Scenario 1: Calm Market
```
LLM: "Current portfolio is well-balanced. Market indices stable. 
No major news expected today. I'll schedule next check for 6 hours."

schedule_next_analysis(
    hours_from_now=6,
    reason="市场平稳，定期监控",
    priority=5
)
```

### Scenario 2: Anticipated Event
```
LLM: "Fed Chair Powell speaks at 2 PM ET. This could significantly 
impact tech stocks (40% of portfolio). I'll analyze right after."

schedule_next_analysis(
    hours_from_now=3.5,  # Powell speaks at 2PM, check at 2:30PM
    reason="美联储主席讲话后市场反应分析",
    priority=1
)
```

### Scenario 3: High Volatility
```
LLM: "SPY dropped 2% in last hour. QQQ down 2.5%. Portfolio down 3.2%.
Need to monitor closely for potential stop-loss or rebalancing."

schedule_next_analysis(
    hours_from_now=1,
    reason="市场波动剧烈，密切监控",
    priority=2
)
```

### Scenario 4: After Rebalancing
```
LLM: "Just executed rebalancing. Need to verify fills and check 
if further adjustments needed after market reacts."

schedule_next_analysis(
    hours_from_now=0.5,  # 30 minutes
    reason="重新平衡后验证执行结果",
    priority=3
)
```

---

## 🔄 Integration with Event System

### Event Flow

```
LLM calls schedule_next_analysis()
    ↓
Tool publishes event via event_system.schedule_next_analysis()
    ↓
Event with scheduled_time enters priority queue
    ↓
Event System monitors time
    ↓
When scheduled_time arrives:
    ↓
Event triggers → _handle_manual_analysis_trigger()
    ↓
Runs LLMPortfolioAgent.run_workflow()
    ↓
LLM analyzes → decides next schedule
    ↓
Cycle continues ♻️
```

### Event Priority

Events are ordered by:
1. **scheduled_time** (earliest first)
2. **priority** (lower number = higher priority)
3. **insertion order** (FIFO for same time/priority)

```python
# High priority (urgent)
priority=1  # e.g., Breaking news, FOMC announcement

# Medium priority (important)
priority=3  # e.g., Post-rebalancing check

# Normal priority (routine)
priority=5  # e.g., Regular monitoring

# Low priority (optional)
priority=8  # e.g., Weekly review
```

---

## 📊 Comparison

| Aspect | Fixed Schedule | LLM Self-Scheduling |
|--------|---------------|---------------------|
| **Timing** | Always 9:30 AM | LLM decides based on context |
| **Frequency** | Fixed daily | Adaptive (1h - 24h+) |
| **Event Awareness** | None | Can anticipate events |
| **Market Conditions** | Ignores | Adapts to volatility |
| **After Rebalancing** | No follow-up | Can schedule verification |
| **Flexibility** | Zero | Full autonomy |

---

## 🚀 Example Workflow

```
Day 1, 9:30 AM - Daily rebalance (system scheduled)
    ↓
LLM: "Market calm, next check in 6 hours"
    ↓
Day 1, 3:30 PM - LLM analysis
    ↓
LLM: "FOMC meeting tomorrow 2 PM, will check at 2:15 PM"
    ↓
Day 2, 2:15 PM - LLM analysis (scheduled by LLM)
    ↓
LLM: "Fed raised rates! Market dropping. Need to monitor closely."
    ↓
Rebalances portfolio: Reduce tech exposure, increase bonds
    ↓
LLM: "Check again in 1 hour to verify execution"
    ↓
Day 2, 3:15 PM - LLM analysis
    ↓
LLM: "Execution good. Market stabilizing. Next check in 4 hours"
    ↓
Day 2, 7:15 PM - LLM analysis
    ↓
LLM: "Market closed. Schedule Monday 9:30 AM"
    ↓
Cycle continues...
```

---

## 🎁 Benefits

### 1. Event Anticipation
- LLM can schedule analysis around known events (earnings, FOMC, etc.)
- No need to manually configure event schedules

### 2. Adaptive Frequency
- More frequent checks during volatility
- Less frequent during calm markets
- Optimal resource usage

### 3. Context Awareness
- Schedules based on portfolio state
- Considers upcoming news
- Adapts to market conditions

### 4. Verification Loops
- Can schedule follow-up checks after rebalancing
- Ensures orders filled correctly
- Allows for quick adjustments

### 5. True Autonomy
- LLM manages its own timing
- No human intervention needed
- Self-optimizing behavior

---

## 🧪 Testing Scenarios

### Test 1: Basic Scheduling
```python
# LLM schedules 2 hours later
schedule_next_analysis(2, "Regular check")
# Verify event created with correct time
```

### Test 2: Priority Handling
```python
# Create normal priority event
schedule_next_analysis(2, "Regular", priority=5)
# Create high priority event (same time)
schedule_next_analysis(2, "Urgent", priority=1)
# Verify high priority executes first
```

### Test 3: Fractional Hours
```python
# Schedule 30 minutes (0.5 hours)
schedule_next_analysis(0.5, "Quick check")
# Schedule 2.5 hours
schedule_next_analysis(2.5, "Mid-day")
```

### Test 4: Long-term Scheduling
```python
# Schedule next week
schedule_next_analysis(168, "Weekly review")  # 7 days
```

---

## 📝 Implementation Details

### Code Changes

1. **LLMPortfolioAgent.__init__**
   ```python
   self.event_system = event_system  # Reference for scheduling
   ```

2. **New Tool**
   ```python
   @tool
   async def schedule_next_analysis(...):
       await self.event_system.schedule_next_analysis(...)
   ```

3. **System Prompt Update**
   - Added "自主调度" section
   - Explained when/how to use scheduling
   - Provided examples

---

## 🔮 Future Enhancements

### 1. Calendar Integration
```python
# LLM queries economic calendar
# Automatically schedules around major events
```

### 2. Learning from History
```python
# LLM learns optimal scheduling patterns
# "High volatility usually lasts 3-4 hours, schedule accordingly"
```

### 3. Multi-Agent Coordination
```python
# Multiple agents schedule non-overlapping times
# Avoid resource contention
```

### 4. Conditional Scheduling
```python
# "Schedule analysis IF volatility exceeds 2%"
# Event only triggers if condition met
```

---

## 📚 Documentation Updated

- ✅ `src/agents/llm_portfolio_agent.py` - Added tool
- ✅ System prompt - Added scheduling instructions
- ✅ Tool docstrings - Clear parameter descriptions
- ✅ `docs/LLM_SELF_SCHEDULING.md` - This document

---

**The LLM is now truly autonomous - it decides not just WHAT to do, but WHEN to do it!** 🤖⏰
