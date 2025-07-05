import asyncio
import schedule
import logging
import time
from datetime import datetime, time as datetime_time, timedelta
from typing import Optional, Callable, Dict, Any
from threading import Thread
import pytz
from config import settings


logger = logging.getLogger(__name__)


class TradingScheduler:
    """Scheduler for trading operations and market events"""
    
    def __init__(self, trading_system=None):
        self.trading_system = trading_system
        self.is_running = False
        self.scheduler_thread = None
        self.timezone = pytz.timezone('US/Eastern')  # Market timezone
        self.scheduled_jobs = {}
        
    def set_trading_system(self, trading_system):
        """Set the trading system reference"""
        self.trading_system = trading_system
    
    def start(self):
        """Start the scheduler"""
        if self.is_running:
            logger.warning("Scheduler is already running")
            return
        
        self.is_running = True
        self._setup_default_schedule()
        
        # Start scheduler in a separate thread
        self.scheduler_thread = Thread(target=self._run_scheduler, daemon=True)
        self.scheduler_thread.start()
        
        logger.info("Trading scheduler started")
    
    def stop(self):
        """Stop the scheduler"""
        self.is_running = False
        schedule.clear()
        
        if self.scheduler_thread and self.scheduler_thread.is_alive():
            self.scheduler_thread.join(timeout=5)
        
        logger.info("Trading scheduler stopped")
    
    def _setup_default_schedule(self):
        """Setup default scheduled jobs"""
        
        # Daily rebalancing at market open
        rebalance_time = settings.rebalance_time
        schedule.every().monday.at(rebalance_time).do(self._safe_run_async, self._daily_rebalance)
        schedule.every().tuesday.at(rebalance_time).do(self._safe_run_async, self._daily_rebalance)
        schedule.every().wednesday.at(rebalance_time).do(self._safe_run_async, self._daily_rebalance)
        schedule.every().thursday.at(rebalance_time).do(self._safe_run_async, self._daily_rebalance)
        schedule.every().friday.at(rebalance_time).do(self._safe_run_async, self._daily_rebalance)
        
        # Portfolio monitoring every hour during market hours
        for hour in range(9, 16):  # 9 AM to 4 PM ET
            schedule.every().monday.at(f"{hour:02d}:30").do(self._safe_run_async, self._portfolio_check)
            schedule.every().tuesday.at(f"{hour:02d}:30").do(self._safe_run_async, self._portfolio_check)
            schedule.every().wednesday.at(f"{hour:02d}:30").do(self._safe_run_async, self._portfolio_check)
            schedule.every().thursday.at(f"{hour:02d}:30").do(self._safe_run_async, self._portfolio_check)
            schedule.every().friday.at(f"{hour:02d}:30").do(self._safe_run_async, self._portfolio_check)
        
        # Market close analysis
        schedule.every().monday.at("16:05").do(self._safe_run_async, self._market_close_analysis)
        schedule.every().tuesday.at("16:05").do(self._safe_run_async, self._market_close_analysis)
        schedule.every().wednesday.at("16:05").do(self._safe_run_async, self._market_close_analysis)
        schedule.every().thursday.at("16:05").do(self._safe_run_async, self._market_close_analysis)
        schedule.every().friday.at("16:05").do(self._safe_run_async, self._market_close_analysis)
        
        # Risk management check every 15 minutes during market hours
        for hour in range(9, 16):
            for minute in [0, 15, 30, 45]:
                time_str = f"{hour:02d}:{minute:02d}"
                schedule.every().monday.at(time_str).do(self._safe_run_async, self._risk_check)
                schedule.every().tuesday.at(time_str).do(self._safe_run_async, self._risk_check)
                schedule.every().wednesday.at(time_str).do(self._safe_run_async, self._risk_check)
                schedule.every().thursday.at(time_str).do(self._safe_run_async, self._risk_check)
                schedule.every().friday.at(time_str).do(self._safe_run_async, self._risk_check)
        
        # Daily cleanup at midnight
        schedule.every().day.at("00:00").do(self._safe_run_async, self._daily_cleanup)
        
        logger.info("Default schedule configured")
    
    def _run_scheduler(self):
        """Run the scheduler loop"""
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                time.sleep(5)
    
    def _safe_run_async(self, async_func):
        """Safely run async function in scheduler"""
        try:
            # Create new event loop for this thread if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            if loop.is_running():
                # If loop is already running, create a task
                asyncio.create_task(async_func())
            else:
                # Run the async function
                loop.run_until_complete(async_func())
                
        except Exception as e:
            logger.error(f"Error running scheduled task: {e}")
    
    async def _daily_rebalance(self):
        """Daily portfolio rebalancing"""
        try:
            logger.info("Starting daily rebalancing")
            
            if not self.trading_system:
                logger.error("Trading system not available for rebalancing")
                return
            
            # Check if market is open
            if not await self.trading_system.is_market_open():
                logger.info("Market is closed, skipping rebalancing")
                return
            
            # Run the trading workflow
            await self.trading_system.run_daily_rebalance()
            
            logger.info("Daily rebalancing completed")
            
        except Exception as e:
            logger.error(f"Error in daily rebalancing: {e}")
    
    async def _portfolio_check(self):
        """Periodic portfolio monitoring"""
        try:
            logger.debug("Running portfolio check")
            
            if not self.trading_system:
                return
            
            # Check if market is open
            if not await self.trading_system.is_market_open():
                return
            
            # Get current portfolio
            portfolio = await self.trading_system.get_portfolio()
            
            # Check for significant changes
            if self._should_alert_portfolio_change(portfolio):
                await self.trading_system.send_portfolio_alert(portfolio)
            
        except Exception as e:
            logger.error(f"Error in portfolio check: {e}")
    
    async def _market_close_analysis(self):
        """Market close analysis and reporting"""
        try:
            logger.info("Running market close analysis")
            
            if not self.trading_system:
                return
            
            # Run end-of-day analysis
            await self.trading_system.run_eod_analysis()
            
            logger.info("Market close analysis completed")
            
        except Exception as e:
            logger.error(f"Error in market close analysis: {e}")
    
    async def _risk_check(self):
        """Risk management check"""
        try:
            logger.debug("Running risk check")
            
            if not self.trading_system:
                return
            
            # Check if market is open
            if not await self.trading_system.is_market_open():
                return
            
            # Run risk management checks
            await self.trading_system.run_risk_checks()
            
        except Exception as e:
            logger.error(f"Error in risk check: {e}")
    
    async def _daily_cleanup(self):
        """Daily cleanup tasks"""
        try:
            logger.info("Running daily cleanup")
            
            if not self.trading_system:
                return
            
            # Cleanup old data, logs, etc.
            await self.trading_system.cleanup_old_data()
            
            logger.info("Daily cleanup completed")
            
        except Exception as e:
            logger.error(f"Error in daily cleanup: {e}")
    
    def _should_alert_portfolio_change(self, portfolio) -> bool:
        """Check if portfolio change warrants an alert"""
        # This is a simplified check - in practice you'd want more sophisticated logic
        try:
            # Alert if day P&L is more than 5% of equity
            if abs(portfolio.day_pnl) > (portfolio.equity * 0.05):
                return True
            
            # Alert if any position has large unrealized loss
            for position in portfolio.positions:
                if position.unrealized_pnl_percentage < -0.1:  # More than 10% loss
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error checking portfolio change: {e}")
            return False
    
    def add_custom_job(self, job_id: str, schedule_time: str, job_func: Callable, 
                      days: list = None, **kwargs):
        """Add a custom scheduled job"""
        try:
            if days is None:
                days = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday']
            
            # Remove existing job if it exists
            if job_id in self.scheduled_jobs:
                self.remove_custom_job(job_id)
            
            jobs = []
            for day in days:
                if asyncio.iscoroutinefunction(job_func):
                    job = getattr(schedule.every(), day.lower()).at(schedule_time).do(
                        self._safe_run_async, lambda: job_func(**kwargs)
                    )
                else:
                    job = getattr(schedule.every(), day.lower()).at(schedule_time).do(
                        job_func, **kwargs
                    )
                jobs.append(job)
            
            self.scheduled_jobs[job_id] = jobs
            logger.info(f"Added custom job: {job_id} at {schedule_time} on {days}")
            
        except Exception as e:
            logger.error(f"Error adding custom job {job_id}: {e}")
    
    def remove_custom_job(self, job_id: str):
        """Remove a custom scheduled job"""
        try:
            if job_id in self.scheduled_jobs:
                for job in self.scheduled_jobs[job_id]:
                    schedule.cancel_job(job)
                del self.scheduled_jobs[job_id]
                logger.info(f"Removed custom job: {job_id}")
            else:
                logger.warning(f"Job {job_id} not found")
                
        except Exception as e:
            logger.error(f"Error removing custom job {job_id}: {e}")
    
    def get_next_run_time(self, job_id: str = None) -> Optional[datetime]:
        """Get the next run time for a job or all jobs"""
        try:
            if job_id and job_id in self.scheduled_jobs:
                jobs = self.scheduled_jobs[job_id]
                if jobs:
                    return jobs[0].next_run
            else:
                # Return next run time for any job
                next_run = None
                for job in schedule.jobs:
                    if next_run is None or job.next_run < next_run:
                        next_run = job.next_run
                return next_run
                
        except Exception as e:
            logger.error(f"Error getting next run time: {e}")
            return None
    
    def get_schedule_status(self) -> Dict[str, Any]:
        """Get current schedule status"""
        try:
            current_time = datetime.now(self.timezone)
            
            status = {
                "is_running": self.is_running,
                "current_time": current_time.isoformat(),
                "timezone": str(self.timezone),
                "total_jobs": len(schedule.jobs),
                "custom_jobs": len(self.scheduled_jobs),
                "next_run": None
            }
            
            # Get next run time
            next_run = self.get_next_run_time()
            if next_run:
                status["next_run"] = next_run.isoformat()
                status["next_run_in"] = str(next_run - current_time.replace(tzinfo=None))
            
            return status
            
        except Exception as e:
            logger.error(f"Error getting schedule status: {e}")
            return {"error": str(e)}
    
    def is_market_hours(self) -> bool:
        """Check if current time is within market hours"""
        try:
            current_time = datetime.now(self.timezone)
            current_weekday = current_time.weekday()
            
            # Market is closed on weekends
            if current_weekday >= 5:  # Saturday = 5, Sunday = 6
                return False
            
            # Market hours: 9:30 AM - 4:00 PM ET
            market_open = current_time.replace(hour=9, minute=30, second=0, microsecond=0)
            market_close = current_time.replace(hour=16, minute=0, second=0, microsecond=0)
            
            return market_open <= current_time <= market_close
            
        except Exception as e:
            logger.error(f"Error checking market hours: {e}")
            return False 