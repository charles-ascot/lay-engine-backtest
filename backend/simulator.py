"""
CHIMERA Back-Test Workbench — Simulator
========================================
Orchestrator: load snapshot data → apply strategy → resolve results → compute P&L.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from gcs_reader import DataReader
from data_loader import MarketSnapshot, RunnerSnapshot, join_books_and_catalogue, is_main_race_market
from strategy_schema import Strategy
from strategy_engine import evaluate_strategy, EvaluationResult
from pnl import BetOutcome, calculate_bet_pnl, aggregate_pnl

logger = logging.getLogger("simulator")


@dataclass
class SimulationRequest:
    date: str
    strategy: Strategy
    market_ids: Optional[list[str]] = None  # None = all markets


@dataclass
class SimulationResult:
    date: str
    strategy_name: str
    markets_evaluated: int
    markets_with_bets: int
    bets_placed: int
    bet_outcomes: list[dict] = field(default_factory=list)
    evaluations: list[dict] = field(default_factory=list)
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "date": self.date,
            "strategy_name": self.strategy_name,
            "markets_evaluated": self.markets_evaluated,
            "markets_with_bets": self.markets_with_bets,
            "bets_placed": self.bets_placed,
            "bet_outcomes": self.bet_outcomes,
            "evaluations": self.evaluations,
            "summary": self.summary,
        }


class Simulator:
    def __init__(self, reader: DataReader):
        self.reader = reader

    def run(self, request: SimulationRequest) -> SimulationResult:
        """
        Full simulation flow:
        1. Load ALL snapshots for the date (chronologically ordered)
        2. Build per-market timeline
        3. For each market: find pre-race data + settled results
        4. Apply strategy, cross-reference with results, compute P&L
        """
        snapshots = self.reader.list_snapshots_for_date(request.date)

        if not snapshots:
            return SimulationResult(
                date=request.date,
                strategy_name=request.strategy.name,
                markets_evaluated=0,
                markets_with_bets=0,
                bets_placed=0,
                summary=aggregate_pnl([]),
            )

        # Load all snapshot data and build per-market timelines
        market_timelines: dict[str, list[tuple[str, MarketSnapshot]]] = {}

        for sp in snapshots:
            books = self.reader.read_ndjson(sp.books_path)
            cats = self.reader.read_ndjson(sp.catalogue_path)
            markets = join_books_and_catalogue(books, cats)

            for m in markets:
                if m.market_id not in market_timelines:
                    market_timelines[m.market_id] = []
                market_timelines[m.market_id].append((sp.timestamp, m))

        # Filter to main race WIN markets (exclude exotics)
        win_markets = {
            mid: timeline for mid, timeline in market_timelines.items()
            if any(
                m.number_of_winners == 1 and is_main_race_market(m.market_name, m.event_name)
                for _, m in timeline
            )
        }

        # Process each market
        all_outcomes: list[BetOutcome] = []
        all_evaluations: list[dict] = []
        markets_with_bets = 0

        for market_id, timeline in win_markets.items():
            if request.market_ids and market_id not in request.market_ids:
                continue

            # Find the last pre-race snapshot (OPEN, not inplay)
            pre_race = self._find_pre_race_snapshot(timeline)
            if pre_race is None:
                continue

            # Evaluate strategy
            eval_result = evaluate_strategy(request.strategy, pre_race)
            all_evaluations.append(eval_result.to_dict())

            if eval_result.skipped or not eval_result.instructions:
                continue

            markets_with_bets += 1

            # Find settled snapshot for results
            settled = self._find_settled_snapshot(timeline)
            runner_results = self._extract_runner_results(settled)

            # Calculate P&L for each bet
            for instruction in eval_result.instructions:
                runner_result = runner_results.get(
                    instruction.selection_id, "UNKNOWN"
                )
                profit = calculate_bet_pnl(instruction, runner_result)
                outcome = BetOutcome(
                    instruction=instruction,
                    runner_result=runner_result,
                    profit=profit,
                )
                all_outcomes.append(outcome)

        return SimulationResult(
            date=request.date,
            strategy_name=request.strategy.name,
            markets_evaluated=len(all_evaluations),
            markets_with_bets=markets_with_bets,
            bets_placed=len(all_outcomes),
            bet_outcomes=[o.to_dict() for o in all_outcomes],
            evaluations=all_evaluations,
            summary=aggregate_pnl(all_outcomes),
        )

    def _find_pre_race_snapshot(
        self, timeline: list[tuple[str, MarketSnapshot]]
    ) -> Optional[MarketSnapshot]:
        """Find the last snapshot where market is OPEN and not in-play."""
        for ts, market in reversed(timeline):
            if market.status == "OPEN" and not market.inplay:
                return market
        return None

    def _find_settled_snapshot(
        self, timeline: list[tuple[str, MarketSnapshot]]
    ) -> Optional[MarketSnapshot]:
        """Find a snapshot where runners have WINNER/LOSER status."""
        for ts, market in reversed(timeline):
            for r in market.runners:
                if r.status in ("WINNER", "LOSER"):
                    return market
        return None

    def _extract_runner_results(
        self, settled: Optional[MarketSnapshot]
    ) -> dict[int, str]:
        """Extract runner results from a settled market snapshot."""
        if settled is None:
            return {}
        return {
            r.selection_id: r.status
            for r in settled.runners
            if r.status in ("WINNER", "LOSER", "REMOVED")
        }
