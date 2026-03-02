"""
Risk Rules API

Provides CRUD operations for risk rules.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from agent_trader.api.deps import get_trading_system
from agent_trader.config.risk_rules import get_risk_rules_manager
from agent_trader.trading_system import TradingSystem

router = APIRouter(prefix="/risk", tags=["risk"])


# ------------------------------------------------------------------
# Request / Response models
# ------------------------------------------------------------------

class RuleCreateRequest(BaseModel):
    name: str
    type: str
    enabled: bool = True
    priority: int = 100
    threshold: float
    action: str = "close"
    reduce_ratio: float = 0.5
    symbols: list[str] | None = None
    cooldown_seconds: int = 0
    description: str | None = None


class RuleUpdateRequest(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    threshold: float | None = None
    action: str | None = None
    reduce_ratio: float | None = None
    symbols: list[str] | None = None
    cooldown_seconds: int | None = None
    description: str | None = None


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@router.get("/rules")
async def get_rules() -> List[Dict[str, Any]]:
    """Get all risk rules."""
    mgr = get_risk_rules_manager()
    return mgr.get_rules()


@router.post("/rules")
async def create_rule(req: RuleCreateRequest) -> Dict[str, Any]:
    """Create a new risk rule."""
    mgr = get_risk_rules_manager()
    try:
        rule = mgr.add_rule(req.model_dump(exclude_none=True))
        return rule.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/rules")
async def replace_all_rules(
    rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Replace all risk rules."""
    mgr = get_risk_rules_manager()
    try:
        updated = mgr.replace_all(rules)
        return {"success": True, "count": len(updated)}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/rules/{name}")
async def update_rule(
    name: str,
    req: RuleUpdateRequest,
) -> Dict[str, Any]:
    """Update a specific risk rule."""
    mgr = get_risk_rules_manager()
    updates = req.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        rule = mgr.update_rule(name, updates)
        return rule.model_dump(mode="json")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/rules/{name}")
async def delete_rule(name: str) -> Dict[str, Any]:
    """Delete a specific risk rule."""
    mgr = get_risk_rules_manager()
    if mgr.delete_rule(name):
        return {"success": True, "deleted": name}
    raise HTTPException(status_code=404, detail=f"Rule '{name}' not found")


@router.get("/summary")
async def get_risk_summary(
    ts: TradingSystem = Depends(get_trading_system),
) -> Dict[str, Any]:
    """Get risk management summary."""
    if not ts.risk_manager:
        return {"enabled": False}
    return {
        "enabled": True,
        **ts.risk_manager.get_risk_summary(),
        "rules": get_risk_rules_manager().get_rules(),
    }
