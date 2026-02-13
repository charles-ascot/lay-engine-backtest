"""
CHIMERA Back-Test Workbench — Strategy Schema
===============================================
Pydantic models for JSON strategy definitions.
Rules are structured data, not code — enabling visual editing and export.
"""

from enum import Enum
from typing import Optional, Literal, Union
from pydantic import BaseModel


class ComparisonOperator(str, Enum):
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    EQ = "eq"
    NEQ = "neq"
    BETWEEN = "between"


class RunnerTarget(str, Enum):
    FAVOURITE = "favourite"
    SECOND_FAVOURITE = "second_favourite"
    THIRD_FAVOURITE = "third_favourite"


class FieldRef(str, Enum):
    FAV_LAY_ODDS = "fav_lay_odds"
    FAV_BACK_ODDS = "fav_back_odds"
    SECOND_FAV_LAY_ODDS = "second_fav_lay_odds"
    SECOND_FAV_BACK_ODDS = "second_fav_back_odds"
    GAP_TO_SECOND = "gap_to_second"
    RUNNER_COUNT = "runner_count"
    TOTAL_MATCHED = "total_matched"
    FAV_TOTAL_MATCHED = "fav_total_matched"


class Condition(BaseModel):
    field: FieldRef
    operator: ComparisonOperator
    value: Union[float, str, bool]
    value_high: Optional[float] = None  # for BETWEEN operator


class BetAction(BaseModel):
    target: RunnerTarget
    bet_type: Literal["LAY", "BACK"] = "LAY"
    stake: float


class Rule(BaseModel):
    id: str
    name: str
    priority: int
    conditions: list[Condition]
    actions: list[BetAction]
    stop_on_match: bool = True


class MarketFilter(BaseModel):
    countries: list[str] = ["GB", "IE"]
    min_runners: int = 2
    max_runners: Optional[int] = None
    exclude_inplay: bool = True
    market_types: list[str] = []  # e.g. ["WIN"] — empty means all
    venue_contains: list[str] = []
    venue_excludes: list[str] = []


class Strategy(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = "1.0"
    rules: list[Rule]
    market_filters: Optional[MarketFilter] = None
