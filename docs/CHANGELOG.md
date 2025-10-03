# Changelog

All notable changes to this project will be documented in this file.

---

## [2025-10-03] - Interval Calculation Refactoring

### 🔄 Refactoring: Unified Configurable Interval Calculation

**Summary**: Refactored time interval calculations from hardcoded functions to a unified, configurable approach.

#### Problems Solved
- Removed code duplication (3 functions → 1 unified function)
- Eliminated hardcoded time intervals
- Made scheduling intervals configurable via environment variables
- Improved code maintainability and flexibility

#### Changes

**Removed Functions**:
- `_calculate_next_market_hour()` - hardcoded 60min
- `_calculate_next_15min_interval()` - hardcoded 15min

**Added Function**:
- `_calculate_next_interval(interval_minutes, market_hours_only, ...)` - universal interval calculator

**Configuration**:
- Added `portfolio_check_interval` setting (default: 60 minutes)
- Added `risk_check_interval` setting (default: 15 minutes)
- Environment variables: `PORTFOLIO_CHECK_INTERVAL`, `RISK_CHECK_INTERVAL`

**Files Modified**:
- `src/trading_system.py`
  - Added unified `_calculate_next_interval()` function
  - Updated `_initialize_scheduled_events()` to use configurable intervals
  - Updated all event handlers to use new function
  - Load intervals from settings
  
- `config.py`
  - Added `portfolio_check_interval: int = 60`
  - Added `risk_check_interval: int = 15`
  
- `env.template`
  - Added `PORTFOLIO_CHECK_INTERVAL=60`
  - Added `RISK_CHECK_INTERVAL=15`

#### Benefits
- Any interval can be configured (5, 15, 30, 60, 120 minutes, etc.)
- Change intervals without code changes
- Single source of truth for interval calculations
- More flexible for different trading strategies
- Easier to maintain and test

#### Configuration Examples
```bash
# Conservative
PORTFOLIO_CHECK_INTERVAL=120
RISK_CHECK_INTERVAL=30

# Balanced (default)
PORTFOLIO_CHECK_INTERVAL=60
RISK_CHECK_INTERVAL=15

# Aggressive
PORTFOLIO_CHECK_INTERVAL=30
RISK_CHECK_INTERVAL=5
```

**Documentation**: `docs/INTERVAL_REFACTORING.md`

---

## [2025-10-03] - Timezone Comparison Fix

### 🔧 Bug Fix: Timezone-Aware Datetime Comparisons

**Summary**: Fixed "can't compare offset-naive and offset-aware datetimes" error in event system.

#### Problem
Event system was comparing timezone-aware datetimes from `trading_system` (US/Eastern) with naive datetimes from `datetime.now()`, causing comparison errors.

#### Solution
All datetime operations now use timezone-aware datetimes with UTC for comparisons:

**Files Modified**:
- `src/events/event_system.py`
  - Import `pytz`
  - Use `datetime.now(pytz.UTC)` for current_time in `_process_events()`
  
- `src/agents/llm_portfolio_agent.py`
  - Import `pytz`
  - Use `datetime.now(pytz.UTC)` in `schedule_next_analysis` tool
  
- `src/models/trading_models.py`
  - Import `pytz`
  - Add `utc_now()` helper function
  - `TradingEvent.timestamp` now uses `utc_now()` for timezone-aware default

#### Technical Details
- Event system uses UTC for all comparisons (timezone-agnostic)
- Python automatically converts between timezones (US/Eastern ↔ UTC)
- No more naive/aware datetime mixing
- DST handled automatically by pytz

**Documentation**: `docs/TIMEZONE_FIX.md`

---

## [2025-10-03] - Event System Refactoring & Self-Perpetuating Scheduling

### 🤖 LLM Self-Scheduling (Autonomous Agent Timing)

**Summary**: LLM can now autonomously decide when to run its next analysis.

#### New Tool: schedule_next_analysis

Added new tool to LLMPortfolioAgent that allows the LLM to schedule its own future analysis:

```python
@tool
async def schedule_next_analysis(
    hours_from_now: float,  # 0.5 = 30min, 2.5 = 2.5 hours
    reason: str,            # e.g., "Expected FOMC announcement"
    priority: int = 0       # 0-10, lower = higher priority
)
```

#### Use Cases
- **Event Anticipation**: LLM schedules around FOMC meetings, earnings reports
- **Volatility Adaptation**: More frequent checks during high volatility
- **Verification Loops**: Schedule follow-up after rebalancing
- **Context Awareness**: Adapts timing based on market conditions

#### Example Scenarios
```python
# Calm market → check in 6 hours
schedule_next_analysis(6, "Regular monitoring", 5)

# FOMC meeting → check right after
schedule_next_analysis(2.5, "Post-FOMC analysis", 1)

# High volatility → check in 1 hour
schedule_next_analysis(1, "Volatility monitoring", 2)

# After rebalancing → verify in 30 min
schedule_next_analysis(0.5, "Verify execution", 3)
```

#### System Integration
- LLMPortfolioAgent now holds reference to `event_system`
- Tool publishes events via `event_system.schedule_next_analysis()`
- Events enter priority queue with `scheduled_time` and `priority`
- When time arrives, `_handle_manual_analysis_trigger()` executes
- LLM analyzes → decides next time → cycle repeats ♻️

#### Benefits
- ✅ **True Autonomy**: LLM decides not just WHAT but WHEN
- ✅ **Event-Aware**: Can anticipate and schedule around known events
- ✅ **Adaptive**: Frequency adjusts to market conditions
- ✅ **Self-Managing**: No human intervention needed for timing

**Files Modified**:
- `src/agents/llm_portfolio_agent.py` - Added tool and event_system reference
- `docs/LLM_SELF_SCHEDULING.md` - Complete guide with examples

---

### 🔄 Self-Perpetuating Event Scheduling

**Summary**: Removed TradingScheduler completely, replaced with self-perpetuating event chains.

#### Removed (DEPRECATED)
- **TradingScheduler Class**: Entire 400+ line scheduler class no longer needed
- **Scheduler Thread**: No separate thread management
- **Schedule Library**: No third-party scheduler dependency
- **Direct Method Calls**: Scheduler no longer calls methods directly

#### Added
- **Self-Perpetuating Events**: Events schedule themselves after execution
- **Event Chain Initialization**: `_initialize_scheduled_events()` kicks off chains
- **Trading Day Calculations**: Helper methods for next occurrence calculations
  - `_calculate_next_trading_day_time()` - Next occurrence on trading day
  - `_calculate_next_market_hour()` - Next hourly check during market hours
  - `_calculate_next_15min_interval()` - Next 15-min interval

#### Changed Event Handlers
All handlers now reschedule themselves after execution:
- `_handle_daily_rebalance_trigger()` - Schedules next trading day 9:30 AM
- `_handle_eod_analysis_trigger()` - Schedules next trading day 4:05 PM
- `_handle_portfolio_check_trigger()` - Schedules next market hour
- `_handle_risk_check_trigger()` - Schedules next 15-min interval
- `_handle_manual_analysis_trigger()` - Does not reschedule (one-time)

#### Architecture Benefits
- ✅ **Event-Driven**: Pure event-driven architecture, no threads
- ✅ **Self-Perpetuating**: Events create chain reactions automatically
- ✅ **Simpler**: ~100 lines vs ~400 lines of scheduler code
- ✅ **LLM-Compatible**: LLM agents can schedule their own events
- ✅ **Zero Redundancy**: Single scheduling mechanism (events)

**Files Modified**:
- `src/trading_system.py` - Removed scheduler, added event initialization
- `src/scheduler/trading_scheduler.py` - **DEPRECATED** (marked for deletion)
- `src/scheduler/DEPRECATED.md` - Deprecation notice
- `docs/SELF_PERPETUATING_EVENTS.md` - Complete guide

**Example Event Chain**:
```python
# Start
_initialize_scheduled_events() → Publish event (scheduled_time=tomorrow 9:30)
    ↓
Event executes at 9:30
    ↓
Handler schedules next event (next trading day 9:30)
    ↓
Cycle repeats forever ♻️
```

---

## [2025-10-03] - Event System Refactoring & Scheduling

### 🎯 Major Refactoring: Event System

**Summary**: Refactored event system to focus on workflow triggering with time-based scheduling support.

#### Changed
- **Event System Role**: Event system now exclusively handles workflow triggering, not order notifications
- **Event Types**: Removed order/portfolio events; added workflow trigger events
  - Removed: `order_created`, `order_filled`, `order_canceled`, `order_rejected`, `portfolio_updated`
  - Added: `trigger_daily_rebalance`, `trigger_realtime_rebalance`, `trigger_manual_analysis`, etc.

#### Architecture Improvements
- **Decoupling**: Scheduler and RealtimeMonitor now publish events instead of direct method calls
- **Event Handlers**: Replaced 9 mixed handlers with 8 focused workflow trigger handlers
- **Design Philosophy**: Single responsibility - event system for workflow coordination only

**Files Modified**:
- `src/events/event_system.py` - Complete rewrite
- `src/trading_system.py` - New event handlers
- `src/scheduler/trading_scheduler.py` - Event-based triggering
- `src/services/realtime_monitor.py` - Event-based triggering

**Documentation**:
- `docs/EVENT_SYSTEM_REFACTORING.md` - Complete refactoring guide

---

### ⏰ New Feature: Time-Based Event Scheduling

**Summary**: Events now support scheduled execution with priority queue management.

#### Added
- **TradingEvent Model Enhancements**:
  - `scheduled_time: Optional[datetime]` - When event should execute (None = immediate)
  - `priority: int` - Event priority (lower = higher priority)
  - `__lt__` method for priority queue comparison

- **EventSystem Enhancements**:
  - Changed from `asyncio.Queue` to `asyncio.PriorityQueue`
  - Time-based event processing with re-queue mechanism
  - All trigger methods now accept `scheduled_time` parameter
  - New `schedule_next_analysis()` method for LLM self-scheduling

#### Features
- **Immediate Execution**: Events with `scheduled_time=None` execute right away (default)
- **Scheduled Execution**: Events execute at specified `scheduled_time`
- **Priority Management**: Events at same time ordered by priority field
- **LLM Self-Scheduling**: LLM agents can schedule future analysis autonomously

#### Event Execution Order
1. `scheduled_time` (earliest first, None treated as immediate)
2. `priority` field (lower number = higher priority)
3. Insertion order (via `_event_counter`)

#### Use Cases
- Pre-market analysis scheduling
- Earnings report tracking
- FOMC announcement monitoring
- Adaptive scheduling based on market volatility
- News event follow-up chains
- LLM autonomous scheduling

#### API Examples

```python
# Immediate execution (backward compatible)
await event_system.trigger_manual_analysis()

# Scheduled execution
await event_system.trigger_manual_analysis(
    context={"reason": "Check"},
    scheduled_time=datetime.now() + timedelta(hours=2)
)

# LLM self-scheduling
await event_system.schedule_next_analysis(
    scheduled_time=datetime.now() + timedelta(hours=2),
    reason="Expected FOMC announcement",
    priority=1
)
```

**Files Modified**:
- `src/models/trading_models.py` - Enhanced TradingEvent model
- `src/events/event_system.py` - Priority queue implementation

**Documentation**:
- `docs/EVENT_SCHEDULING_SYSTEM.md` - Complete technical documentation
- `docs/EVENT_SCHEDULING_EXAMPLES.md` - Real-world usage examples

#### Backward Compatibility
- ✅ All existing code works without changes
- ✅ `scheduled_time` defaults to `None` (immediate execution)
- ✅ Gradual adoption - add scheduling where useful

---

### 💵 Enhancement: Cash Position Management

**Summary**: Improved cash position handling to prevent confusion with CASH stock ticker.

#### Added
- **Cash Keyword Filtering**: Automatically filters `CASH`, `USD`, `DOLLAR`, `现金`, `美元` from allocations
- **Flexible Allocation**: Target allocations can sum to <100%, remainder is cash
- **Enhanced Portfolio Status**: Shows cash percentage and per-position percentages

#### Changes
- `get_portfolio_status` now includes `cash_percentage` and `percentage` for each position
- `rebalance_portfolio` validates total ≤100% instead of requiring ~100%
- Telegram notifications show cash allocation explicitly

**Files Modified**:
- `src/agents/llm_portfolio_agent.py` - Cash filtering and display

**Documentation**:
- `CASH_POSITION_MANAGEMENT.md` - Complete guide

---

### 🌐 Enhancement: Timezone Auto-Conversion

**Summary**: All time configurations now in US/Eastern, automatically converted to local system time.

#### Added
- **Timezone Conversion**: `_convert_et_to_local_time()` in TradingScheduler
- **DST Support**: Properly handles Daylight Saving Time transitions
- **Dependencies**: Added `pytz` and `tzlocal` for robust timezone handling

#### Changes
- All scheduled jobs now convert US/Eastern config time to local system time
- `REBALANCE_TIME` in config/env is US/Eastern, system handles conversion
- Removed redundant `daily_rebalance_time` setting

**Files Modified**:
- `src/scheduler/trading_scheduler.py` - Timezone conversion
- `config.py` - Updated comments
- `env.template` - Clarified timezone usage
- `requirements.txt` - Added pytz, tzlocal

**Documentation**:
- `TIMEZONE_CONFIG.md` - Configuration guide
- `TIMEZONE_IMPROVEMENT.md` - Technical details
- `TIMEZONE_AND_MARKET_CLOSE_FIX_V2.md` - Summary

---

### 🔒 Fix: Market Close Handling

**Summary**: Prevents repeated rebalancing attempts during market off-hours.

#### Fixed
- Added market open check in `rebalance_portfolio` tool
- LLM system prompt updated to stop if market closed
- Scheduler's `_daily_rebalance` already had market check (confirmed)

**Files Modified**:
- `src/agents/llm_portfolio_agent.py` - Market check in rebalance tool

---

### 🐛 Bug Fixes

#### Fixed: UUID Serialization
- **Issue**: `Object of type UUID is not JSON serializable`
- **Fix**: Added `default=str` to `json.dumps` calls, explicit UUID to string conversion

#### Fixed: Insufficient Funds
- **Issue**: `insufficient qty available for order`, `insufficient buying power`
- **Fix**: Enhanced `_calculate_rebalance_trades` to calculate available funds and adjust buy orders

#### Fixed: Telegram Markdown Parsing
- **Issue**: Markdown escape characters showing in messages
- **Fix**: Removed over-escaping, send LLM content directly

#### Fixed: Scheduler Thread Bug
- **Issue**: `RuntimeError` when calling `asyncio.get_event_loop()` in non-main thread
- **Fix**: Create new event loop per scheduled task execution

**Files Modified**:
- `src/agents/llm_portfolio_agent.py`
- `src/scheduler/trading_scheduler.py`

---

### 📚 Documentation

#### Added
- `docs/EVENT_SYSTEM_REFACTORING.md` - Event system redesign
- `docs/EVENT_SCHEDULING_SYSTEM.md` - Scheduling system technical guide
- `docs/EVENT_SCHEDULING_EXAMPLES.md` - Real-world usage examples
- `docs/LLM_PORTFOLIO_AGENT.md` - LLM-driven agent documentation
- `CASH_POSITION_MANAGEMENT.md` - Cash handling guide
- `TIMEZONE_CONFIG.md` - Timezone configuration guide
- `TIMEZONE_IMPROVEMENT.md` - Timezone technical details
- `TIMEZONE_AND_MARKET_CLOSE_FIX_V2.md` - Market close fix summary
- `CHANGELOG.md` - This file

---

### 🔄 Migration Guide

#### Event System
- **Before**: Scheduler/Monitor called methods directly
- **After**: Publish events via `event_system.trigger_*()` methods
- **Compatibility**: Existing code continues to work

#### Event Scheduling
- **Before**: All events executed immediately
- **After**: Events can be scheduled with `scheduled_time` parameter
- **Compatibility**: Default behavior unchanged (`scheduled_time=None`)

#### Cash Position
- **Before**: LLM might include "CASH" in allocations
- **After**: System automatically filters cash keywords
- **Compatibility**: Transparent to LLM

#### Timezone
- **Before**: Timezone ambiguous or local
- **After**: Config in US/Eastern, auto-converted
- **Compatibility**: Update `REBALANCE_TIME` to US/Eastern format

---

### 📊 Testing

All changes tested with:
- ✅ Unit tests for event priority queue ordering
- ✅ Integration tests for scheduled event execution
- ✅ Timezone conversion verification
- ✅ Cash filtering validation
- ✅ Market close handling
- ✅ No linter errors

---

### 👥 Contributors

- Event system refactoring
- Time-based scheduling implementation
- Cash management enhancement
- Timezone auto-conversion
- Market close fix
- Documentation

---

**Version**: 2025-10-03
**Status**: ✅ Production Ready

