"""
CHIMERA Back-Test Workbench — Data Loader
==========================================
Parse NDJSON files and join books + catalogue data into MarketSnapshot objects.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class RunnerSnapshot:
    """A runner at a point in time with price and metadata."""
    selection_id: int
    runner_name: str
    handicap: float = 0.0
    status: str = "ACTIVE"
    best_available_to_lay: Optional[float] = None
    best_available_to_back: Optional[float] = None
    lay_depth: list = field(default_factory=list)
    back_depth: list = field(default_factory=list)
    last_price_traded: Optional[float] = None
    total_matched: float = 0.0


@dataclass
class MarketSnapshot:
    """A single market at a point in time, with both price and metadata."""
    market_id: str
    market_name: str
    venue: str
    market_start_time: str
    event_name: str
    event_country: str
    status: str
    inplay: bool
    recorded_at: str
    number_of_winners: int
    total_matched: float
    runners: list[RunnerSnapshot] = field(default_factory=list)


EXOTIC_PATTERNS = [
    "forecast", "reverse fc", "match bet", "without ",
    "to win by over", "to be placed", "each way",
    "daily win dist", "winning distances",
]


def is_main_race_market(market_name: str, event_name: str = "") -> bool:
    """
    Identify if a market is a main race WIN market (not exotic).
    The live engine only fetches WIN market types from Betfair.
    Since back-data doesn't have marketType, we filter by name patterns.
    Checks both market_name and event_name (some exotics have swapped fields).
    """
    combined = f"{market_name} {event_name}".lower().strip()
    for pattern in EXOTIC_PATTERNS:
        if pattern in combined:
            return False
    return True


def join_books_and_catalogue(
    books: list[dict],
    catalogues: list[dict],
) -> list[MarketSnapshot]:
    """
    Join books and catalogue entries by marketId.
    Returns a list of MarketSnapshot objects with full runner data.
    """
    # Index catalogues by marketId
    cat_by_id = {c["marketId"]: c for c in catalogues}

    results = []
    for book in books:
        mid = book["marketId"]
        cat = cat_by_id.get(mid)
        if cat is None:
            continue

        # Build runner name map from catalogue
        runner_names = {
            r["selectionId"]: r["runnerName"]
            for r in cat.get("runners", [])
        }

        # Build runner snapshots from book + catalogue data
        runners = []
        for r in book.get("runners", []):
            sid = r["selectionId"]
            lay_prices = r.get("ex", {}).get("availableToLay", [])
            back_prices = r.get("ex", {}).get("availableToBack", [])

            runners.append(RunnerSnapshot(
                selection_id=sid,
                runner_name=runner_names.get(sid, f"Selection {sid}"),
                handicap=r.get("handicap", 0.0),
                status=r.get("status", "ACTIVE"),
                best_available_to_lay=lay_prices[0]["price"] if lay_prices else None,
                best_available_to_back=back_prices[0]["price"] if back_prices else None,
                lay_depth=lay_prices,
                back_depth=back_prices,
                last_price_traded=r.get("lastPriceTraded"),
                total_matched=r.get("totalMatched", 0.0),
            ))

        event = cat.get("event", {})
        results.append(MarketSnapshot(
            market_id=mid,
            market_name=cat.get("marketName", ""),
            venue=event.get("venue", event.get("name", "Unknown")),
            market_start_time=cat.get("marketStartTime", ""),
            event_name=event.get("name", ""),
            event_country=event.get("countryCode", ""),
            status=book.get("status", "UNKNOWN"),
            inplay=book.get("inplay", False),
            recorded_at=book.get("_recorded_at", ""),
            number_of_winners=book.get("numberOfWinners", 1),
            total_matched=book.get("totalMatched", 0.0),
            runners=runners,
        ))

    return results
