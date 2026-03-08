"""
Black-Litterman Portfolio Optimization Workflow

结合 Black-Litterman 模型和 LLM 分析的智能组合优化:
1. LLM 分析市场生成投资观点 (Views)
2. 从历史数据计算市场均衡收益和协方差
3. Black-Litterman 模型融合观点和市场先验
4. 生成最优组合配置并执行

依赖：
    pip install pypfopt cvxpy

参考：
    - Black & Litterman (1992): "Global Portfolio Optimization"
    - He & Litterman (1999): "The Intuition Behind Black-Litterman"
"""

import json
import time
from typing import Dict, List, Any, Optional, Tuple
from datetime import timedelta

import numpy as np
import pandas as pd

from config import settings

from agent_trader.utils.logging_config import get_logger
from agent_trader.utils.timezone import utc_now, format_for_display
from agent_trader.agents.workflow_base import WorkflowBase
from agent_trader.agents.workflow_factory import register_workflow
from agent_trader.agents.tools.trading_tools import (
    calculate_rebalance_trades, execute_rebalance_trades,
)

logger = get_logger(__name__)

# 尝试导入 pypfopt
try:
    from pypfopt import BlackLittermanModel, EfficientFrontier
    from pypfopt import risk_models
    from pypfopt.black_litterman import market_implied_prior_returns
    PYPFOPT_AVAILABLE = True
except ImportError:
    PYPFOPT_AVAILABLE = False
    logger.warning("pyportfolioopt 未安装。运行: pip install pyportfolioopt cvxpy")


BL_SYSTEM_PROMPT = """\
你是一位专业的量化投资分析师，负责为 Black-Litterman 模型提供投资观点。

## 你的任务
1. 分析市场新闻、宏观经济数据和个股信息
2. 对资产池中的股票/ETF 形成投资观点
3. 为每个观点提供置信度评估

## 观点格式
- 观点表示为预期超额收益率（相对于市场）
- 例如: AAPL: 0.15 表示预期 AAPL 超越市场 15%
- 例如: TLT: -0.05 表示预期 TLT 跑输市场 5%
- 置信度 0-1，1 表示非常确定

## 分析要点
- 关注 Fed 货币政策对股债的影响
- 关注科技股的业绩和估值
- 关注地缘政治对大宗商品的影响
- 关注行业轮动和风格切换
- 只对你有明确观点的资产发表意见，不必覆盖所有资产

## 输出
使用 generate_investment_views 工具输出你的观点"""


@register_workflow(
    "black_litterman",
    description="Black-Litterman 量化组合优化",
    features=["📊 Black-Litterman 模型", "LLM 生成观点", "均值-方差优化"],
    best_for="量化 + AI 结合的科学配置"
)
class BlackLittermanWorkflow(WorkflowBase):
    """Black-Litterman 组合优化 Workflow"""

    # 修改 bl_default_universe 时也需要 rebuild agent（因为 effective prompt 会变）
    _REBUILD_KEYS = frozenset({"system_prompt", "bl_default_universe"})

    def _default_config(self) -> Dict[str, Any]:
        return {
            "system_prompt": BL_SYSTEM_PROMPT,
            "bl_risk_aversion": settings.bl_risk_aversion,
            "bl_historical_days": settings.bl_historical_days,
            "bl_base_variance": settings.bl_base_variance,
            "bl_min_weight": settings.bl_min_weight,
            "bl_default_universe": settings.get_bl_default_universe(),
        }

    def _get_effective_system_prompt(self) -> str:
        """system_prompt + 资产池列表，运行时拼接。"""
        prompt = self._config.get("system_prompt", "")
        universe = self._config.get("bl_default_universe", [])
        if universe:
            prompt += f"\n\n## 资产池\n{', '.join(universe)}"
        return prompt

    def __init__(self, **kwargs):
        universe = kwargs.pop("universe", None)
        risk_aversion = kwargs.pop("risk_aversion", None)
        session_id = kwargs.pop("session_id", "bl_agent")

        super().__init__(**kwargs)

        if not PYPFOPT_AVAILABLE:
            raise ImportError(
                "pypfopt 未安装。请运行: pip install pypfopt cvxpy"
            )

        # 如果通过 kwargs 传入了自定义值，覆盖 _config 中的默认值
        if universe:
            self._config["bl_default_universe"] = universe
        if risk_aversion is not None:
            self._config["bl_risk_aversion"] = risk_aversion

        # BL 观点状态（供 analysis_tools 中的 generate_investment_views 写入）
        self._current_views: Dict[str, float] = {}
        self._current_confidences: Dict[str, float] = {}
        self._current_reasoning: str = ""

        # 初始化 LLM + Tools + Agent（基类方法）
        self._init_agent(session_id=session_id)

        # 缓存
        self._cached_prices: Optional[pd.DataFrame] = None
        self._cached_cov: Optional[pd.DataFrame] = None
        self._last_optimization: Optional[Dict] = None

        logger.info(
            f"Black-Litterman Workflow 已初始化 "
            f"(资产池: {len(self._config['bl_default_universe'])} 个, "
            f"风险厌恶: {self._config['bl_risk_aversion']})"
        )

    # ========== BL 模型核心逻辑 ==========

    async def _fetch_historical_prices(self, days: int = None) -> pd.DataFrame:
        """获取历史价格数据"""
        if days is None:
            days = self._config.get("bl_historical_days", 252)
        prices_dict = {}
        end_date = utc_now()
        start_date = end_date - timedelta(days=days + 30)

        for symbol in self._config["bl_default_universe"]:
            try:
                data = await self.market_data_api.get_eod_prices(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                if data:
                    df = pd.DataFrame(data)
                    if 'date' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['date'])
                        df.set_index('timestamp', inplace=True)
                    close_col = 'adjClose' if 'adjClose' in df.columns else 'close'
                    prices_dict[symbol] = df[close_col]
                    logger.debug(f"获取 {symbol} 历史数据成功: {len(df)} 条")
                else:
                    logger.warning(f"No market data for {symbol}")
            except Exception as e:
                logger.warning(f"获取 {symbol} 历史数据失败: {e}")

        if not prices_dict:
            raise ValueError("无法获取任何历史价格数据")

        prices_df = pd.DataFrame(prices_dict)
        prices_df = prices_df.dropna(axis=1, how='all')
        prices_df = prices_df.ffill().bfill()

        self._cached_prices = prices_df
        return prices_df

    def _calculate_market_prior(
        self,
        prices: pd.DataFrame,
        market_weights: Dict[str, float] = None
    ) -> Tuple[pd.Series, pd.DataFrame]:
        """计算市场隐含先验收益"""
        cov_matrix = risk_models.sample_cov(prices)
        self._cached_cov = cov_matrix

        if market_weights is None:
            n_assets = len(prices.columns)
            market_weights = {col: 1.0 / n_assets for col in prices.columns}

        mkt_weights = pd.Series(market_weights)
        mkt_weights = mkt_weights.reindex(prices.columns).fillna(0)
        mkt_weights = mkt_weights / mkt_weights.sum()

        prior = market_implied_prior_returns(
            market_caps=mkt_weights,
            risk_aversion=self._config["bl_risk_aversion"],
            cov_matrix=cov_matrix
        )

        return prior, cov_matrix

    def _build_view_matrices(
        self,
        views: Dict[str, float],
        confidences: Dict[str, float],
        assets: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """构建 Black-Litterman 观点矩阵"""
        n_assets = len(assets)
        n_views = len(views)

        P = np.zeros((n_views, n_assets))
        Q = np.zeros(n_views)

        asset_to_idx = {asset: i for i, asset in enumerate(assets)}

        for i, (symbol, expected_return) in enumerate(views.items()):
            if symbol in asset_to_idx:
                P[i, asset_to_idx[symbol]] = 1.0
                Q[i] = expected_return

        base_variance = self._config.get("bl_base_variance", 0.05)
        omega_diag = []
        for symbol in views.keys():
            conf = confidences.get(symbol, 0.5)
            uncertainty = (1 - conf) * base_variance
            omega_diag.append(max(uncertainty, 0.001))

        omega = np.diag(omega_diag)

        return P, Q, omega

    async def _run_black_litterman(
        self,
        views: Dict[str, float],
        confidences: Dict[str, float]
    ) -> Dict[str, float]:
        """运行 Black-Litterman 模型，返回最优权重（0-1）"""
        step_id = self.emit_step("bl_optimization", "获取历史价格数据", "running")
        t0 = time.monotonic()

        prices = await self._fetch_historical_prices()
        available_assets = list(prices.columns)

        self.update_step(
            step_id, "completed",
            output_data=f"获取 {len(available_assets)} 个资产的历史数据",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        filtered_views = {k: v for k, v in views.items() if k in available_assets}
        filtered_conf = {k: v for k, v in confidences.items() if k in available_assets}

        if not filtered_views:
            logger.warning("没有有效观点，使用等权配置")
            n = len(available_assets)
            return {asset: 1.0 / n for asset in available_assets}

        step_id = self.emit_step("bl_optimization", "Black-Litterman 模型优化", "running")
        t0 = time.monotonic()

        prior, cov_matrix = self._calculate_market_prior(prices)

        P, Q, omega = self._build_view_matrices(
            filtered_views, filtered_conf, available_assets
        )

        bl = BlackLittermanModel(
            cov_matrix,
            pi=prior,
            P=P,
            Q=Q,
            omega=omega
        )

        posterior_returns = bl.bl_returns()

        ef = EfficientFrontier(posterior_returns, cov_matrix)
        ef.max_sharpe()
        weights = ef.clean_weights()
        weights_dict = dict(weights)

        self._last_optimization = {
            "prior_returns": prior.to_dict(),
            "posterior_returns": posterior_returns.to_dict(),
            "views": filtered_views,
            "weights": weights_dict,
            "timestamp": utc_now().isoformat()
        }

        # 格式化输出
        top_weights = sorted(weights_dict.items(), key=lambda x: -x[1])[:5]
        output_summary = ", ".join([f"{s}: {w*100:.1f}%" for s, w in top_weights])

        self.update_step(
            step_id, "completed",
            output_data=f"最优配置: {output_summary}",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        return weights_dict

    # ========== 主 Workflow ==========

    async def run_workflow(
        self,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        运行 Black-Litterman Workflow。

        注意：DB 持久化由 execute() 模板方法自动处理。
        """
        context = initial_context or {}
        trigger = context.get("trigger", "manual")

        # 初始化观点
        self._current_views = {}
        self._current_confidences = {}
        self._current_reasoning = ""

        # 1. LLM 分析生成观点（流式执行，自动 emit 每个步骤）
        user_message = context.get("user_message")
        recall_query = user_message or "Black-Litterman market views optimization"
        recalled = await self._recall_memories(query=recall_query, limit=10)

        # 如果是用户直接发消息（chat），使用用户消息作为主指令
        if user_message:
            user_prompt = user_message
        else:
            user_prompt = "请分析当前市场状况，生成投资观点。"

        if recalled:
            user_prompt = (
                f"**历史上下文摘要（你之前的分析和决策）：**\n"
                f"{recalled}\n\n---\n{user_prompt}"
            )

        agent_result = await self._run_agent(user_prompt)
        final_response = agent_result.text

        # 检查是否有观点
        if not self._current_views:
            self.emit_step("decision", "未生成有效观点", "failed", error="LLM 未调用 generate_investment_views 工具")
            return {
                "success": False,
                "error": "未生成投资观点",
                "workflow_type": self.get_workflow_type(),
                "llm_response": final_response,
            }

        # 2. 运行 Black-Litterman 优化
        optimal_weights = await self._run_black_litterman(
            self._current_views,
            self._current_confidences
        )

        # 发送优化结果
        weights_str = "\n".join([
            f"  • {sym}: {w * 100:.1f}%"
            for sym, w in sorted(optimal_weights.items(), key=lambda x: -x[1])
            if w >= self._config.get("bl_min_weight", 0.01)
        ])

        await self.message_manager.send_message(
            f"📊 **Black-Litterman 最优配置**\n\n{weights_str}",
            "info"
        )

        # 3. 执行再平衡
        step_id = self.emit_step("tool_call", "执行组合再平衡", "running")
        t0 = time.monotonic()
        trade_results = await self._execute_rebalance(optimal_weights)
        self.update_step(
            step_id, "completed",
            output_data=f"执行 {len(trade_results)} 笔交易",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        # 4. 更新 long-term memory
        step_id = self.emit_step("notification", "保存分析记忆", "running")
        t0 = time.monotonic()
        summary_context = (
            f"**本次 Black-Litterman 分析：**\n"
            f"- 时间: {format_for_display(utc_now())}\n"
            f"- 投资观点: {json.dumps(self._current_views, ensure_ascii=False)}\n"
            f"- 优化后权重: {json.dumps(optimal_weights, ensure_ascii=False)}\n"
            f"- 分析推理: {self._current_reasoning[:500]}\n"
        )
        summary = await self._generate_memory_summary(summary_context)
        if summary:
            await self._save_memory(summary, trigger, self.workflow_id)
        self.update_step(
            step_id, "completed",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

        return {
            "success": True,
            "workflow_type": self.get_workflow_type(),
            "trigger": trigger,
            "llm_response": final_response,
            "views": self._current_views,
            "optimal_weights": optimal_weights,
            "trades_executed": trade_results,
            "tool_calls": agent_result.tool_calls + ["black_litterman_optimization"],
        }

    async def _execute_rebalance(
        self,
        target_weights: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """
        执行 BL 优化后的组合再平衡。

        将 BL 权重（0-1）转为百分比（0-100），复用通用 rebalance 逻辑。
        """
        if not await self.is_market_open():
            await self.message_manager.send_message(
                "⚠️ 市场未开放，无法执行交易", "warning"
            )
            return []

        portfolio = await self.get_portfolio()
        if not portfolio:
            return []

        # 将权重 0-1 转为百分比 0-100，过滤掉低于 min_weight 的
        target_allocations = {
            symbol: weight * 100
            for symbol, weight in target_weights.items()
            if weight >= self._config.get("bl_min_weight", 0.01)
        }

        # 复用通用 rebalance 计算
        trades = await calculate_rebalance_trades(
            portfolio, target_allocations, self.market_data_api
        )

        if not trades:
            return []

        # 执行交易（先卖后买）
        return await execute_rebalance_trades(self.broker_api, trades)

    def get_optimization_result(self) -> Optional[Dict]:
        """获取最近一次优化结果"""
        return self._last_optimization
