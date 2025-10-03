# 📅 Event Scheduling - Usage Examples

Complete examples showing how to use the new time-based event scheduling system.

---

## 🚀 Quick Start

### Example 1: Immediate Execution (Default Behavior)

```python
# Execute immediately (backward compatible)
await event_system.trigger_manual_analysis()
await event_system.trigger_daily_rebalance()
```

### Example 2: Schedule for Specific Time

```python
from datetime import datetime, timedelta

# Schedule analysis for 2 hours from now
scheduled_time = datetime.now() + timedelta(hours=2)
await event_system.trigger_manual_analysis(
    context={"reason": "Scheduled check"},
    scheduled_time=scheduled_time
)

# Schedule portfolio check for tomorrow 9:30 AM
tomorrow_morning = datetime.now().replace(
    hour=9, minute=30, second=0, microsecond=0
) + timedelta(days=1)
await event_system.trigger_portfolio_check(
    scheduled_time=tomorrow_morning
)
```

### Example 3: LLM Self-Scheduling

```python
# LLM agent schedules next analysis based on its decision
await event_system.schedule_next_analysis(
    scheduled_time=datetime.now() + timedelta(hours=2),
    reason="Expected FOMC announcement",
    priority=1,  # High priority
    context={
        "expected_event": "FOMC",
        "symbols_to_watch": ["SPY", "QQQ"]
    }
)
```

---

## 💼 Real-World Scenarios

### Scenario 1: Pre-Market Preparation

```python
from datetime import datetime, time, timedelta
import pytz

# Schedule pre-market analysis
eastern = pytz.timezone('US/Eastern')
today = datetime.now(eastern)

# Market opens at 9:30 AM ET
market_open = today.replace(hour=9, minute=30, second=0, microsecond=0)
if market_open < datetime.now(eastern):
    market_open += timedelta(days=1)  # Tomorrow

# Schedule analysis 5 minutes before market open
pre_market_time = market_open - timedelta(minutes=5)

await event_system.trigger_manual_analysis(
    context={
        "type": "pre_market_analysis",
        "target_time": market_open.isoformat()
    },
    scheduled_time=pre_market_time
)

print(f"📅 Pre-market analysis scheduled for {pre_market_time}")
```

### Scenario 2: Earnings Calendar

```python
# Company earnings calendar
earnings_calendar = {
    "AAPL": datetime(2025, 10, 3, 16, 30, 0),  # After market close
    "MSFT": datetime(2025, 10, 4, 16, 30, 0),
    "GOOGL": datetime(2025, 10, 5, 16, 30, 0),
}

# Schedule analysis for each earnings
for symbol, earnings_time in earnings_calendar.items():
    # Schedule 5 minutes after earnings release
    analysis_time = earnings_time + timedelta(minutes=5)
    
    await event_system.schedule_next_analysis(
        scheduled_time=analysis_time,
        reason=f"{symbol} earnings report",
        priority=0,  # Highest priority
        context={
            "trigger": "earnings",
            "symbol": symbol,
            "earnings_time": earnings_time.isoformat()
        }
    )
    
    print(f"📊 {symbol} earnings analysis scheduled for {analysis_time}")
```

### Scenario 3: Federal Reserve Announcements

```python
# FOMC meeting schedule
fomc_announcement = datetime(2025, 10, 3, 14, 0, 0)  # 2 PM ET

# Schedule pre-FOMC analysis (30 minutes before)
await event_system.schedule_next_analysis(
    scheduled_time=fomc_announcement - timedelta(minutes=30),
    reason="Pre-FOMC analysis - prepare for volatility",
    priority=1
)

# Schedule post-FOMC analysis (5 minutes after)
await event_system.schedule_next_analysis(
    scheduled_time=fomc_announcement + timedelta(minutes=5),
    reason="Post-FOMC analysis - react to announcement",
    priority=0  # Higher priority than pre-FOMC
)

# Schedule follow-up analysis (1 hour after)
await event_system.schedule_next_analysis(
    scheduled_time=fomc_announcement + timedelta(hours=1),
    reason="Post-FOMC follow-up - assess market reaction",
    priority=2
)

print(f"🏛️  FOMC event schedule created")
print(f"   Pre-announcement: {fomc_announcement - timedelta(minutes=30)}")
print(f"   Post-announcement: {fomc_announcement + timedelta(minutes=5)}")
print(f"   Follow-up: {fomc_announcement + timedelta(hours=1)}")
```

### Scenario 4: Adaptive Scheduling Based on Volatility

```python
# In LLM Portfolio Agent workflow
async def run_workflow(self, context: Dict):
    # ... perform analysis ...
    
    # Get current market volatility
    volatility = await self.calculate_market_volatility()
    
    # Adaptive scheduling based on volatility
    if volatility > 0.02:  # High volatility (>2%)
        next_check = datetime.now() + timedelta(minutes=30)
        priority = 0  # High priority
        reason = f"High volatility ({volatility:.2%}), frequent monitoring"
    elif volatility > 0.01:  # Medium volatility (1-2%)
        next_check = datetime.now() + timedelta(hours=1)
        priority = 1
        reason = f"Medium volatility ({volatility:.2%}), hourly check"
    else:  # Low volatility (<1%)
        next_check = datetime.now() + timedelta(hours=3)
        priority = 2
        reason = f"Low volatility ({volatility:.2%}), periodic check"
    
    # Schedule next analysis
    await self.trading_system.event_system.schedule_next_analysis(
        scheduled_time=next_check,
        reason=reason,
        priority=priority,
        context={
            "volatility": float(volatility),
            "adaptive": True
        }
    )
    
    logger.info(f"🔄 Next analysis: {next_check} - {reason}")
```

### Scenario 5: News-Triggered Analysis Chain

```python
# When breaking news is detected
async def handle_breaking_news(news: Dict):
    """
    Handle breaking news with scheduled follow-up analysis
    """
    symbol = news['symbol']
    headline = news['headline']
    
    # Immediate analysis
    await event_system.trigger_manual_analysis(
        context={
            "trigger": "breaking_news",
            "symbol": symbol,
            "headline": headline
        }
    )
    
    # Schedule follow-up analyses
    follow_ups = [
        (timedelta(minutes=15), "Short-term reaction", 0),
        (timedelta(hours=1), "Medium-term impact", 1),
        (timedelta(hours=4), "Long-term assessment", 2),
    ]
    
    for delta, reason, priority in follow_ups:
        await event_system.schedule_next_analysis(
            scheduled_time=datetime.now() + delta,
            reason=f"{symbol} news follow-up: {reason}",
            priority=priority,
            context={
                "trigger": "news_followup",
                "symbol": symbol,
                "original_news": headline
            }
        )
    
    print(f"📰 News analysis chain created for {symbol}")
```

---

## 🔧 Integration Examples

### In Scheduler

```python
# src/scheduler/trading_scheduler.py

async def _daily_rebalance(self):
    """Daily rebalance with optional scheduling"""
    if not await self.trading_system.is_market_open():
        # Market closed, schedule for market open
        eastern = pytz.timezone('US/Eastern')
        now = datetime.now(eastern)
        
        market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
        if market_open < now:
            market_open += timedelta(days=1)
        
        await self.trading_system.event_system.trigger_daily_rebalance(
            context={"trigger": "daily_rebalance", "deferred": True},
            scheduled_time=market_open
        )
        logger.info(f"Market closed, rebalance scheduled for {market_open}")
        return
    
    # Market open, trigger immediately
    await self.trading_system.event_system.trigger_daily_rebalance(
        context={"trigger": "daily_rebalance", "timestamp": datetime.now().isoformat()}
    )
```

### In LLM Agent Tool

```python
# Add scheduling tool to LLM agent

@tool
async def schedule_analysis(
    hours_from_now: float,
    reason: str,
    priority: int = 1
) -> str:
    """
    Schedule a future analysis (LLM self-scheduling)
    
    Args:
        hours_from_now: How many hours in the future (e.g., 2.5 for 2.5 hours)
        reason: Why this analysis is scheduled
        priority: Priority level (0=highest, 1, 2, ...)
    
    Returns:
        Confirmation message
    """
    scheduled_time = datetime.now() + timedelta(hours=hours_from_now)
    
    await self.trading_system.event_system.schedule_next_analysis(
        scheduled_time=scheduled_time,
        reason=reason,
        priority=priority,
        context={
            "llm_scheduled": True,
            "hours_from_now": hours_from_now
        }
    )
    
    return f"Analysis scheduled for {scheduled_time.isoformat()} ({hours_from_now}h from now): {reason}"
```

**LLM System Prompt Addition**:
```markdown
## Scheduling Tool

You can schedule your next analysis using:
- schedule_analysis(hours, reason, priority): Schedule future analysis

Examples:
- Schedule in 2 hours for earnings: schedule_analysis(2, "AAPL earnings", 0)
- Schedule in 4 hours for market close: schedule_analysis(4, "EOD review", 1)

Use this when you anticipate important events or want adaptive monitoring.
```

---

## 📊 Testing Examples

### Test 1: Verify Execution Order

```python
async def test_event_ordering():
    """Test that events execute in correct order"""
    from src.events.event_system import event_system
    
    executed_events = []
    
    # Mock handler
    async def test_handler(event):
        executed_events.append(event.event_type)
    
    # Register handler
    event_system.register_handler("test_event", test_handler)
    
    # Schedule events in random order
    await event_system.publish_event(TradingEvent(
        event_type="test_event",
        data={"order": 3},
        scheduled_time=datetime.now() + timedelta(seconds=3)
    ))
    
    await event_system.publish_event(TradingEvent(
        event_type="test_event",
        data={"order": 1},
        scheduled_time=datetime.now() + timedelta(seconds=1)
    ))
    
    await event_system.publish_event(TradingEvent(
        event_type="test_event",
        data={"order": 2},
        scheduled_time=datetime.now() + timedelta(seconds=2)
    ))
    
    # Wait for all events to execute
    await asyncio.sleep(4)
    
    # Verify order
    assert executed_events == ["test_event", "test_event", "test_event"]
    print("✅ Events executed in scheduled order")
```

### Test 2: Priority Verification

```python
async def test_priority():
    """Test that priority affects execution order"""
    executed = []
    
    async def test_handler(event):
        executed.append(event.data["label"])
    
    event_system.register_handler("test", test_handler)
    
    # All scheduled for same time but different priorities
    target_time = datetime.now() + timedelta(seconds=2)
    
    await event_system.publish_event(TradingEvent(
        event_type="test",
        data={"label": "low"},
        scheduled_time=target_time,
        priority=10
    ))
    
    await event_system.publish_event(TradingEvent(
        event_type="test",
        data={"label": "high"},
        scheduled_time=target_time,
        priority=0
    ))
    
    await event_system.publish_event(TradingEvent(
        event_type="test",
        data={"label": "medium"},
        scheduled_time=target_time,
        priority=5
    ))
    
    await asyncio.sleep(3)
    
    # Should execute: high → medium → low
    assert executed == ["high", "medium", "low"]
    print("✅ Priority ordering works correctly")
```

---

## 🎯 Best Practices

### 1. Use Immediate for Time-Critical Events

```python
# ✅ Good: Immediate execution for urgent events
await event_system.trigger_realtime_rebalance(
    reason="price_change",
    details={"symbol": "AAPL", "change": -5.2}
    # No scheduled_time = immediate
)
```

### 2. Schedule for Known Future Events

```python
# ✅ Good: Schedule for known events
earnings_time = datetime(2025, 10, 3, 16, 30, 0)
await event_system.schedule_next_analysis(
    scheduled_time=earnings_time,
    reason="AAPL earnings"
)
```

### 3. Use Priority Wisely

```python
# ✅ Good: Use priority to differentiate importance
await event_system.schedule_next_analysis(
    scheduled_time=target_time,
    reason="Critical: FOMC announcement",
    priority=0  # Highest
)

await event_system.schedule_next_analysis(
    scheduled_time=target_time,
    reason="Routine: Portfolio check",
    priority=5  # Lower
)
```

### 4. Clean Context Data

```python
# ✅ Good: Include relevant context
await event_system.trigger_manual_analysis(
    context={
        "trigger": "earnings",
        "symbol": "AAPL",
        "expected_eps": 1.50,
        "previous_eps": 1.45
    },
    scheduled_time=earnings_time
)
```

---

## ⚠️ Common Pitfalls

### ❌ Don't: Schedule in the Past

```python
# ❌ Bad: Past time will execute immediately (probably not what you want)
past_time = datetime.now() - timedelta(hours=1)
await event_system.trigger_manual_analysis(scheduled_time=past_time)

# ✅ Good: Verify time is in future
target_time = calculate_target_time()
if target_time > datetime.now():
    await event_system.trigger_manual_analysis(scheduled_time=target_time)
else:
    logger.warning(f"Target time {target_time} is in the past")
```

### ❌ Don't: Over-schedule

```python
# ❌ Bad: Too many events in short time
for i in range(100):
    await event_system.schedule_next_analysis(
        scheduled_time=datetime.now() + timedelta(minutes=i),
        reason=f"Check {i}"
    )

# ✅ Good: Reasonable scheduling
await event_system.schedule_next_analysis(
    scheduled_time=datetime.now() + timedelta(hours=1),
    reason="Hourly check"
)
```

### ❌ Don't: Ignore Timezone

```python
# ❌ Bad: Naive datetime (timezone unaware)
target = datetime(2025, 10, 3, 14, 0, 0)

# ✅ Good: Timezone-aware datetime
import pytz
eastern = pytz.timezone('US/Eastern')
target = eastern.localize(datetime(2025, 10, 3, 14, 0, 0))
```

---

**Now you can leverage time-based event scheduling for flexible workflow automation!** 📅✨
