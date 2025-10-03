# ⏰ Event Scheduling System

**Date**: 2025-10-03  
**Feature**: Time-based Event Scheduling with Priority Queue

---

## 🎯 Overview

The event system now supports **time-based scheduling** with a **priority queue**, enabling:

1. **Delayed Execution**: Events can be scheduled for future execution
2. **LLM Self-Scheduling**: LLM agents can autonomously schedule their next analysis
3. **Priority Management**: Events at the same time are ordered by priority
4. **Immediate Execution**: Events without `scheduled_time` execute immediately

---

## 📦 Key Components

### 1. Enhanced `TradingEvent` Model

**Location**: `src/models/trading_models.py`

```python
class TradingEvent(BaseModel):
    """
    Trading event with scheduled execution support
    """
    event_type: str  # Event type
    timestamp: datetime  # When event was created
    scheduled_time: Optional[datetime] = None  # When to execute (None = immediate)
    data: Dict[str, Any]  # Event data
    processed: bool = False
    priority: int = 0  # Lower = higher priority
    
    def __lt__(self, other):
        """Compare for priority queue ordering"""
        # Primary: scheduled_time (earlier first)
        # Secondary: priority (lower number = higher priority)
```

**New Fields**:
- `scheduled_time`: When the event should execute (`None` = immediate)
- `priority`: Priority level (0 = highest, 1, 2, ... = lower)

---

### 2. Priority Queue in `EventSystem`

**Location**: `src/events/event_system.py`

**Before**:
```python
self.event_queue = asyncio.Queue()  # FIFO queue
```

**After**:
```python
self.event_queue = asyncio.PriorityQueue()  # Priority queue (time-ordered)
self._event_counter = 0  # Maintains insertion order for same-time events
```

**Event Storage**:
```python
# Events stored as tuple: (event, counter)
# Sorted by event.__lt__ which compares:
# 1. scheduled_time (earliest first)
# 2. priority field (lower = higher)
# 3. counter (insertion order)
```

---

### 3. Time-Based Event Processing

**Location**: `src/events/event_system.py:_process_events()`

```python
async def _process_events(self):
    """
    Process Events from Priority Queue
    
    - Checks scheduled_time before executing
    - Re-queues events if scheduled time hasn't arrived
    - Processes immediate events right away
    """
    while self.is_running:
        event_tuple = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
        event, counter = event_tuple
        
        current_time = datetime.now()
        
        if event.scheduled_time and event.scheduled_time > current_time:
            # Not time yet, calculate wait
            wait_seconds = (event.scheduled_time - current_time).total_seconds()
            
            if wait_seconds < 1.0:
                # Very soon, just wait
                await asyncio.sleep(wait_seconds)
                await self._handle_event(event)
            else:
                # Re-queue for later
                await self.event_queue.put((event, counter))
                await asyncio.sleep(0.5)  # Avoid busy loop
        else:
            # Time has arrived (or immediate), execute now
            await self._handle_event(event)
```

**Key Logic**:
1. Get next event from priority queue
2. Check if `scheduled_time` has arrived
3. If not, re-queue and wait
4. If yes (or `None`), execute immediately

---

## 🚀 Usage Examples

### Example 1: Immediate Execution (Default)

```python
# No scheduled_time = execute immediately
await event_system.trigger_manual_analysis()
```

### Example 2: Delayed Execution

```python
from datetime import datetime, timedelta

# Schedule for 2 hours from now
scheduled_time = datetime.now() + timedelta(hours=2)
await event_system.trigger_manual_analysis(
    context={"reason": "Delayed analysis"},
    scheduled_time=scheduled_time
)
```

### Example 3: LLM Self-Scheduling

```python
# LLM agent decides to schedule next analysis
await event_system.schedule_next_analysis(
    scheduled_time=datetime.now() + timedelta(hours=2),
    reason="Expected FOMC announcement at 2pm",
    priority=1,  # Higher priority than regular analysis
    context={
        "expected_event": "FOMC",
        "symbols_to_watch": ["SPY", "QQQ", "GLD"]
    }
)
```

**Output**:
```
[INFO] LLM Scheduled Analysis: 2025-10-03T16:00:00 - Expected FOMC announcement at 2pm
[DEBUG] Event Scheduled: trigger_manual_analysis at 2025-10-03T16:00:00
...
[INFO] Executing Scheduled Event: trigger_manual_analysis
```

### Example 4: Priority Management

```python
# Two events scheduled for the same time
# Lower priority number = executes first

# High priority event
await event_system.trigger_manual_analysis(
    scheduled_time=datetime(2025, 10, 3, 14, 0, 0),
    priority=0  # Highest priority
)

# Low priority event
await event_system.trigger_portfolio_check(
    scheduled_time=datetime(2025, 10, 3, 14, 0, 0),
    priority=5  # Lower priority
)

# Result: manual_analysis executes before portfolio_check
```

---

## 📊 Event Flow Diagram

### Immediate Event
```
Publish Event (scheduled_time=None)
        │
        v
  Priority Queue
        │
        v
  _process_events checks time
        │
        │ (None = immediate)
        v
  Execute Handler
```

### Scheduled Event
```
Publish Event (scheduled_time=14:00)
        │
        v
  Priority Queue (sorted by time)
        │
        v
  _process_events checks time
        │
        ├─ Not time yet (13:58)
        │   │
        │   v
        │  Re-queue
        │   │
        │   v
        │  Sleep 0.5s
        │   │
        │   └─> Loop back
        │
        └─ Time arrived (14:00)
            │
            v
        Execute Handler
```

---

## 🔧 API Changes

### All Trigger Methods Now Support `scheduled_time`

```python
# Before (immediate only)
await event_system.trigger_daily_rebalance(context)

# After (with optional scheduling)
await event_system.trigger_daily_rebalance(
    context=context,
    scheduled_time=datetime.now() + timedelta(hours=1)
)
```

**Updated Methods**:
- `trigger_daily_rebalance(context, scheduled_time)`
- `trigger_realtime_rebalance(reason, details, scheduled_time)`
- `trigger_manual_analysis(context, scheduled_time)`
- `trigger_portfolio_check(scheduled_time)`
- `trigger_risk_check(scheduled_time)`
- `trigger_eod_analysis(scheduled_time)`
- `publish_system_event(event_type, message, level, scheduled_time)`

**New Method**:
```python
async def schedule_next_analysis(
    scheduled_time: datetime,
    reason: str,
    priority: int = 0,
    context: Dict[str, Any] = None
):
    """
    LLM Self-Scheduling
    
    Allows LLM agents to autonomously schedule future analysis
    based on their decision-making process.
    """
```

---

## 💡 LLM Agent Integration

### In `llm_portfolio_agent.py`

```python
async def run_workflow(self, context: Dict):
    # ... LLM analysis ...
    
    # LLM decides to schedule next analysis
    if should_schedule_next_analysis:
        scheduled_time = determine_next_analysis_time()  # e.g., 2 hours later
        
        await self.trading_system.event_system.schedule_next_analysis(
            scheduled_time=scheduled_time,
            reason="Expected market catalyst",
            priority=1
        )
```

### System Prompt Update (Future)

```markdown
## Event Scheduling Tool

You can schedule your next analysis by calling:
- schedule_next_analysis(time, reason): Schedule future analysis

Example:
If you expect important news at 2pm, you can schedule:
schedule_next_analysis("2025-10-03 14:00", "FOMC announcement")
```

---

## 🧪 Testing Examples

### Test 1: Immediate vs Delayed

```python
# Test immediate execution
start = datetime.now()
await event_system.trigger_manual_analysis()
# Executes within ~100ms

# Test delayed execution
scheduled = datetime.now() + timedelta(seconds=5)
await event_system.trigger_manual_analysis(scheduled_time=scheduled)
# Waits ~5 seconds before executing
```

### Test 2: Priority Ordering

```python
# Schedule 3 events for same time with different priorities
target_time = datetime.now() + timedelta(seconds=10)

await event_system.trigger_manual_analysis(
    context={"test": "low"},
    scheduled_time=target_time,
    priority=10
)

await event_system.trigger_manual_analysis(
    context={"test": "high"},
    scheduled_time=target_time,
    priority=0
)

await event_system.trigger_manual_analysis(
    context={"test": "medium"},
    scheduled_time=target_time,
    priority=5
)

# Execution order: high → medium → low
```

---

## 🔍 Implementation Details

### Priority Queue Tuple Format

```python
# Queue stores: (event, counter)
await self.event_queue.put((event, self._event_counter))
self._event_counter += 1  # Ensures insertion order for same-time events
```

### Event Comparison Logic

```python
def __lt__(self, other):
    """
    Comparison for priority queue ordering
    
    Priority:
    1. scheduled_time (earlier = higher priority)
       - None treated as immediate (current time)
    2. priority field (lower number = higher priority)
    3. Implicitly: counter (insertion order)
    """
    self_time = self.scheduled_time or self.timestamp
    other_time = other.scheduled_time or other.timestamp
    
    if self_time != other_time:
        return self_time < other_time
    
    return self.priority < other.priority
```

### Re-queue Strategy

```python
if wait_seconds < 1.0:
    # Very soon, just wait inline
    await asyncio.sleep(wait_seconds)
    await self._handle_event(event)
else:
    # Future event, re-queue
    await self.event_queue.put((event, counter))
    await asyncio.sleep(0.5)  # Prevent busy loop
```

**Why re-queue instead of sleep?**
- Allows other immediate events to execute
- Prevents blocking the event loop
- Maintains priority queue ordering

---

## 📈 Benefits

| Feature | Before | After |
|---------|--------|-------|
| **Execution** | Immediate only | Immediate + Scheduled ⭐ |
| **Queue Type** | FIFO | Priority (time-ordered) ⭐ |
| **LLM Autonomy** | Manual only | Self-scheduling ⭐ |
| **Event Order** | Insertion order | Time + Priority ⭐ |
| **Use Cases** | Limited | Flexible scheduling ⭐ |

---

## 🎯 Use Cases

### 1. Pre-Market Analysis
```python
# Schedule analysis 5 minutes before market open
market_open = datetime(2025, 10, 3, 9, 30, 0)  # 9:30 AM ET
pre_market = market_open - timedelta(minutes=5)

await event_system.trigger_manual_analysis(
    context={"type": "pre_market"},
    scheduled_time=pre_market
)
```

### 2. Earnings Report
```python
# Schedule analysis for earnings release
earnings_time = datetime(2025, 10, 3, 16, 0, 0)  # 4 PM ET

await event_system.schedule_next_analysis(
    scheduled_time=earnings_time,
    reason="AAPL earnings report",
    priority=0  # High priority
)
```

### 3. FOMC Announcement
```python
# Schedule around Fed announcement
fomc_time = datetime(2025, 10, 3, 14, 0, 0)  # 2 PM ET

await event_system.schedule_next_analysis(
    scheduled_time=fomc_time - timedelta(minutes=30),
    reason="Pre-FOMC analysis",
    priority=1
)

await event_system.schedule_next_analysis(
    scheduled_time=fomc_time + timedelta(minutes=5),
    reason="Post-FOMC analysis",
    priority=0  # Higher priority than pre-FOMC
)
```

### 4. Adaptive Scheduling (LLM)
```python
# LLM decides when to check next based on market conditions
if market_volatility > threshold:
    next_check = datetime.now() + timedelta(minutes=30)  # Check frequently
else:
    next_check = datetime.now() + timedelta(hours=2)  # Check less often

await event_system.schedule_next_analysis(
    scheduled_time=next_check,
    reason=f"Adaptive scheduling: volatility={market_volatility}",
    priority=2
)
```

---

## 🔒 Edge Cases Handled

1. **`None` scheduled_time**: Executes immediately ✅
2. **Past scheduled_time**: Executes immediately ✅
3. **Same scheduled_time**: Ordered by priority ✅
4. **Event queue overflow**: Handled by asyncio.PriorityQueue ✅
5. **System shutdown with pending events**: Graceful cleanup ✅

---

## 📝 Migration Notes

### Existing Code Compatibility

**All existing code continues to work** without changes:

```python
# Old code (still works, scheduled_time defaults to None)
await event_system.trigger_manual_analysis()

# New code (with scheduling)
await event_system.trigger_manual_analysis(
    scheduled_time=datetime.now() + timedelta(hours=1)
)
```

### Optional Migration

```python
# You can gradually adopt scheduling where useful:

# Scheduler (can add delayed triggers for specific events)
await self.trading_system.event_system.trigger_daily_rebalance(
    context={"trigger": "daily_rebalance"},
    scheduled_time=None  # Immediate (default)
)

# LLM Agent (can use self-scheduling)
await self.trading_system.event_system.schedule_next_analysis(
    scheduled_time=next_analysis_time,
    reason="Expected catalyst"
)
```

---

**Now the event system supports flexible time-based scheduling!** ⏰✨
