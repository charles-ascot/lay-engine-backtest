"""
CHIMERA Back-Test Workbench — Strategy Engine
===============================================
Runtime interpreter that evaluates JSON strategy definitions against market data.
Designed to be dependency-free (no GCS, no FastAPI) so it can be copied
into the live engine as a drop-in replacement for rules.py.
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from strategy_schema import (
    Strategy, Rule, Condition, BetAction,
    FieldRef, ComparisonOperator, RunnerTarget, MarketFilter,
)
from data_loader import MarketSnapshot, RunnerSnapshot


@dataclass
class BetInstruction:
    """A specific bet to place, output of strategy evaluation."""
    market_id: str
    selection_id: int
    runner_name: str
    bet_type: str       # "LAY" or "BACK"
    price: float        # the odds
    stake: float        # the size
    rule_id: str
    rule_name: str

    @property
    def liability(self) -> float:
        if self.bet_type == "LAY":
            return round(self.stake * (self.price - 1), 2)
        return self.stake

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "selection_id": self.selection_id,
            "runner_name": self.runner_name,
            "bet_type": self.bet_type,
            "price": self.price,
            "stake": self.stake,
            "liability": self.liability,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
        }


@dataclass
class EvaluationResult:
    """Output of evaluating a strategy against a market."""
    market_id: str
    market_name: str
    venue: str
    market_start_time: str
    instructions: list[BetInstruction] = field(default_factory=list)
    matched_rule_id: Optional[str] = None
    matched_rule_name: Optional[str] = None
    favourite: Optional[dict] = None
    second_favourite: Optional[dict] = None
    skipped: bool = False
    skip_reason: str = ""

    def to_dict(self) -> dict:
        return {
            "market_id": self.market_id,
            "market_name": self.market_name,
            "venue": self.venue,
            "market_start_time": self.market_start_time,
            "instructions": [i.to_dict() for i in self.instructions],
            "matched_rule_id": self.matched_rule_id,
            "matched_rule_name": self.matched_rule_name,
            "favourite": self.favourite,
            "second_favourite": self.second_favourite,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "total_stake": sum(i.stake for i in self.instructions),
            "total_liability": sum(i.liability for i in self.instructions),
        }


def _get_sorted_active_runners(market: MarketSnapshot) -> list[RunnerSnapshot]:
    """Get active runners sorted by best available to lay (lowest first = favourite)."""
    active = [
        r for r in market.runners
        if r.status == "ACTIVE" and r.best_available_to_lay is not None
    ]
    active.sort(key=lambda r: r.best_available_to_lay)
    return active


def resolve_field(field_ref: FieldRef, market: MarketSnapshot) -> Optional[float]:
    """Extract a field value from a market snapshot for condition evaluation."""
    active = _get_sorted_active_runners(market)
    fav = active[0] if len(active) >= 1 else None
    second_fav = active[1] if len(active) >= 2 else None

    if field_ref == FieldRef.FAV_LAY_ODDS:
        return fav.best_available_to_lay if fav else None
    elif field_ref == FieldRef.FAV_BACK_ODDS:
        return fav.best_available_to_back if fav else None
    elif field_ref == FieldRef.SECOND_FAV_LAY_ODDS:
        return second_fav.best_available_to_lay if second_fav else None
    elif field_ref == FieldRef.SECOND_FAV_BACK_ODDS:
        return second_fav.best_available_to_back if second_fav else None
    elif field_ref == FieldRef.GAP_TO_SECOND:
        if fav and second_fav:
            return second_fav.best_available_to_lay - fav.best_available_to_lay
        return None
    elif field_ref == FieldRef.RUNNER_COUNT:
        return float(len(active))
    elif field_ref == FieldRef.TOTAL_MATCHED:
        return market.total_matched
    elif field_ref == FieldRef.FAV_TOTAL_MATCHED:
        return fav.total_matched if fav else None

    return None


def evaluate_condition(condition: Condition, market: MarketSnapshot) -> bool:
    """Evaluate a single condition against a market."""
    actual = resolve_field(condition.field, market)
    if actual is None:
        return False

    value = float(condition.value)

    if condition.operator == ComparisonOperator.LT:
        return actual < value
    elif condition.operator == ComparisonOperator.LTE:
        return actual <= value
    elif condition.operator == ComparisonOperator.GT:
        return actual > value
    elif condition.operator == ComparisonOperator.GTE:
        return actual >= value
    elif condition.operator == ComparisonOperator.EQ:
        return actual == value
    elif condition.operator == ComparisonOperator.NEQ:
        return actual != value
    elif condition.operator == ComparisonOperator.BETWEEN:
        high = float(condition.value_high) if condition.value_high is not None else value
        return value <= actual <= high

    return False


def resolve_target(
    target: RunnerTarget, market: MarketSnapshot
) -> list[RunnerSnapshot]:
    """Resolve a runner target to actual runner(s)."""
    active = _get_sorted_active_runners(market)

    if target == RunnerTarget.FAVOURITE:
        return [active[0]] if len(active) >= 1 else []
    elif target == RunnerTarget.SECOND_FAVOURITE:
        return [active[1]] if len(active) >= 2 else []
    elif target == RunnerTarget.THIRD_FAVOURITE:
        return [active[2]] if len(active) >= 3 else []

    return []


def _check_market_filters(
    filters: Optional[MarketFilter], market: MarketSnapshot
) -> Optional[str]:
    """
    Check if a market passes the strategy filters.
    Returns None if it passes, or a skip reason string if it doesn't.
    """
    if filters is None:
        return None

    if filters.exclude_inplay and market.inplay:
        return "In-play market excluded"

    active_count = len(_get_sorted_active_runners(market))
    if active_count < filters.min_runners:
        return f"Only {active_count} active runners (min: {filters.min_runners})"

    if filters.max_runners and active_count > filters.max_runners:
        return f"{active_count} runners exceeds max ({filters.max_runners})"

    if filters.countries and market.event_country not in filters.countries:
        return f"Country {market.event_country} not in {filters.countries}"

    if filters.venue_excludes:
        for pattern in filters.venue_excludes:
            if pattern.lower() in market.venue.lower():
                return f"Venue '{market.venue}' excluded by filter '{pattern}'"

    return None


def evaluate_strategy(
    strategy: Strategy, market: MarketSnapshot
) -> EvaluationResult:
    """
    Evaluate a full strategy against a market snapshot.
    Rules are sorted by priority and evaluated in order.
    For each rule, ALL conditions must be true (AND).
    If a rule matches and stop_on_match=True, skip remaining rules.
    """
    result = EvaluationResult(
        market_id=market.market_id,
        market_name=market.market_name,
        venue=market.venue,
        market_start_time=market.market_start_time,
    )

    # Set favourite info for display
    active = _get_sorted_active_runners(market)
    if len(active) >= 1:
        fav = active[0]
        result.favourite = {
            "name": fav.runner_name,
            "odds": fav.best_available_to_lay,
            "selection_id": fav.selection_id,
        }
    if len(active) >= 2:
        sf = active[1]
        result.second_favourite = {
            "name": sf.runner_name,
            "odds": sf.best_available_to_lay,
            "selection_id": sf.selection_id,
        }

    # Check market filters
    skip_reason = _check_market_filters(strategy.market_filters, market)
    if skip_reason:
        result.skipped = True
        result.skip_reason = skip_reason
        return result

    # Evaluate rules in priority order
    sorted_rules = sorted(strategy.rules, key=lambda r: r.priority)

    for rule in sorted_rules:
        all_conditions_met = all(
            evaluate_condition(c, market) for c in rule.conditions
        )
        if not all_conditions_met:
            continue

        # Rule matched — generate bet instructions
        for action in rule.actions:
            target_runners = resolve_target(action.target, market)
            for runner in target_runners:
                price = (
                    runner.best_available_to_lay
                    if action.bet_type == "LAY"
                    else runner.best_available_to_back
                )
                if price is None:
                    continue

                result.instructions.append(BetInstruction(
                    market_id=market.market_id,
                    selection_id=runner.selection_id,
                    runner_name=runner.runner_name,
                    bet_type=action.bet_type,
                    price=price,
                    stake=action.stake,
                    rule_id=rule.id,
                    rule_name=rule.name,
                ))

        result.matched_rule_id = rule.id
        result.matched_rule_name = rule.name

        if rule.stop_on_match:
            return result

    if not result.instructions:
        result.skipped = True
        result.skip_reason = "No rules matched"

    return result
