"""
CHIMERA Live Data Recorder — Configuration
============================================
Centralised configuration for the recorder.
All settings are environment-driven with sensible defaults.
Runtime settings can be updated via the API and persisted to disk and GCS.
"""

import os
import json
import logging
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Optional

logger = logging.getLogger("config")

RUNTIME_CONFIG_FILE = Path(
    os.environ.get("RUNTIME_CONFIG_FILE", "/tmp/chimera_recorder_config.json")
)


@dataclass
class BetfairConfig:
    """Betfair API authentication and connection settings."""
    app_key: str = ""
    ssoid: str = ""  # Session token (X-Authentication header)


@dataclass
class GCSConfig:
    """Google Cloud Storage settings."""
    project_id: str = ""
    bucket_name: str = ""
    base_path: str = "betfair-live"  # Root path prefix inside the bucket


@dataclass
class RecorderConfig:
    """Core recorder behaviour settings."""
    poll_interval_seconds: int = 60
    countries: list = field(default_factory=lambda: ["GB", "IE"])
    event_type_id: str = "7"  # Horse Racing
    market_types: list = field(default_factory=lambda: ["WIN"])  # WIN only
    price_projection: list = field(
        default_factory=lambda: [
            "EX_BEST_OFFERS",
            "EX_ALL_OFFERS",
            "EX_TRADED",
            "SP_AVAILABLE",
            "SP_TRADED",
        ]
    )
    max_markets_per_request: int = 6  # Betfair weight limit safeguard
    catalogue_projections: list = field(
        default_factory=lambda: [
            "EVENT",
            "MARKET_START_TIME",
            "RUNNER_DESCRIPTION",
            "MARKET_DESCRIPTION",
        ]
    )


# ── GCS config persistence helpers ──

def _gcs_config_path(base_path: str) -> str:
    """Build the GCS object path for the runtime config."""
    return f"{base_path.strip('/')}/config/runtime_config.json"


def _save_config_to_gcs(config_dict: dict, bucket_name: str, base_path: str):
    """Persist config dict to GCS. Best-effort, logs errors."""
    if not bucket_name:
        return
    try:
        from gcs_writer import _get_bucket
        object_path = _gcs_config_path(base_path)
        content = json.dumps(config_dict, indent=2).encode("utf-8")
        bucket = _get_bucket(bucket_name)
        blob = bucket.blob(object_path)
        blob.upload_from_string(content, content_type="application/json")
        logger.info(f"Config saved to GCS: gs://{bucket_name}/{object_path}")
    except Exception as e:
        logger.warning(f"Failed to save config to GCS: {e}")


def _load_config_from_gcs(bucket_name: str, base_path: str) -> Optional[dict]:
    """Load config dict from GCS. Returns None on any failure."""
    if not bucket_name:
        return None
    try:
        from gcs_writer import _get_bucket
        object_path = _gcs_config_path(base_path)
        bucket = _get_bucket(bucket_name)
        blob = bucket.blob(object_path)
        if not blob.exists():
            logger.info("No config found in GCS (first run?)")
            return None
        content = blob.download_as_text()
        data = json.loads(content)
        logger.info(f"Config loaded from GCS: gs://{bucket_name}/{object_path}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load config from GCS: {e}")
        return None


@dataclass
class AppConfig:
    """Top-level application configuration."""
    betfair: BetfairConfig = field(default_factory=BetfairConfig)
    gcs: GCSConfig = field(default_factory=GCSConfig)
    recorder: RecorderConfig = field(default_factory=RecorderConfig)
    frontend_url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_safe_dict(self) -> dict:
        """Return config without sensitive fields for the frontend."""
        d = self.to_dict()
        if d["betfair"]["ssoid"]:
            d["betfair"]["ssoid"] = f"...{d['betfair']['ssoid'][-8:]}"
        return d

    def save(self):
        """Persist runtime config to /tmp (fast cache) and GCS (durable)."""
        config_dict = self.to_dict()

        # Local cache (fast, survives warm restarts)
        try:
            RUNTIME_CONFIG_FILE.write_text(json.dumps(config_dict, indent=2))
            logger.info("Runtime config saved to /tmp")
        except Exception as e:
            logger.warning(f"Failed to save runtime config to /tmp: {e}")

        # GCS (durable, survives cold starts and redeployments)
        _save_config_to_gcs(config_dict, self.gcs.bucket_name, self.gcs.base_path)

    @classmethod
    def load(cls) -> "AppConfig":
        """Load config from env vars, then overlay from GCS (or /tmp fallback)."""
        config = cls()

        # ── Load from environment variables first ──
        config.betfair.app_key = os.environ.get("BETFAIR_APP_KEY", "")
        config.betfair.ssoid = os.environ.get("BETFAIR_SSOID", "")
        config.gcs.project_id = os.environ.get("GCS_PROJECT_ID", "")
        config.gcs.bucket_name = os.environ.get("GCS_BUCKET_NAME", "")
        config.gcs.base_path = os.environ.get("GCS_BASE_PATH", "betfair-live")
        config.frontend_url = os.environ.get(
            "FRONTEND_URL", "http://localhost:5173"
        )
        interval = os.environ.get("POLL_INTERVAL", "60")
        config.recorder.poll_interval_seconds = int(interval)

        # ── Overlay from GCS (durable source of truth) ──
        gcs_data = _load_config_from_gcs(
            config.gcs.bucket_name, config.gcs.base_path
        )
        if gcs_data:
            _merge_config(config, gcs_data)
            logger.info("Runtime config overlaid from GCS")
        else:
            # ── Fallback: overlay from /tmp (warm-instance cache) ──
            try:
                if RUNTIME_CONFIG_FILE.exists():
                    data = json.loads(RUNTIME_CONFIG_FILE.read_text())
                    _merge_config(config, data)
                    logger.info("Runtime config loaded from /tmp (GCS unavailable)")
            except Exception as e:
                logger.warning(f"Failed to load runtime config from /tmp: {e}")

        # Log effective config for debugging
        logger.info(
            f"Effective config: countries={config.recorder.countries}, "
            f"market_types={config.recorder.market_types}, "
            f"catalogue_projections={config.recorder.catalogue_projections}"
        )

        return config


def _merge_config(config: AppConfig, data: dict):
    """Merge a dict into the config, overwriting non-empty values."""
    bf = data.get("betfair", {})
    if bf.get("app_key"):
        config.betfair.app_key = bf["app_key"]
    if bf.get("ssoid"):
        config.betfair.ssoid = bf["ssoid"]

    gcs = data.get("gcs", {})
    if gcs.get("project_id"):
        config.gcs.project_id = gcs["project_id"]
    if gcs.get("bucket_name"):
        config.gcs.bucket_name = gcs["bucket_name"]
    if gcs.get("base_path"):
        config.gcs.base_path = gcs["base_path"]

    rec = data.get("recorder", {})
    if rec.get("poll_interval_seconds"):
        config.recorder.poll_interval_seconds = int(rec["poll_interval_seconds"])
    if rec.get("countries"):
        config.recorder.countries = rec["countries"]
    # Only override market_types if the saved value is a non-empty list.
    # An empty list [] means "no filter" which records ALL market types —
    # protect against this by requiring explicit non-empty values.
    if rec.get("market_types"):
        config.recorder.market_types = rec["market_types"]
    elif rec.get("market_types") is not None:
        # Saved config has market_types: [] — log warning and keep default
        logger.warning(
            f"Saved config has empty market_types (records ALL types). "
            f"Resetting to default: {config.recorder.market_types}"
        )
    if rec.get("price_projection"):
        config.recorder.price_projection = rec["price_projection"]
    if rec.get("catalogue_projections"):
        config.recorder.catalogue_projections = rec["catalogue_projections"]

    if data.get("frontend_url"):
        config.frontend_url = data["frontend_url"]
