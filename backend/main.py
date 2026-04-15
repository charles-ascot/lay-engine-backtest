"""
CHIMERA Live Data Recorder — FastAPI Server
=============================================
Exposes REST endpoints for:
  • Configuration management (Betfair, GCS, recorder settings)
  • Session validation and GCS connection testing
  • Recorder lifecycle (start / stop / manual poll)
  • Dashboard state (engine status, stats, market list)
  • Data feed for the Lay Bet App (drop-in Betfair replacement)
  • Health / keepalive for Cloud Run and Cloud Scheduler
"""

import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from config import AppConfig
from recorder import RecorderEngine

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)-12s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── Globals ──
config: AppConfig = None
engine: RecorderEngine = None


# ── Lifespan ──
@asynccontextmanager
async def lifespan(app: FastAPI):
    global config, engine
    config = AppConfig.load()
    engine = RecorderEngine(config)
    logger.info("CHIMERA Live Recorder initialised")
    yield
    if engine and engine.running:
        engine.stop()
    logger.info("CHIMERA Live Recorder shutdown")


# ── App ──
app = FastAPI(
    title="CHIMERA Live Data Recorder",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──
frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
cors_origins = [
    frontend_url,
    "http://localhost:5173",
    "http://localhost:3000",
]
# Support comma-separated FRONTEND_URL for multiple origins
if "," in frontend_url:
    cors_origins = [u.strip() for u in frontend_url.split(",")] + [
        "http://localhost:5173",
        "http://localhost:3000",
    ]
# Deduplicate
cors_origins = list(dict.fromkeys(cors_origins))
logger.info(f"CORS allowed origins: {cors_origins}")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════
#  REQUEST / RESPONSE MODELS
# ═══════════════════════════════════════════

class ConfigUpdate(BaseModel):
    betfair_app_key: Optional[str] = None
    betfair_ssoid: Optional[str] = None
    gcs_project_id: Optional[str] = None
    gcs_bucket_name: Optional[str] = None
    gcs_base_path: Optional[str] = None
    poll_interval_seconds: Optional[int] = None
    countries: Optional[list[str]] = None
    market_types: Optional[list[str]] = None
    price_projection: Optional[list[str]] = None
    catalogue_projections: Optional[list[str]] = None


class SessionValidation(BaseModel):
    ssoid: str
    app_key: Optional[str] = None


class CountriesRequest(BaseModel):
    countries: list[str]


class FeedBooksRequest(BaseModel):
    market_ids: list[str]


# ═══════════════════════════════════════════
#  HEALTH & KEEPALIVE
# ═══════════════════════════════════════════

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "recorder": engine.status if engine else "uninitialised",
    }


@app.get("/api/diag")
async def diagnostics():
    """Diagnostic endpoint — shows CORS config, env state, credential presence."""
    return {
        "cors_origins": cors_origins,
        "frontend_url_env": frontend_url,
        "betfair_app_key_set": bool(config.betfair.app_key),
        "betfair_ssoid_set": bool(config.betfair.ssoid),
        "gcs_configured": bool(config.gcs.bucket_name and config.gcs.project_id),
        "recorder_status": engine.status if engine else "uninitialised",
    }


@app.get("/api/keepalive")
async def keepalive():
    """Cloud Scheduler hits this to keep the instance warm."""
    result = {"warmed": True, "status": engine.status if engine else "uninitialised"}
    if engine and engine.running and engine.client:
        ka = engine.client.keepalive()
        result["session_alive"] = ka
    return result


# ═══════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════

@app.get("/api/config")
async def get_config():
    return config.to_safe_dict()


@app.post("/api/config")
async def update_config(update: ConfigUpdate):
    changes = update.model_dump(exclude_none=True)
    if not changes:
        raise HTTPException(400, "No fields provided")

    # Map flat fields back to nested config
    if "betfair_app_key" in changes:
        config.betfair.app_key = changes["betfair_app_key"]
    if "betfair_ssoid" in changes:
        config.betfair.ssoid = changes["betfair_ssoid"]
    if "gcs_project_id" in changes:
        config.gcs.project_id = changes["gcs_project_id"]
    if "gcs_bucket_name" in changes:
        config.gcs.bucket_name = changes["gcs_bucket_name"]
    if "gcs_base_path" in changes:
        config.gcs.base_path = changes["gcs_base_path"]
    if "poll_interval_seconds" in changes:
        config.recorder.poll_interval_seconds = changes["poll_interval_seconds"]
    if "countries" in changes:
        config.recorder.countries = changes["countries"]
    if "market_types" in changes:
        config.recorder.market_types = changes["market_types"]
    if "price_projection" in changes:
        config.recorder.price_projection = changes["price_projection"]
    if "catalogue_projections" in changes:
        config.recorder.catalogue_projections = changes["catalogue_projections"]

    engine.update_config(config)
    return {"success": True, "config": config.to_safe_dict()}


@app.post("/api/countries")
async def set_countries(req: CountriesRequest):
    """Update the market countries filter (quick toggle from dashboard)."""
    valid = {"GB", "IE", "ZA", "FR"}
    filtered = [c for c in req.countries if c in valid]
    if not filtered:
        raise HTTPException(400, "At least one valid country required")
    config.recorder.countries = filtered
    engine.update_config(config)
    return {"countries": config.recorder.countries}


# ═══════════════════════════════════════════
#  SESSION & CONNECTION TESTING
# ═══════════════════════════════════════════

@app.post("/api/validate-session")
async def validate_session(body: SessionValidation):
    """Test a Betfair SSOID before saving it."""
    from betfair_client import BetfairClient

    app_key = body.app_key or config.betfair.app_key
    if not app_key:
        return {
            "valid": False,
            "message": "No app key provided and none saved in config. Enter your Betfair Application Key.",
            "field": "app_key",
        }
    if not body.ssoid:
        return {
            "valid": False,
            "message": "No SSOID provided. Paste your Betfair session token.",
            "field": "ssoid",
        }

    test_client = BetfairClient(app_key=app_key, ssoid=body.ssoid)
    result = test_client.validate_session()
    return result


@app.post("/api/test-gcs")
async def test_gcs():
    """Test the GCS connection with current config."""
    result = engine.writer.test_connection()
    return result


# ═══════════════════════════════════════════
#  RECORDER LIFECYCLE
# ═══════════════════════════════════════════

@app.post("/api/recorder/start")
async def start_recorder():
    result = engine.start()
    if not result["success"]:
        raise HTTPException(400, result["message"])
    return result


@app.post("/api/recorder/stop")
async def stop_recorder():
    return engine.stop()


@app.post("/api/recorder/poll")
async def manual_poll():
    """Execute a single poll cycle (for testing)."""
    result = engine.run_single_poll()
    if not result["success"]:
        raise HTTPException(400, result["message"])
    return result


# ═══════════════════════════════════════════
#  DASHBOARD STATE
# ═══════════════════════════════════════════

@app.get("/api/state")
async def get_state():
    return engine.get_state()


# ═══════════════════════════════════════════
#  DATA FEED (for Lay Bet App)
# ═══════════════════════════════════════════

@app.get("/api/feed/markets")
async def feed_markets():
    """Return cached market catalogue — drop-in for Betfair listMarketCatalogue."""
    return engine.get_feed_markets()


@app.get("/api/feed/book/{market_id}")
async def feed_book(market_id: str):
    """Return cached market book — drop-in for Betfair listMarketBook."""
    book = engine.get_feed_book(market_id)
    if book is None:
        raise HTTPException(404, f"No book data for market {market_id}")
    return book


@app.post("/api/feed/books")
async def feed_books(body: FeedBooksRequest):
    """Return cached books for multiple markets."""
    return engine.get_feed_books(body.market_ids)


# ═══════════════════════════════════════════
#  DEBUG (temporary — remove once working)
# ═══════════════════════════════════════════

@app.get("/api/debug/catalogue")
async def debug_catalogue():
    """Make a raw listMarketCatalogue call and return the full response."""
    import requests as req
    from datetime import datetime, timezone
    from betfair_client import BETTING_API_URL

    if not engine.client.is_authenticated:
        return {"error": "Not authenticated"}

    now = datetime.now(timezone.utc)

    # Match the exact format from the working Lay Engine reference
    payload = {
        "jsonrpc": "2.0",
        "method": "SportsAPING/v1.0/listMarketCatalogue",
        "params": {
            "filter": {
                "eventTypeIds": ["7"],
                "marketCountries": config.recorder.countries,
                "marketStartTime": {
                    "from": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "to": now.replace(hour=23, minute=59, second=59).strftime("%Y-%m-%dT%H:%M:%SZ"),
                },
            },
            "maxResults": "200",
            "marketProjection": ["EVENT", "MARKET_START_TIME", "RUNNER_DESCRIPTION"],
            "sort": "FIRST_TO_START",
        },
        "id": 1,
    }

    resp = req.post(
        BETTING_API_URL,
        json=[payload],
        headers=engine.client._headers(),
        timeout=30,
    )

    return {
        "status_code": resp.status_code,
        "url": BETTING_API_URL,
        "payload": payload,
        "response_length": len(resp.text),
        "response_preview": resp.text[:2000],
    }


# ═══════════════════════════════════════════
#  RUN
# ═══════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        reload=True,
    )
