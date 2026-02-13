"""
CHIMERA Back-Test Workbench — GCS Reader
=========================================
List and read NDJSON files from Google Cloud Storage.
Also supports reading local files for development.
"""

import json
import os
import re
import time
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger("gcs_reader")

FILENAME_PATTERN = re.compile(
    r"betfair-live_7_(\d{4}-\d{2}-\d{2})_(books|catalogue)_(\d{2}-\d{2}-\d{2})\.ndjson"
)


@dataclass
class SnapshotPair:
    """A paired books + catalogue snapshot."""
    date: str
    timestamp: str  # "HH-MM-SS"
    books_path: str
    catalogue_path: str


def parse_filename(name: str) -> Optional[tuple[str, str, str]]:
    """Parse a filename into (date, data_type, time). Returns None if not matching."""
    # Strip directory prefix
    basename = name.rsplit("/", 1)[-1] if "/" in name else name
    m = FILENAME_PATTERN.match(basename)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return None


class DataReader:
    """
    Reads NDJSON data from either GCS or local filesystem.
    Provides a uniform interface for both.
    """

    def __init__(self, bucket_name: Optional[str] = None, local_dir: Optional[str] = None):
        self.bucket_name = bucket_name
        self.local_dir = local_dir
        self._gcs_client = None
        self._dates_cache: Optional[tuple[float, list[str]]] = None
        self._CACHE_TTL = 300  # 5 minutes

    @property
    def gcs_client(self):
        if self._gcs_client is None and self.bucket_name:
            from google.cloud import storage
            self._gcs_client = storage.Client()
        return self._gcs_client

    def list_available_dates(self) -> list[str]:
        """List all dates that have recorded data."""
        # Check cache
        if self._dates_cache:
            cached_at, dates = self._dates_cache
            if time.time() - cached_at < self._CACHE_TTL:
                return dates

        if self.local_dir:
            dates = self._list_dates_local()
        elif self.bucket_name:
            dates = self._list_dates_gcs()
        else:
            dates = []

        dates.sort()
        self._dates_cache = (time.time(), dates)
        return dates

    def list_snapshots_for_date(self, date: str) -> list[SnapshotPair]:
        """List all paired snapshots for a given date, sorted chronologically."""
        if self.local_dir:
            return self._list_snapshots_local(date)
        elif self.bucket_name:
            return self._list_snapshots_gcs(date)
        return []

    def read_ndjson(self, path: str) -> list[dict]:
        """Read an NDJSON file and return list of parsed JSON objects."""
        if self.local_dir:
            return self._read_local(path)
        elif self.bucket_name:
            return self._read_gcs(path)
        return []

    # ── Local filesystem ──

    def _list_dates_local(self) -> list[str]:
        dates = set()
        local = Path(self.local_dir)
        if not local.exists():
            return []
        for f in local.iterdir():
            parsed = parse_filename(f.name)
            if parsed:
                dates.add(parsed[0])
        return list(dates)

    def _list_snapshots_local(self, date: str) -> list[SnapshotPair]:
        local = Path(self.local_dir)
        if not local.exists():
            return []

        # Group files by (date, timestamp)
        groups: dict[str, dict[str, str]] = {}
        for f in local.iterdir():
            parsed = parse_filename(f.name)
            if parsed and parsed[0] == date:
                file_date, data_type, file_time = parsed
                key = file_time
                if key not in groups:
                    groups[key] = {}
                groups[key][data_type] = str(f)

        # Build pairs where both books and catalogue exist
        pairs = []
        for ts, files in sorted(groups.items()):
            if "books" in files and "catalogue" in files:
                pairs.append(SnapshotPair(
                    date=date,
                    timestamp=ts,
                    books_path=files["books"],
                    catalogue_path=files["catalogue"],
                ))
        return pairs

    def _read_local(self, path: str) -> list[dict]:
        entries = []
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
        return entries

    # ── Google Cloud Storage ──

    def _list_dates_gcs(self) -> list[str]:
        dates = set()
        bucket = self.gcs_client.bucket(self.bucket_name)
        blobs = bucket.list_blobs(prefix="betfair-live_7_")
        for blob in blobs:
            parsed = parse_filename(blob.name)
            if parsed:
                dates.add(parsed[0])
        return list(dates)

    def _list_snapshots_gcs(self, date: str) -> list[SnapshotPair]:
        bucket = self.gcs_client.bucket(self.bucket_name)
        prefix = f"betfair-live_7_{date}_"
        blobs = bucket.list_blobs(prefix=prefix)

        groups: dict[str, dict[str, str]] = {}
        for blob in blobs:
            parsed = parse_filename(blob.name)
            if parsed and parsed[0] == date:
                _, data_type, file_time = parsed
                if file_time not in groups:
                    groups[file_time] = {}
                groups[file_time][data_type] = blob.name

        pairs = []
        for ts, files in sorted(groups.items()):
            if "books" in files and "catalogue" in files:
                pairs.append(SnapshotPair(
                    date=date,
                    timestamp=ts,
                    books_path=files["books"],
                    catalogue_path=files["catalogue"],
                ))
        return pairs

    def _read_gcs(self, blob_name: str) -> list[dict]:
        bucket = self.gcs_client.bucket(self.bucket_name)
        blob = bucket.blob(blob_name)
        content = blob.download_as_text()
        entries = []
        for line in content.strip().split("\n"):
            if line:
                entries.append(json.loads(line))
        return entries
