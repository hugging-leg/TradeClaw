# ⏰ 时区配置说明

## 当前系统时区
- **系统时区**: Asia/Shanghai (CST, +0800)
- **市场时区**: US/Eastern (EST/EDT)

## 时差说明

### 夏令时期间（3月第二个周日 - 11月第一个周日）
- 美东使用EDT (UTC-4)
- 上海时间 = 美东时间 + 12小时
- **美东09:30 → 上海21:30**

### 标准时期间（11月第一个周日 - 3月第二个周日）
- 美东使用EST (UTC-5)
- 上海时间 = 美东时间 + 13小时
- **美东09:30 → 上海22:30**

## 配置建议

### 方案1：调整配置时间（推荐）

在 `.env` 或 `config.py` 中设置：

```bash
# 夏令时期间（3-11月）
DAILY_REBALANCE_TIME=21:30  # 对应美东09:30

# 标准时期间（11-3月）
DAILY_REBALANCE_TIME=22:30  # 对应美东09:30
```

**注意**：需要手动在3月和11月调整配置！

### 方案2：修改系统时区（不推荐）

```bash
sudo timedatectl set-timezone America/New_York
```

⚠️ 这会影响整个系统时间，可能影响其他应用。

### 方案3：智能时区转换（最佳，但需要代码改动）

修改 `TradingScheduler` 使其自动处理时区转换，支持夏令时自动切换。

## 当前配置状态

```python
daily_rebalance_time: str = "09:30"  # ⚠️ 系统本地时间（上海09:30 = 美东前一天21:30）
```

## 推荐配置

根据当前时间（2025年9月30日，夏令时期间）：

```bash
# .env
DAILY_REBALANCE_TIME=21:30  # 美东09:30开盘
```

## 市场休市保护

系统已添加市场状态检查：
- ✅ `rebalance_portfolio` 工具会检查市场是否开放
- ✅ 休市时返回 `market_open: false`
- ✅ LLM会停止调用并返回休市提示

## 验证方法

```python
# 测试时区转换
from datetime import datetime
import pytz

eastern = pytz.timezone('US/Eastern')
shanghai = pytz.timezone('Asia/Shanghai')

# 上海时间21:30
sh_time = shanghai.localize(datetime(2025, 10, 1, 21, 30))
# 转换为美东时间
et_time = sh_time.astimezone(eastern)
print(f"上海 {sh_time} = 美东 {et_time}")
# 输出: 上海 2025-10-01 21:30:00+08:00 = 美东 2025-10-01 09:30:00-04:00
```
