"""
CHIMERA Back-Test Workbench — FastAPI App
==========================================
REST API for the back-testing workbench.
"""

import os
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from dotenv import load_dotenv

from gcs_reader import DataReader
from data_loader import join_books_and_catalogue, is_main_race_market
from strategy_schema import Strategy
from simulator import Simulator, SimulationRequest
from default_strategies import CHIMERA_DEFAULT

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(name)s | %(message)s")
logger = logging.getLogger("main")

# ── Configuration ──
GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME", "")
LOCAL_DATA_DIR = os.environ.get("LOCAL_DATA_DIR", "../back-data")
STRATEGIES_DIR = Path(os.environ.get("STRATEGIES_DIR", "./strategies"))
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

# Ensure strategies directory exists
STRATEGIES_DIR.mkdir(parents=True, exist_ok=True)

# ── Data Reader ──
reader = DataReader(
    bucket_name=GCS_BUCKET_NAME if GCS_BUCKET_NAME else None,
    local_dir=LOCAL_DATA_DIR if not GCS_BUCKET_NAME else None,
)

simulator = Simulator(reader)

# ── FastAPI app ──
app = FastAPI(title="CHIMERA Back-Test Workbench")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "https://layback.thync.online",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_origin_regex=r"https://.*\.pages\.dev",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request/Response Models ──

class SimulateBody(BaseModel):
    date: str
    strategy: Strategy
    market_ids: Optional[list[str]] = None


class SaveStrategyBody(BaseModel):
    strategy: Strategy


# ── Endpoints ──

@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "source": "gcs" if GCS_BUCKET_NAME else "local",
        "data_dir": LOCAL_DATA_DIR if not GCS_BUCKET_NAME else None,
        "bucket": GCS_BUCKET_NAME if GCS_BUCKET_NAME else None,
    }


@app.get("/api/dates")
def list_dates():
    """List all available dates with recorded data."""
    dates = reader.list_available_dates()
    return {"dates": dates}


@app.get("/api/markets/{date}")
def list_markets(date: str):
    """List all WIN markets for a given date, grouped by venue."""
    snapshots = reader.list_snapshots_for_date(date)
    if not snapshots:
        return {"date": date, "venues": [], "total_markets": 0}

    # Use the first snapshot to get market listing
    sp = snapshots[0]
    books = reader.read_ndjson(sp.books_path)
    cats = reader.read_ndjson(sp.catalogue_path)
    markets = join_books_and_catalogue(books, cats)

    # Filter to main race WIN markets (exclude exotics like Forecast, Each Way, etc.)
    win_markets = [
        m for m in markets
        if m.number_of_winners == 1 and is_main_race_market(m.market_name, m.event_name)
    ]

    # Group by venue
    venues: dict[str, list] = {}
    for m in win_markets:
        venue = m.venue or "Unknown"
        if venue not in venues:
            venues[venue] = []

        # Count active runners with lay prices
        active_runners = [
            r for r in m.runners
            if r.status == "ACTIVE" and r.best_available_to_lay is not None
        ]

        venues[venue].append({
            "market_id": m.market_id,
            "market_name": m.market_name,
            "market_start_time": m.market_start_time,
            "venue": venue,
            "event_name": m.event_name,
            "runner_count": len(active_runners),
            "total_matched": m.total_matched,
            "runners": [
                {
                    "selection_id": r.selection_id,
                    "runner_name": r.runner_name,
                    "best_lay_odds": r.best_available_to_lay,
                    "best_back_odds": r.best_available_to_back,
                    "status": r.status,
                }
                for r in m.runners
                if r.status == "ACTIVE"
            ],
        })

    # Sort venues and markets within each venue
    sorted_venues = []
    for venue_name in sorted(venues.keys()):
        venue_markets = sorted(venues[venue_name], key=lambda m: m["market_start_time"])
        sorted_venues.append({
            "venue": venue_name,
            "markets": venue_markets,
        })

    return {
        "date": date,
        "venues": sorted_venues,
        "total_markets": len(win_markets),
        "snapshot_count": len(snapshots),
    }


@app.post("/api/simulate")
def simulate(body: SimulateBody):
    """Run a back-test simulation."""
    request = SimulationRequest(
        date=body.date,
        strategy=body.strategy,
        market_ids=body.market_ids,
    )
    result = simulator.run(request)
    return result.to_dict()


@app.get("/api/strategies/default")
def get_default_strategy():
    """Return the CHIMERA default strategy as JSON."""
    return CHIMERA_DEFAULT


@app.get("/api/strategies")
def list_strategies():
    """List all saved strategies."""
    strategies = []

    # Always include the default
    strategies.append({
        "id": CHIMERA_DEFAULT["id"],
        "name": CHIMERA_DEFAULT["name"],
        "description": CHIMERA_DEFAULT["description"],
        "is_default": True,
    })

    # Load saved strategies
    for f in STRATEGIES_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            strategies.append({
                "id": data.get("id", f.stem),
                "name": data.get("name", f.stem),
                "description": data.get("description", ""),
                "is_default": False,
            })
        except Exception:
            pass

    return {"strategies": strategies}


@app.get("/api/strategies/{strategy_id}")
def get_strategy(strategy_id: str):
    """Get a specific strategy by ID."""
    if strategy_id == "chimera_default":
        return CHIMERA_DEFAULT

    path = STRATEGIES_DIR / f"{strategy_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Strategy not found")

    return json.loads(path.read_text())


@app.post("/api/strategies")
def save_strategy(body: SaveStrategyBody):
    """Save a strategy to disk."""
    strategy = body.strategy
    path = STRATEGIES_DIR / f"{strategy.id}.json"
    path.write_text(json.dumps(strategy.model_dump(), indent=2))
    return {"status": "saved", "id": strategy.id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
