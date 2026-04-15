"""
CHIMERA Live Data Recorder — GCS Writer
=========================================
Writes market data to Google Cloud Storage in NDJSON format.

Directory hierarchy follows Betfair's conventions:
  gs://{bucket}/{base_path}/{event_type_id}/{YYYY-MM-DD}/
    ├── catalogue/
    │   └── {HH-MM-SS}.ndjson        (one line per market)
    └── books/
        └── {HH-MM-SS}.ndjson        (one line per market)

Each NDJSON file contains one JSON object per line, where each line
represents a single market's data at that timestamp.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from io import BytesIO

logger = logging.getLogger("gcs")

# GCS client is lazily initialised to avoid import errors
# when google-cloud-storage isn't needed (e.g. local dev)
_storage_client = None
_bucket_cache = {}


def _get_client():
    """Lazy-init the GCS client."""
    global _storage_client
    if _storage_client is None:
        from google.cloud import storage
        _storage_client = storage.Client()
    return _storage_client


def _get_bucket(bucket_name: str):
    """Get a bucket object, cached to avoid repeated lookups."""
    if bucket_name not in _bucket_cache:
        client = _get_client()
        _bucket_cache[bucket_name] = client.bucket(bucket_name)
    return _bucket_cache[bucket_name]


class GCSWriter:
    """Writes NDJSON data to Google Cloud Storage."""

    def __init__(
        self,
        project_id: str,
        bucket_name: str,
        base_path: str = "betfair-live",
        event_type_id: str = "7",
    ):
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.base_path = base_path.strip("/")
        self.event_type_id = event_type_id
        self._enabled = bool(bucket_name)
        self._write_count = 0
        self._error_count = 0
        self._last_error: Optional[str] = None

    @property
    def is_configured(self) -> bool:
        return bool(self.bucket_name and self.project_id)

    @property
    def stats(self) -> dict:
        return {
            "enabled": self._enabled,
            "configured": self.is_configured,
            "bucket": self.bucket_name,
            "base_path": self.base_path,
            "writes": self._write_count,
            "errors": self._error_count,
            "last_error": self._last_error,
        }

    def update_config(
        self,
        project_id: str,
        bucket_name: str,
        base_path: str,
    ):
        """Update GCS configuration."""
        self.project_id = project_id
        self.bucket_name = bucket_name
        self.base_path = base_path.strip("/")
        self._enabled = bool(bucket_name)
        # Clear bucket cache in case bucket changed
        _bucket_cache.clear()

    def _build_path(self, data_type: str, timestamp: datetime) -> str:
        """
        Build the GCS object path following Betfair's hierarchy.

        Pattern: {base_path}/{event_type}/{YYYY-MM-DD}/{data_type}/{HH-MM-SS}.ndjson
        """
        date_str = timestamp.strftime("%Y-%m-%d")
        time_str = timestamp.strftime("%H-%M-%S")
        return (
            f"{self.base_path}/{self.event_type_id}/{date_str}/"
            f"{data_type}/{time_str}.ndjson"
        )

    def write_ndjson(
        self,
        data_type: str,
        records: list[dict],
        timestamp: Optional[datetime] = None,
    ) -> Optional[str]:
        """
        Write a list of dicts as NDJSON to GCS.

        Args:
            data_type: 'catalogue' or 'books'
            records: List of dicts, each becomes one NDJSON line
            timestamp: Override timestamp (defaults to now UTC)

        Returns:
            The GCS object path if successful, None on failure.
        """
        if not self._enabled or not self.is_configured:
            return None

        if not records:
            return None

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        object_path = self._build_path(data_type, timestamp)

        try:
            # Build NDJSON content
            lines = []
            for record in records:
                # Inject recording metadata
                enriched = {
                    "_recorded_at": timestamp.isoformat(),
                    "_data_type": data_type,
                    **record,
                }
                lines.append(json.dumps(enriched, separators=(",", ":")))

            content = "\n".join(lines) + "\n"
            content_bytes = content.encode("utf-8")

            # Upload to GCS
            bucket = _get_bucket(self.bucket_name)
            blob = bucket.blob(object_path)
            blob.upload_from_file(
                BytesIO(content_bytes),
                content_type="application/x-ndjson",
                size=len(content_bytes),
            )

            self._write_count += 1
            logger.info(
                f"GCS write: {object_path} "
                f"({len(records)} records, {len(content_bytes)} bytes)"
            )
            return object_path

        except Exception as e:
            self._error_count += 1
            self._last_error = str(e)
            logger.error(f"GCS write failed for {object_path}: {e}")
            return None

    def write_catalogue(
        self, markets: list[dict], timestamp: Optional[datetime] = None
    ) -> Optional[str]:
        """Write market catalogue data to GCS."""
        return self.write_ndjson("catalogue", markets, timestamp)

    def write_books(
        self, books: list[dict], timestamp: Optional[datetime] = None
    ) -> Optional[str]:
        """Write market book (price) data to GCS."""
        return self.write_ndjson("books", books, timestamp)

    def test_connection(self) -> dict:
        """
        Test the GCS connection by attempting to access the bucket.
        Returns a status dict.
        """
        if not self.is_configured:
            return {
                "success": False,
                "message": "GCS not configured (missing project_id or bucket_name)",
            }
        try:
            bucket = _get_bucket(self.bucket_name)
            # Attempt to check if bucket exists
            client = _get_client()
            bucket_obj = client.get_bucket(self.bucket_name)
            return {
                "success": True,
                "message": f"Connected to bucket: {bucket_obj.name}",
                "location": bucket_obj.location,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"GCS connection failed: {e}",
            }
