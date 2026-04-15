"""
CHIMERA Live Data Recorder — Betfair API Client
=================================================
Read-only Betfair Exchange API client for data recording.
NO betting operations. Only market discovery and price retrieval.

Authentication uses SSOID (session token) which the user obtains
from their Betfair session and provides via the settings UI.
Session keepalive is handled automatically.
"""

import json
import time
import logging
import requests
from datetime import datetime, timedelta, timezone
from typing import Optional

logger = logging.getLogger("betfair")

# ── Betfair API endpoints ──
KEEPALIVE_URL = "https://identitysso.betfair.com/api/keepAlive"
BETTING_API_URL = "https://api.betfair.com/exchange/betting/json-rpc/v1"

# ── Horse Racing event type ──
EVENT_TYPE_HORSE_RACING = "7"

# ── Betfair market data weight limits ──
# sum(weight) * number_of_market_ids must not exceed 200 per request
PRICE_WEIGHTS = {
    "EX_BEST_OFFERS": 5,
    "EX_ALL_OFFERS": 17,
    "EX_TRADED": 17,
    "SP_AVAILABLE": 3,
    "SP_TRADED": 7,
}
# Known combined weights (overrides sum of individuals)
COMBINED_WEIGHTS = {
    frozenset(["EX_BEST_OFFERS", "EX_TRADED"]): 20,
    frozenset(["EX_ALL_OFFERS", "EX_TRADED"]): 32,
}
MAX_REQUEST_WEIGHT = 200


def calculate_batch_size(price_data: list[str]) -> int:
    """
    Calculate how many markets can be requested per API call
    given the requested price projections and Betfair's weight limits.
    """
    data_set = frozenset(price_data)

    # Check for known combined weights first
    for combo, weight in COMBINED_WEIGHTS.items():
        if combo.issubset(data_set):
            # Use the heaviest known combo as base, add remaining
            remaining = data_set - combo
            total = weight + sum(PRICE_WEIGHTS.get(p, 0) for p in remaining)
            return max(1, MAX_REQUEST_WEIGHT // total)

    # Sum individual weights
    total = sum(PRICE_WEIGHTS.get(p, 2) for p in price_data)
    if total == 0:
        total = 2  # Null projection default weight
    return max(1, MAX_REQUEST_WEIGHT // total)


class BetfairClient:
    """Read-only Betfair Exchange API client for data recording."""

    def __init__(self, app_key: str, ssoid: str):
        self.app_key = app_key
        self.ssoid = ssoid
        self._last_keepalive: Optional[datetime] = None
        self._session_valid = bool(ssoid)

    def update_credentials(self, app_key: str, ssoid: str):
        """Update credentials (called when user changes settings)."""
        self.app_key = app_key
        self.ssoid = ssoid
        self._session_valid = bool(ssoid)
        self._last_keepalive = None

    @property
    def is_authenticated(self) -> bool:
        return bool(self.app_key and self.ssoid and self._session_valid)

    def _headers(self) -> dict:
        return {
            "X-Application": self.app_key,
            "X-Authentication": self.ssoid,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def keepalive(self) -> bool:
        """Send keepalive to extend session. Should be called periodically."""
        if not self.ssoid:
            return False
        try:
            resp = requests.post(
                KEEPALIVE_URL,
                headers=self._headers(),
                timeout=10,
            )
            data = resp.json()
            if data.get("status") == "SUCCESS":
                self._last_keepalive = datetime.now(timezone.utc)
                self._session_valid = True
                logger.debug("Keepalive successful")
                return True
            else:
                logger.warning(f"Keepalive failed: {data.get('error', 'unknown')}")
                self._session_valid = False
                return False
        except Exception as e:
            logger.error(f"Keepalive exception: {e}")
            return False

    def ensure_session(self) -> bool:
        """
        Ensure the session is valid.
        Sends keepalive if more than 15 minutes since last one.
        """
        if not self.ssoid or not self.app_key:
            return False

        now = datetime.now(timezone.utc)
        if self._last_keepalive is None or (
            now - self._last_keepalive > timedelta(minutes=15)
        ):
            return self.keepalive()

        return self._session_valid

    def _api_call(self, method: str, params: dict) -> Optional[list | dict]:
        """
        Make a JSON-RPC call to the Betfair Betting API.
        Matches the proven format from the working Lay Engine client.
        """
        if not self.is_authenticated:
            logger.error("Cannot make API call: not authenticated")
            return None

        payload = {
            "jsonrpc": "2.0",
            "method": f"SportsAPING/v1.0/{method}",
            "params": params,
            "id": 1,
        }

        try:
            resp = requests.post(
                BETTING_API_URL,
                json=[payload],
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            results = resp.json()

            if results and len(results) > 0:
                result = results[0]
                if "error" in result:
                    error = result["error"]
                    logger.error(f"API error on {method}: {error}")
                    # Check for auth errors
                    if isinstance(error, dict):
                        err_code = error.get("data", {}).get("APINGException", {}).get(
                            "errorCode", ""
                        )
                        if err_code in ("INVALID_SESSION_INFORMATION", "NO_SESSION"):
                            self._session_valid = False
                    return None
                data = result.get("result")
                if data is None:
                    logger.warning(
                        f"API {method}: result key missing. "
                        f"Response keys: {list(result.keys())}"
                    )
                elif isinstance(data, list):
                    logger.info(f"API {method}: returned {len(data)} results")
                return data

            logger.warning(
                f"API {method}: empty response body. "
                f"Raw (first 300 chars): {resp.text[:300]}"
            )
            return None

        except requests.exceptions.Timeout:
            logger.error(f"API call {method} timed out")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API call {method} failed: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in {method}: {e}")
            return None

    # ──────────────────────────────────────────────
    #  MARKET CATALOGUE (static/semi-static data)
    # ──────────────────────────────────────────────

    def get_market_catalogue(
        self,
        countries: list[str],
        market_types: list[str],
        projections: list[str],
        from_time: Optional[datetime] = None,
        to_time: Optional[datetime] = None,
    ) -> Optional[list[dict]]:
        """
        Fetch market catalogue for UK/IE horse racing.
        Returns list of markets, or None on API failure.
        """
        now = datetime.now(timezone.utc)
        if from_time is None:
            from_time = now
        if to_time is None:
            to_time = now.replace(hour=23, minute=59, second=59, microsecond=0)

        market_filter = {
            "eventTypeIds": [EVENT_TYPE_HORSE_RACING],
            "marketCountries": countries,
            "marketStartTime": {
                "from": from_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": to_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            },
        }

        # Only filter by market type if explicitly specified
        if market_types:
            market_filter["marketTypeCodes"] = market_types

        params = {
            "filter": market_filter,
            "maxResults": "200",
            "marketProjection": projections,
            "sort": "FIRST_TO_START",
        }

        result = self._api_call("listMarketCatalogue", params)
        if result is None:
            return None

        logger.info(f"Catalogue: {len(result)} markets found")
        return result

    # ──────────────────────────────────────────────
    #  MARKET BOOK (dynamic price data)
    # ──────────────────────────────────────────────

    def get_market_books(
        self,
        market_ids: list[str],
        price_data: list[str],
    ) -> list[dict]:
        """
        Fetch market book (prices) for a list of market IDs.
        Automatically batches requests to respect Betfair weight limits.
        Returns raw Betfair response data.
        """
        if not market_ids:
            return []

        batch_size = calculate_batch_size(price_data)
        all_books = []

        for i in range(0, len(market_ids), batch_size):
            batch = market_ids[i : i + batch_size]
            params = {
                "marketIds": batch,
                "priceProjection": {
                    "priceData": price_data,
                    "virtualise": True,
                },
            }

            result = self._api_call("listMarketBook", params)
            if result:
                all_books.extend(result)

            # Small delay between batches to be a good API citizen
            if i + batch_size < len(market_ids):
                time.sleep(0.2)

        logger.info(
            f"Books: {len(all_books)}/{len(market_ids)} markets fetched "
            f"(batch_size={batch_size})"
        )
        return all_books

    # ──────────────────────────────────────────────
    #  VENUES (for navigation)
    # ──────────────────────────────────────────────

    def get_venues(self, countries: list[str]) -> list[dict]:
        """Fetch list of venues for horse racing in specified countries."""
        params = {
            "filter": {
                "eventTypeIds": [EVENT_TYPE_HORSE_RACING],
                "marketCountries": countries,
            },
        }
        result = self._api_call("listVenues", params)
        return result or []

    # ──────────────────────────────────────────────
    #  SESSION VALIDATION
    # ──────────────────────────────────────────────

    def validate_session(self) -> dict:
        """
        Validate the current SSOID by making a lightweight API call.
        Returns status dict with authentication state and diagnostic info.
        """
        if not self.app_key:
            return {"valid": False, "message": "App key is empty", "field": "app_key"}
        if not self.ssoid:
            return {"valid": False, "message": "SSOID is empty", "field": "ssoid"}

        # First try keepalive to test the session token directly
        try:
            resp = requests.post(
                KEEPALIVE_URL,
                headers=self._headers(),
                timeout=10,
            )
            ka_data = resp.json()
            if ka_data.get("status") != "SUCCESS":
                ka_error = ka_data.get("error", "unknown")
                return {
                    "valid": False,
                    "message": f"Session token rejected by Betfair: {ka_error}. Get a fresh SSOID from your Betfair session.",
                    "field": "ssoid",
                    "betfair_response": ka_data,
                }
        except Exception as e:
            return {
                "valid": False,
                "message": f"Could not reach Betfair identity API: {e}",
            }

        # Now test the betting API with the app key
        result = self._api_call(
            "listEventTypes",
            {"filter": {"eventTypeIds": [EVENT_TYPE_HORSE_RACING]}},
        )
        if result is not None:
            self._session_valid = True
            return {"valid": True, "message": "Session is valid — both app key and SSOID confirmed"}
        else:
            self._session_valid = False
            return {
                "valid": False,
                "message": "Session token is valid but the Betting API rejected the request. Check your app key has the correct permissions.",
                "field": "app_key",
            }
