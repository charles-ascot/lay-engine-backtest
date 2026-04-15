"""
CHIMERA Live Data Recorder — Core Recorder Engine
====================================================
Orchestrates the polling loop:
  1. Discover all UK/IE horse racing markets (catalogue)
  2. Fetch full price data for all markets (books)
  3. Save both to GCS in NDJSON format
  4. Cache latest data in memory for the Lay Bet App feed

Runs from midnight to midnight, polling every 60 seconds.
Day rolls over automatically. State persists across Cloud Run cold starts.
"""

import json
import time
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from copy import deepcopy

from config import AppConfig
from betfair_client import BetfairClient
from gcs_writer import GCSWriter

logger = logging.getLogger("recorder")

STATE_FILE = Path("/tmp/chimera_recorder_state.json")


class RecorderEngine:
    """
    Core recording engine.
    Discovers markets, fetches prices, writes to GCS, serves feed.
    """

    def __init__(self, config: AppConfig):
        self.config = config

        # ── Betfair client ──
        self.client = BetfairClient(
            app_key=config.betfair.app_key,
            ssoid=config.betfair.ssoid,
        )

        # ── GCS writer ──
        self.writer = GCSWriter(
            project_id=config.gcs.project_id,
            bucket_name=config.gcs.bucket_name,
            base_path=config.gcs.base_path,
        )

        # ── Engine state ──
        self.running = False
        self.status = "STOPPED"
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # ── Today's recording state ──
        self.day_started = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        self.poll_count = 0
        self.last_poll: Optional[str] = None
        self.last_catalogue_path: Optional[str] = None
        self.last_books_path: Optional[str] = None
        self.errors: list[dict] = []
        self.activity_log: list[dict] = []  # Recent activity for dashboard

        # ── In-memory data cache (for feed API and dashboard) ──
        self._catalogue_cache: list[dict] = []  # Latest catalogue data
        self._books_cache: dict[str, dict] = {}  # market_id -> latest book
        self._market_index: dict[str, dict] = {}  # market_id -> catalogue summary

        # ── Statistics ──
        self.stats = {
            "total_polls": 0,
            "total_markets_recorded": 0,
            "total_books_recorded": 0,
            "total_gcs_writes": 0,
            "gcs_errors": 0,
            "api_errors": 0,
        }

        # ── Load persisted state ──
        self._load_state()

    # ──────────────────────────────────────────────
    #  CONFIGURATION UPDATE
    # ──────────────────────────────────────────────

    def update_config(self, config: AppConfig):
        """Update configuration at runtime."""
        self.config = config
        self.client.update_credentials(
            app_key=config.betfair.app_key,
            ssoid=config.betfair.ssoid,
        )
        self.writer.update_config(
            project_id=config.gcs.project_id,
            bucket_name=config.gcs.bucket_name,
            base_path=config.gcs.base_path,
        )
        config.save()
        self._log("Configuration updated")
        logger.info("Configuration updated")

    # ──────────────────────────────────────────────
    #  ENGINE LIFECYCLE
    # ──────────────────────────────────────────────

    def start(self) -> dict:
        """Start the recording loop."""
        if not self.client.is_authenticated:
            return {"success": False, "message": "Not authenticated. Set SSOID first."}

        if self.running:
            return {"success": False, "message": "Already running."}

        # Validate session before starting
        self._log("Validating Betfair session...")
        validation = self.client.validate_session()
        if not validation["valid"]:
            self._log(f"Session validation failed: {validation['message']}", level="error")
            return {
                "success": False,
                "message": f"Session validation failed: {validation['message']}",
            }
        self._log("Session valid — starting recording loop")

        self.running = True
        self.status = "STARTING"
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._log("Recorder started")
        logger.info("Recorder started")
        return {"success": True, "message": "Recorder started."}

    def stop(self) -> dict:
        """Stop the recording loop."""
        self.running = False
        self.status = "STOPPED"
        self._save_state()
        self._log("Recorder stopped")
        logger.info("Recorder stopped")
        return {"success": True, "message": "Recorder stopped."}

    def _run_loop(self):
        """Main recording loop."""
        self.status = "RUNNING"
        logger.info(
            f"Recording loop started "
            f"(interval={self.config.recorder.poll_interval_seconds}s, "
            f"countries={self.config.recorder.countries})"
        )

        while self.running:
            try:
                self._check_day_rollover()
                self._poll_cycle()
            except Exception as e:
                logger.error(f"Poll cycle error: {e}", exc_info=True)
                self._add_error(f"Poll cycle error: {e}")
                self.stats["api_errors"] += 1

            # Sleep in small increments so stop() is responsive
            for _ in range(self.config.recorder.poll_interval_seconds):
                if not self.running:
                    break
                time.sleep(1)

        self.status = "STOPPED"
        logger.info("Recording loop ended")

    def _check_day_rollover(self):
        """Reset daily state at midnight UTC."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if today != self.day_started:
            logger.info(f"Day rollover: {self.day_started} → {today}")
            self.day_started = today
            self.poll_count = 0
            self._catalogue_cache = []
            self._books_cache = {}
            self._market_index = {}
            self.errors = []
            self._save_state()

    # ──────────────────────────────────────────────
    #  CORE POLL CYCLE
    # ──────────────────────────────────────────────

    def _poll_cycle(self):
        """Execute one complete poll cycle: catalogue + books + save."""
        now = datetime.now(timezone.utc)
        self.last_poll = now.isoformat()
        self.poll_count += 1

        # ── Ensure session is alive ──
        self._log(f"Poll #{self.poll_count}: checking Betfair session...")
        if not self.client.ensure_session():
            self._add_error("Session expired — attempting keepalive failed")
            self.status = "AUTH_ERROR"
            return

        self._log(
            f"Poll #{self.poll_count}: session OK, fetching catalogue "
            f"(countries={self.config.recorder.countries}, "
            f"market_types={self.config.recorder.market_types or 'ALL'})"
        )
        self.status = "POLLING"

        # ── Step 1: Fetch market catalogue ──
        catalogue = self.client.get_market_catalogue(
            countries=self.config.recorder.countries,
            market_types=self.config.recorder.market_types,
            projections=self.config.recorder.catalogue_projections,
        )

        if catalogue is None:
            self._log(
                f"Poll #{self.poll_count}: catalogue API call FAILED — "
                f"check Cloud Run logs for error details",
                level="error",
            )
            self.stats["api_errors"] += 1
            self.status = "RUNNING"
            return

        if len(catalogue) == 0:
            self._log(
                f"Poll #{self.poll_count}: Betfair returned 0 markets "
                f"(API OK but no matches for current filter)",
                level="warn",
            )
            logger.info("No markets found in this poll cycle")
            self.status = "RUNNING"
            return

        # Update caches
        with self._lock:
            self._catalogue_cache = catalogue
            for market in catalogue:
                mid = market.get("marketId", "")
                self._market_index[mid] = {
                    "marketId": mid,
                    "marketName": market.get("marketName", ""),
                    "marketStartTime": market.get("marketStartTime", ""),
                    "venue": market.get("event", {}).get("venue", ""),
                    "event": market.get("event", {}).get("name", ""),
                    "runners": len(market.get("runners", [])),
                    "status": "OPEN",
                }

        self._log(f"Poll #{self.poll_count}: found {len(catalogue)} markets, fetching books...")

        # ── Step 2: Fetch market books (prices) ──
        market_ids = [m["marketId"] for m in catalogue]

        books = self.client.get_market_books(
            market_ids=market_ids,
            price_data=self.config.recorder.price_projection,
        )

        # Update book cache
        with self._lock:
            for book in books:
                mid = book.get("marketId", "")
                self._books_cache[mid] = book
                # Update status in market index
                if mid in self._market_index:
                    self._market_index[mid]["status"] = book.get("status", "UNKNOWN")
                    self._market_index[mid]["inPlay"] = book.get("inPlay", False)
                    self._market_index[mid]["totalMatched"] = book.get(
                        "totalMatched", 0
                    )

        self._log(f"Poll #{self.poll_count}: got {len(books)} books, writing to GCS...")

        # ── Step 3: Write to GCS ──
        self.status = "WRITING"

        cat_path = self.writer.write_catalogue(catalogue, now)
        if cat_path:
            self.last_catalogue_path = cat_path
            self.stats["total_gcs_writes"] += 1
            self._log(f"GCS write: catalogue → {cat_path}")
        elif self.writer.is_configured:
            self.stats["gcs_errors"] += 1
            self._log("GCS write failed: catalogue", level="error")

        book_path = self.writer.write_books(books, now)
        if book_path:
            self.last_books_path = book_path
            self.stats["total_gcs_writes"] += 1
            self._log(f"GCS write: books → {book_path}")
        elif self.writer.is_configured:
            self.stats["gcs_errors"] += 1
            self._log("GCS write failed: books", level="error")

        # ── Update stats ──
        self.stats["total_polls"] += 1
        self.stats["total_markets_recorded"] += len(catalogue)
        self.stats["total_books_recorded"] += len(books)

        # ── Persist state every 5 polls ──
        if self.poll_count % 5 == 0:
            self._save_state()

        self.status = "RUNNING"
        self._log(f"Poll #{self.poll_count} complete: {len(catalogue)} markets, {len(books)} books")
        logger.info(
            f"Poll #{self.poll_count}: {len(catalogue)} markets, "
            f"{len(books)} books recorded"
        )

    # ──────────────────────────────────────────────
    #  DATA FEED (for Lay Bet App)
    # ──────────────────────────────────────────────

    def get_feed_markets(self) -> list[dict]:
        """
        Return cached market catalogue in the same format as
        Betfair's listMarketCatalogue response.
        Used by the Lay Bet App as a drop-in replacement.
        """
        with self._lock:
            return deepcopy(self._catalogue_cache)

    def get_feed_book(self, market_id: str) -> Optional[dict]:
        """
        Return cached market book for a specific market.
        Same format as Betfair's listMarketBook response (single market).
        """
        with self._lock:
            book = self._books_cache.get(market_id)
            return deepcopy(book) if book else None

    def get_feed_books(self, market_ids: list[str]) -> list[dict]:
        """
        Return cached market books for multiple markets.
        Same format as Betfair's listMarketBook response.
        """
        with self._lock:
            result = []
            for mid in market_ids:
                book = self._books_cache.get(mid)
                if book:
                    result.append(deepcopy(book))
            return result

    # ──────────────────────────────────────────────
    #  STATE ACCESS (for dashboard)
    # ──────────────────────────────────────────────

    def get_state(self) -> dict:
        """Return full engine state for the frontend dashboard."""
        now = datetime.now(timezone.utc)

        with self._lock:
            # Build market summary
            markets_summary = []
            for mid, info in self._market_index.items():
                try:
                    start_time = info.get("marketStartTime", "")
                    if start_time:
                        rt = datetime.fromisoformat(
                            start_time.replace("Z", "+00:00")
                        )
                        info_copy = dict(info)
                        info_copy["minutesToOff"] = round(
                            (rt - now).total_seconds() / 60, 1
                        )
                        info_copy["hasBookData"] = mid in self._books_cache
                        markets_summary.append(info_copy)
                except (ValueError, KeyError):
                    markets_summary.append(info)

            markets_summary.sort(key=lambda x: x.get("marketStartTime", ""))

        return {
            "status": self.status,
            "authenticated": self.client.is_authenticated,
            "date": self.day_started,
            "lastPoll": self.last_poll,
            "pollCount": self.poll_count,
            "pollInterval": self.config.recorder.poll_interval_seconds,
            "stats": {
                **self.stats,
                "markets_cached": len(self._market_index),
                "books_cached": len(self._books_cache),
            },
            "gcs": self.writer.stats,
            "lastCataloguePath": self.last_catalogue_path,
            "lastBooksPath": self.last_books_path,
            "markets": markets_summary,
            "errors": self.errors[-20:],
            "log": self.activity_log[-50:],
            "config": self.config.to_safe_dict(),
        }

    def run_single_poll(self) -> dict:
        """Execute a single poll cycle manually (for testing)."""
        if not self.client.is_authenticated:
            return {"success": False, "message": "Not authenticated"}
        try:
            self._poll_cycle()
            return {
                "success": True,
                "message": f"Poll complete: {len(self._catalogue_cache)} markets",
            }
        except Exception as e:
            return {"success": False, "message": str(e)}

    # ──────────────────────────────────────────────
    #  STATE PERSISTENCE
    # ──────────────────────────────────────────────

    def _save_state(self):
        """Persist state for Cloud Run cold-start recovery."""
        try:
            state = {
                "day_started": self.day_started,
                "poll_count": self.poll_count,
                "last_poll": self.last_poll,
                "stats": self.stats,
                "errors": self.errors[-50:],
                "status": self.status,
                "saved_at": datetime.now(timezone.utc).isoformat(),
            }
            STATE_FILE.write_text(json.dumps(state, default=str))
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")

    def _load_state(self):
        """Reload state after a cold start."""
        try:
            if not STATE_FILE.exists():
                return
            data = json.loads(STATE_FILE.read_text())

            # Only restore same-day state
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            if data.get("day_started") != today:
                STATE_FILE.unlink(missing_ok=True)
                return

            self.day_started = data["day_started"]
            self.poll_count = data.get("poll_count", 0)
            self.last_poll = data.get("last_poll")
            self.stats = {**self.stats, **data.get("stats", {})}
            self.errors = data.get("errors", [])

            logger.info(
                f"Restored state: {self.poll_count} polls from today"
            )
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")

    def _log(self, msg: str, level: str = "info"):
        """Add an entry to the activity log visible on the dashboard."""
        self.activity_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": msg,
        })
        if len(self.activity_log) > 500:
            self.activity_log = self.activity_log[-250:]

    def _add_error(self, msg: str):
        """Record an error."""
        self._log(msg, level="error")
        self.errors.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "message": msg,
            }
        )
        if len(self.errors) > 200:
            self.errors = self.errors[-100:]
