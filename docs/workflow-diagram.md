# Trading Workflow Diagram

## Overview
This diagram shows the simplified flow of the AI Trading Agent's main processes.

## Simplified System Flow

```mermaid
graph LR
    %% User Interaction
    subgraph "User Control"
        USER[👤 User]
        CMD[📱 Telegram Commands]
    end
    
    %% Main System
    subgraph "Trading System"
        TS[🎯 Trading System]
        WF[🤖 AI Workflow]
        DECISION[📊 Trading Decision]
    end
    
    %% External Services
    subgraph "External APIs"
        BROKER[🏦 Alpaca<br/>Trading]
        DATA[📈 Tiingo<br/>Market Data]
        NEWS[📰 Tiingo<br/>News]
        AI[🧠 OpenAI/DeepSeek<br/>LLM]
    end
    
    %% Workflow Types
    subgraph "Workflow Types"
        SEQ[🔄 Sequential<br/>Fixed Steps]
        TOOL[🛠️ Tool Calling<br/>Dynamic LLM]
    end
    
    %% Flow connections
    USER --> CMD
    CMD --> TS
    TS --> WF
    
    %% Workflow selection
    WF --> SEQ
    WF --> TOOL
    
    %% Data gathering
    SEQ --> DATA
    SEQ --> NEWS
    SEQ --> BROKER
    
    TOOL --> AI
    AI --> DATA
    AI --> NEWS
    AI --> BROKER
    
    %% Decision making
    SEQ --> DECISION
    TOOL --> DECISION
    DECISION --> BROKER
    
    %% Notifications back to user
    DECISION --> CMD
    BROKER --> CMD
    
    %% Styling
    classDef user fill:#f1f8e9,stroke:#33691e,stroke-width:2px
    classDef system fill:#e3f2fd,stroke:#0d47a1,stroke-width:2px
    classDef external fill:#e1f5fe,stroke:#01579b,stroke-width:2px
    classDef workflow fill:#fff3e0,stroke:#e65100,stroke-width:2px
    
    class USER,CMD user
    class TS,WF,DECISION system
    class BROKER,DATA,NEWS,AI external
    class SEQ,TOOL workflow
```

## Process Flow Description

### 1. User Interaction
- User sends commands via Telegram Bot
- Commands trigger system operations

### 2. Workflow Selection
- System selects appropriate workflow type:
  - **Sequential**: Fixed 4-step process
  - **Tool Calling**: Dynamic LLM-driven process

### 3. Data Collection
- **Sequential Workflow**: Systematically gathers data from all sources
- **Tool Calling Workflow**: LLM decides which data sources to query

### 4. Decision Making
- Both workflows produce trading decisions
- Decisions are executed through the broker API

### 5. Feedback Loop
- Results are communicated back to user via Telegram
- System maintains real-time status updates

## Workflow Comparison

| Aspect | Sequential Workflow | Tool Calling Workflow |
|--------|-------------------|---------------------|
| **Process** | Fixed 4 steps | Dynamic tool selection |
| **Predictability** | High | Variable |
| **Cost** | Lower | Higher |
| **Flexibility** | Limited | High |
| **Best For** | Routine trading | Complex analysis | 