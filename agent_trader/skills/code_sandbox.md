---
name: code_sandbox
description: 代码执行与终端 — 在安全沙箱中执行 Python 代码或终端命令
---

# Code Sandbox — 代码执行与终端

## 代码执行工具

### `execute_python`
在 OpenSandbox 中执行 Python 代码。

```
execute_python(code="""
import pandas as pd
import numpy as np

# 计算投资组合的夏普比率
returns = pd.Series([0.02, -0.01, 0.03, 0.01, -0.02, 0.04])
sharpe = returns.mean() / returns.std() * np.sqrt(252)
print(f"Annualized Sharpe Ratio: {sharpe:.2f}")
""")
```

### `sandbox_terminal`
在 OpenSandbox 中执行终端命令。

```
sandbox_terminal(command="pip install yfinance && python -c 'import yfinance; print(yfinance.__version__)'")
```

## 使用场景

### 数据计算
- 计算技术指标（RSI、MACD、布林带等）
- 计算投资组合风险指标（夏普比率、最大回撤、VaR）
- 相关性分析
- 回测策略

### 数据可视化
- 生成价格走势图
- 绘制技术指标图
- 投资组合分布饼图

### 安装依赖
```
sandbox_terminal(command="pip install --break-system-packages yfinance ta-lib")
```

## 注意事项

1. **沙箱环境**：代码在隔离的 OpenSandbox 容器中执行，不影响主系统
2. **持久化**：同一 session 内安装的依赖在后续执行中可用
3. **超时**：默认超时 30 秒，复杂计算可能需要更长时间
4. **网络**：沙箱可以访问外部网络（下载数据、安装包等）
5. **无 GUI**：不支持图形界面，matplotlib 等需要使用 `plt.savefig()` 保存

## 常用库

沙箱预装了常用 Python 库：
- `pandas`, `numpy` — 数据处理
- `requests` — HTTP 请求
- 其他库需要通过 `pip install` 安装
