"""
CHIMERA Back-Test Workbench — P&L Calculation
===============================================
Calculate profit/loss for individual bets and aggregate across simulation runs.
"""

from dataclasses import dataclass
from strategy_engine import BetInstruction


@dataclass
class BetOutcome:
    """A bet with its result and P&L."""
    instruction: BetInstruction
    runner_result: str  # "WINNER", "LOSER", "REMOVED", "UNKNOWN"
    profit: float       # positive = we won, negative = we lost

    def to_dict(self) -> dict:
        return {
            **self.instruction.to_dict(),
            "runner_result": self.runner_result,
            "profit": self.profit,
        }


def calculate_bet_pnl(instruction: BetInstruction, runner_result: str) -> float:
    """
    Calculate P&L for a single bet.

    LAY bets:
      Horse LOSES → profit = +stake (we keep the backer's money)
      Horse WINS  → loss = -liability = -(stake × (odds - 1))
      REMOVED     → void (£0)

    BACK bets:
      Horse WINS  → profit = stake × (odds - 1)
      Horse LOSES → loss = -stake
      REMOVED     → void (£0)
    """
    if runner_result == "REMOVED":
        return 0.0

    if instruction.bet_type == "LAY":
        if runner_result == "LOSER":
            return instruction.stake
        elif runner_result == "WINNER":
            return -instruction.liability
        return 0.0

    elif instruction.bet_type == "BACK":
        if runner_result == "WINNER":
            return round(instruction.stake * (instruction.price - 1), 2)
        elif runner_result == "LOSER":
            return -instruction.stake
        return 0.0

    return 0.0


def aggregate_pnl(outcomes: list[BetOutcome]) -> dict:
    """Compute summary statistics across all bet outcomes."""
    if not outcomes:
        return {
            "total_pnl": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "void_count": 0,
            "total_stake": 0.0,
            "total_liability": 0.0,
            "roi_percent": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
        }

    wins = [o for o in outcomes if o.profit > 0]
    losses = [o for o in outcomes if o.profit < 0]
    voids = [o for o in outcomes if o.profit == 0]

    total_pnl = sum(o.profit for o in outcomes)
    total_liability = sum(o.instruction.liability for o in outcomes)

    return {
        "total_pnl": round(total_pnl, 2),
        "win_count": len(wins),
        "loss_count": len(losses),
        "void_count": len(voids),
        "total_stake": round(sum(o.instruction.stake for o in outcomes), 2),
        "total_liability": round(total_liability, 2),
        "roi_percent": round(
            (total_pnl / total_liability * 100), 2
        ) if total_liability > 0 else 0.0,
        "avg_win": round(
            sum(o.profit for o in wins) / len(wins), 2
        ) if wins else 0.0,
        "avg_loss": round(
            sum(o.profit for o in losses) / len(losses), 2
        ) if losses else 0.0,
    }
