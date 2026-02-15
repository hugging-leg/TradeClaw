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

import asyncio
import json
from typing import Dict, List, Any, Optional, Tuple
from datetime import timedelta

import numpy as np
import pandas as pd

from langchain_core.messages import HumanMessage, AIMessage
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

from config import settings

from src.utils.logging_config import get_logger
from src.agents.workflow_base import WorkflowBase
from src.agents.workflow_factory import register_workflow
from src.interfaces.broker_api import BrokerAPI
from src.interfaces.market_data_api import MarketDataAPI
from src.interfaces.news_api import NewsAPI
from src.messaging.message_manager import MessageManager
from src.utils.llm_utils import create_llm_client
from src.utils.db_utils import DB_AVAILABLE, get_trading_repository
from src.utils.timezone import utc_now, format_for_display
from src.agents.tools.registry import ToolRegistry
from src.agents.tools.common import create_common_tools
from src.agents.tools.trading_tools import execute_rebalance_trades

logger = get_logger(__name__)

# 尝试导入 pypfopt (包名是 pyportfolioopt)
try:
    from pypfopt import BlackLittermanModel, EfficientFrontier
    from pypfopt import risk_models
    from pypfopt.black_litterman import market_implied_prior_returns
    PYPFOPT_AVAILABLE = True
except ImportError:
    PYPFOPT_AVAILABLE = False
    logger.warning("pyportfolioopt 未安装。运行: pip install pyportfolioopt cvxpy")


@register_workflow(
    "black_litterman",
    description="Black-Litterman 量化组合优化",
    features=["📊 Black-Litterman 模型", "LLM 生成观点", "均值-方差优化"],
    best_for="量化 + AI 结合的科学配置"
)
class BlackLittermanWorkflow(WorkflowBase):
    """
    Black-Litterman 组合优化 Workflow

    核心流程:
    1. 获取资产池历史数据，计算协方差矩阵和市场均衡收益
    2. LLM 分析市场新闻和数据，生成投资观点 (Views)
    3. 使用 Black-Litterman 模型融合先验和观点
    4. 均值-方差优化得到最优权重
    5. 执行组合再平衡

    优势:
    - 量化模型 + AI 分析结合
    - 考虑风险和收益的数学优化
    - 观点可解释、可追溯
    """

    def __init__(
        self,
        broker_api: BrokerAPI = None,
        market_data_api: MarketDataAPI = None,
        news_api: NewsAPI = None,
        message_manager: MessageManager = None,
        universe: List[str] = None,
        risk_aversion: float = None,
        session_id: str = "bl_agent"
    ):
        """
        初始化 Black-Litterman Workflow

        Args:
            universe: 资产池列表
            risk_aversion: 风险厌恶系数 (delta)，默认从配置读取
            session_id: 会话 ID
        """
        super().__init__(broker_api, market_data_api, news_api, message_manager)

        if not PYPFOPT_AVAILABLE:
            raise ImportError(
                "pypfopt 未安装。请运行: pip install pypfopt cvxpy"
            )

        self.universe = universe or settings.get_bl_default_universe()
        self.risk_aversion = risk_aversion if risk_aversion is not None else settings.bl_risk_aversion
        self.session_id = session_id

        self.llm = create_llm_client()
        self.memory = MemorySaver()

        # BL 观点状态（供 analysis_tools 中的 generate_investment_views 写入）
        self._current_views: Dict[str, float] = {}
        self._current_confidences: Dict[str, float] = {}
        self._current_reasoning: str = ""

        # Tool Registry: 统一管理 tools 的启用/禁用
        self.tool_registry = ToolRegistry()
        self._register_tools()
        self.tools = self.tool_registry.get_enabled_tools()

        self.system_prompt = self._get_system_prompt()

        # 创建 Agent（system_prompt 在创建时注入）
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.memory,
        )

        # 状态
        self._db_available = DB_AVAILABLE
        self._cached_prices: Optional[pd.DataFrame] = None
        self._cached_cov: Optional[pd.DataFrame] = None
        self._last_optimization: Optional[Dict] = None
        
        # 历史摘要
        self.history_summary = ""

        logger.info(
            f"Black-Litterman Workflow 已初始化 "
            f"(资产池: {len(self.universe)} 个, 风险厌恶: {self.risk_aversion})"
        )

    def _get_system_prompt(self) -> str:
        return f"""你是一位专业的量化投资分析师，负责为 Black-Litterman 模型提供投资观点。

## 你的任务
1. 分析市场新闻、宏观经济数据和个股信息
2. 对资产池中的股票/ETF 形成投资观点
3. 为每个观点提供置信度评估

## 资产池
{', '.join(self.universe)}

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
使用 generate_investment_views 工具输出你的观点
"""

    def _register_tools(self) -> None:
        """注册所有 tools 到 ToolRegistry"""
        # create_common_tools 返回所有分类的 tools
        # 其中 analysis_tools 会检测 _current_views 属性并自动注册 generate_investment_views
        all_tools = create_common_tools(self)
        self.tool_registry.register_many(all_tools)

    def rebuild_agent(self) -> None:
        """当 tool 启用/禁用状态变更后，重新构建 agent"""
        self.tools = self.tool_registry.get_enabled_tools()
        self.agent = create_agent(
            self.llm,
            self.tools,
            system_prompt=self.system_prompt,
            checkpointer=self.memory,
        )
        logger.info(f"BL Agent rebuilt with {len(self.tools)} tools")

    # ========== 配置管理 ==========

    def get_config(self) -> Dict[str, Any]:
        config = super().get_config()
        config.update({
            "llm_model": settings.llm_model,
            "llm_recursion_limit": settings.llm_recursion_limit,
            "bl_risk_aversion": self.risk_aversion,
            "bl_historical_days": settings.bl_historical_days,
            "bl_base_variance": settings.bl_base_variance,
            "bl_min_weight": settings.bl_min_weight,
            "bl_default_universe": self.universe,
        })
        return config

    def update_config(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        # BL 特有参数
        if "bl_risk_aversion" in updates:
            self.risk_aversion = updates["bl_risk_aversion"]
        if "bl_default_universe" in updates:
            self.universe = updates["bl_default_universe"]
        for field in ("bl_historical_days", "bl_base_variance", "bl_min_weight"):
            if field in updates:
                setattr(settings, field, updates[field])

        # LLM 参数
        for field in ("llm_model", "llm_recursion_limit"):
            if field in updates:
                setattr(settings, field, updates[field])

        return super().update_config(updates)

    # ========== BL 模型核心逻辑 ==========

    async def _fetch_historical_prices(self, days: int = None) -> pd.DataFrame:
        """获取历史价格数据"""
        if days is None:
            days = settings.bl_historical_days
        prices_dict = {}
        end_date = utc_now()
        start_date = end_date - timedelta(days=days + 30)  # 多取 30 天以确保足够数据

        for symbol in self.universe:
            try:
                data = await self.market_data_api.get_eod_prices(
                    symbol=symbol,
                    start_date=start_date,
                    end_date=end_date
                )
                if data:
                    df = pd.DataFrame(data)
                    # Tiingo 返回的字段是 'date' 和 'adjClose'
                    if 'date' in df.columns:
                        df['timestamp'] = pd.to_datetime(df['date'])
                        df.set_index('timestamp', inplace=True)
                    # 优先使用调整后收盘价
                    close_col = 'adjClose' if 'adjClose' in df.columns else 'close'
                    prices_dict[symbol] = df[close_col]
                    logger.debug(f"获取 {symbol} 历史数据成功: {len(df)} 条")
                else:
                    logger.warning(f"No market data available for {symbol} (timeframe: 1Day, limit: {days})")
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
        """
        计算市场隐含先验收益

        Args:
            prices: 历史价格 DataFrame
            market_weights: 市场权重（可选，默认等权）

        Returns:
            (先验收益, 协方差矩阵)
        """
        # 计算协方差矩阵（年化）
        cov_matrix = risk_models.sample_cov(prices)
        self._cached_cov = cov_matrix

        # 如果没有提供市场权重，使用等权
        if market_weights is None:
            n_assets = len(prices.columns)
            market_weights = {col: 1.0 / n_assets for col in prices.columns}

        # 转换为 pandas Series
        mkt_weights = pd.Series(market_weights)
        mkt_weights = mkt_weights.reindex(prices.columns).fillna(0)
        mkt_weights = mkt_weights / mkt_weights.sum()

        # 计算市场隐含先验收益
        prior = market_implied_prior_returns(
            market_caps=mkt_weights,
            risk_aversion=self.risk_aversion,
            cov_matrix=cov_matrix
        )

        return prior, cov_matrix

    def _build_view_matrices(
        self,
        views: Dict[str, float],
        confidences: Dict[str, float],
        assets: List[str]
    ) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        构建 Black-Litterman 观点矩阵

        Args:
            views: 观点字典 {symbol: expected_return}
            confidences: 置信度字典 {symbol: confidence}
            assets: 资产列表

        Returns:
            (P矩阵, Q向量, omega矩阵)
        """
        n_assets = len(assets)
        n_views = len(views)

        P = np.zeros((n_views, n_assets))
        Q = np.zeros(n_views)

        asset_to_idx = {asset: i for i, asset in enumerate(assets)}

        for i, (symbol, expected_return) in enumerate(views.items()):
            if symbol in asset_to_idx:
                P[i, asset_to_idx[symbol]] = 1.0
                Q[i] = expected_return

        # Omega: 观点不确定性矩阵（对角矩阵）
        # 不确定性 = (1 - confidence) * 基础方差
        base_variance = settings.bl_base_variance
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
        """
        运行 Black-Litterman 模型

        Args:
            views: LLM 生成的投资观点
            confidences: 观点置信度

        Returns:
            最优组合权重
        """
        await self.message_manager.send_message(
            "🧮 运行 Black-Litterman 优化...", "info"
        )

        # 获取历史数据
        prices = await self._fetch_historical_prices()
        available_assets = list(prices.columns)

        # 过滤观点，只保留可用资产
        filtered_views = {k: v for k, v in views.items() if k in available_assets}
        filtered_conf = {k: v for k, v in confidences.items() if k in available_assets}

        if not filtered_views:
            logger.warning("没有有效观点，使用等权配置")
            n = len(available_assets)
            return {asset: 1.0 / n for asset in available_assets}

        # 计算先验
        prior, cov_matrix = self._calculate_market_prior(prices)

        # 构建观点矩阵
        P, Q, omega = self._build_view_matrices(
            filtered_views, filtered_conf, available_assets
        )

        # 运行 Black-Litterman
        bl = BlackLittermanModel(
            cov_matrix,
            pi=prior,
            P=P,
            Q=Q,
            omega=omega
        )

        # 获取后验收益
        posterior_returns = bl.bl_returns()

        # 均值-方差优化
        ef = EfficientFrontier(posterior_returns, cov_matrix)
        ef.max_sharpe()
        weights = ef.clean_weights()

        # 转换为字典
        weights_dict = dict(weights)

        self._last_optimization = {
            "prior_returns": prior.to_dict(),
            "posterior_returns": posterior_returns.to_dict(),
            "views": filtered_views,
            "weights": weights_dict,
            "timestamp": utc_now().isoformat()
        }

        return weights_dict

    async def _execute_bl_rebalance(
        self,
        target_weights: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """
        执行 BL 优化后的组合再平衡

        Args:
            target_weights: BL 模型输出的权重 {symbol: weight}（0-1）

        Returns:
            交易执行结果列表
        """
        # 检查市场状态
        if not await self.is_market_open():
            await self.message_manager.send_message(
                "⚠️ 市场未开放，无法执行交易", "warning"
            )
            return []

        portfolio = await self.get_portfolio()
        if not portfolio:
            return []

        equity = float(portfolio.equity)
        current_positions = {
            pos.symbol: float(pos.market_value) / equity
            for pos in portfolio.positions
            if pos.quantity != 0
        }

        weight_diff_threshold = settings.rebalance_weight_diff_threshold

        # 计算需要的交易
        trades: List[Dict[str, Any]] = []
        for symbol, target_weight in target_weights.items():
            if target_weight < settings.bl_min_weight:
                continue

            current_weight = current_positions.get(symbol, 0)
            weight_diff = target_weight - current_weight

            if abs(weight_diff) < weight_diff_threshold:
                continue

            target_value = equity * target_weight
            current_value = equity * current_weight
            value_diff = target_value - current_value

            try:
                price_data = await self.market_data_api.get_latest_price(symbol)
                if price_data:
                    price = float(price_data['close'])
                    shares = int(value_diff / price)
                    if abs(shares) >= 1:
                        trades.append({
                            'symbol': symbol,
                            'action': 'BUY' if shares > 0 else 'SELL',
                            'shares': abs(shares),
                            'price': price,
                            'target_weight': target_weight,
                            'current_weight': current_weight,
                        })
            except Exception as e:
                logger.warning(f"获取 {symbol} 价格失败: {e}")

        # 清仓不在目标中的持仓
        for symbol, current_weight in current_positions.items():
            if symbol not in target_weights and current_weight > settings.bl_min_weight:
                for pos in portfolio.positions:
                    if pos.symbol == symbol and pos.quantity > 0:
                        trades.append({
                            'symbol': symbol,
                            'action': 'SELL',
                            'shares': int(pos.quantity),
                            'price': 0,
                            'target_weight': 0,
                            'current_weight': current_weight,
                        })

        # 使用通用交易执行（先卖后买）
        return await execute_rebalance_trades(self.broker_api, trades)

    # ========== 历史摘要 ==========

    async def _update_history_summary(
        self, 
        views: Dict[str, float], 
        weights: Dict[str, float],
        reasoning: str
    ):
        """更新历史摘要"""
        try:
            summary_prompt = f"""请将以下内容整合为简洁的投资历史摘要（限制500字）：

**之前的历史摘要：**
{self.history_summary if self.history_summary else "无（首次分析）"}

**本次 Black-Litterman 分析：**
- 时间: {format_for_display(utc_now())}
- 投资观点: {json.dumps(views, ensure_ascii=False) if views else '无'}
- 优化后权重: {json.dumps(weights, ensure_ascii=False) if weights else '无'}
- 分析推理: {reasoning[:500] if reasoning else '无'}

请生成更新后的摘要，重点保留：
1. 最近形成的投资观点及依据
2. 优化后的资产配置
3. 市场判断和风险评估
4. 值得关注的变化

只输出摘要内容。"""

            response = await asyncio.to_thread(
                lambda: self.llm.invoke(summary_prompt).content
            )
            self.history_summary = response.strip()[:2000]
            logger.debug(f"历史摘要已更新: {len(self.history_summary)} 字符")
        except Exception as e:
            logger.warning(f"更新历史摘要失败: {e}")

    # ========== 主 Workflow ==========

    async def run_workflow(
        self,
        initial_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        运行 Black-Litterman Workflow

        流程:
        1. LLM 分析市场生成观点
        2. Black-Litterman 模型优化
        3. 执行再平衡
        """
        try:
            self.workflow_id = self._generate_workflow_id()
            self.start_time = utc_now()

            context = initial_context or {}
            trigger = context.get("trigger", "manual")

            await self.send_workflow_start_notification("Black-Litterman")

            # 初始化观点
            self._current_views = {}
            self._current_confidences = {}
            self._current_reasoning = ""

            # 1. LLM 分析生成观点
            await self.message_manager.send_message(
                "🤖 LLM 分析市场并生成投资观点...", "info"
            )

            # 每次分析使用独立的 thread_id，避免历史消息累积
            unique_thread_id = f"{self.session_id}_{self.workflow_id}"
            config = {
                "configurable": {"thread_id": unique_thread_id},
                "recursion_limit": settings.llm_recursion_limit
            }

            # 构建包含历史摘要的 prompt
            user_prompt = "请分析当前市场状况，生成投资观点。"
            if self.history_summary:
                user_prompt = f"""**历史上下文摘要（你之前的分析）：**
{self.history_summary}

---
{user_prompt}"""

            result = await self.agent.ainvoke(
                {"messages": [HumanMessage(content=user_prompt)]},
                config=config,
            )

            # 提取 LLM 响应
            messages = result.get("messages", [])
            final_response = ""
            for msg in messages:
                if isinstance(msg, AIMessage) and msg.content:
                    final_response = msg.content

            # 检查是否有观点
            if not self._current_views:
                await self.message_manager.send_message(
                    "⚠️ LLM 未生成有效观点", "warning"
                )
                return {
                    "success": False,
                    "error": "未生成投资观点",
                    "workflow_type": "black_litterman"
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
                if w >= settings.bl_min_weight
            ])

            await self.message_manager.send_message(
                f"📊 **Black-Litterman 最优配置**\n\n{weights_str}",
                "info"
            )

            # 3. 执行再平衡
            trade_results = await self._execute_bl_rebalance(optimal_weights)

            # 计算执行时间
            self.end_time = utc_now()
            execution_time = (self.end_time - self.start_time).total_seconds()

            # 保存到数据库
            if self._db_available:
                try:
                    TradingRepository = get_trading_repository()
                    if TradingRepository:
                        await TradingRepository.save_analysis(
                            trigger=trigger,
                            workflow_id=self.workflow_id,
                            analysis_type="black_litterman",
                            input_context=context,
                            output_response=final_response,
                            tool_calls=["black_litterman_optimization"],
                            trades_executed=trade_results,
                            execution_time_seconds=execution_time,
                            success=True
                        )
                except Exception as e:
                    logger.warning(f"保存分析历史失败: {e}")

            # 更新历史摘要
            await self._update_history_summary(
                self._current_views or {},
                optimal_weights or {},
                self._current_reasoning
            )

            await self.send_workflow_complete_notification(
                "Black-Litterman", execution_time
            )

            return {
                "success": True,
                "workflow_type": "black_litterman",
                "workflow_id": self.workflow_id,
                "trigger": trigger,
                "views": self._current_views,
                "optimal_weights": optimal_weights,
                "trades_executed": trade_results,
                "execution_time": execution_time
            }

        except Exception as e:
            logger.error(f"Black-Litterman Workflow 错误: {e}")
            return await self._handle_workflow_error(e, "Black-Litterman")

    def get_optimization_result(self) -> Optional[Dict]:
        """获取最近一次优化结果"""
        return self._last_optimization
