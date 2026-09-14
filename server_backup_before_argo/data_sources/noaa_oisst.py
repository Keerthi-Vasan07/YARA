import time
import os
import json
import logging
from datetime import datetime, timedelta
from threading import Lock
from typing import Any, Dict, Optional

import numpy as np
from pydap.client import open_url

from .base import DataSource

logger = logging.getLogger(__name__)

CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "cache", "noaa_oisst")
os.makedirs(CACHE_DIR, exist_ok=True)


class RateLimitError(Exception):
    """Raised when NOAA returns 429 or we are in cooldown."""
    pass


class DateNotAvailableError(Exception):
    """Raised when the requested date is outside the dataset range."""
    pass


class NOAAOISSTSource(DataSource):
    """
    NOAA OISST v2.1 daily high-resolution SST source.

    Data is accessed remotely through OPeNDAP using PyDAP with:
    - Date-based fetching (any date in the dataset)
    - 429 circuit breaker (5-minute cooldown, NO retry on 429)
    - Date-keyed memory + disk caching
    - Stale fallback on transient errors (only if cached data exists for exact date)
    """

    BASE_URL = (
        "https://psl.noaa.gov/thredds/dodsC/"
        "Datasets/noaa.oisst.v2.highres/"
    )

    VARIABLE = "sst"

    # --- Class-level shared state (singleton pattern) ---
    _dataset_cache: Dict[int, Any] = {}  # year -> dataset
    _dataset_lock = Lock()
    _metadata_cache: Optional[Dict] = None
    _metadata_lock = Lock()
    _date_cache: Dict[str, Dict] = {}  # "YYYY-MM-DD" -> result dict
    _date_cache_lock = Lock()

    # 429 circuit breaker
    _cooldown_until: float = 0.0
    _cooldown_lock = Lock()
    COOLDOWN_SECONDS = 300  # 5 minutes

    def __init__(self, url: str | None = None):
        # url parameter kept for backward compatibility but we use year-based URLs
        self._custom_url = url

    def _get_url_for_year(self, year: int) -> str:
        """Get the OPeNDAP URL for a specific year's dataset."""
        if self._custom_url:
            return self._custom_url
        return f"{self.BASE_URL}sst.day.mean.{year}.nc"

    def _check_cooldown(self):
        """Check if we are in 429 cooldown. Raises RateLimitError if so."""
        with NOAAOISSTSource._cooldown_lock:
            if time.time() < NOAAOISSTSource._cooldown_until:
                remaining = int(NOAAOISSTSource._cooldown_until - time.time())
                raise RateLimitError(
                    f"NOAA rate limited. Cooldown active for {remaining}s. "
                    f"Try again after {datetime.fromtimestamp(NOAAOISSTSource._cooldown_until).strftime('%H:%M:%S')}."
                )

    def _set_cooldown(self):
        """Activate 429 cooldown."""
        with NOAAOISSTSource._cooldown_lock:
            NOAAOISSTSource._cooldown_until = time.time() + self.COOLDOWN_SECONDS
            logger.warning(
                f"[SST] 429 cooldown activated for {self.COOLDOWN_SECONDS}s. "
                f"No NOAA requests until {datetime.fromtimestamp(NOAAOISSTSource._cooldown_until).strftime('%H:%M:%S')}."
            )

    def _is_429_error(self, exc: Exception) -> bool:
        """Check if an exception indicates a 429 rate limit."""
        msg = str(exc).lower()
        return "429" in msg or "too many requests" in msg or "rate limit" in msg

    def _open(self, year: int = 2026):
        """
        Open the remote OPeNDAP dataset with locking.
        No retry on 429 — raises RateLimitError immediately.
        Only retries on transient network errors (once).
        """
        self._check_cooldown()

        with NOAAOISSTSource._dataset_lock:
            if year in NOAAOISSTSource._dataset_cache:
                return NOAAOISSTSource._dataset_cache[year]

            url = self._get_url_for_year(year)
            logger.info(f"[SST] Opening NOAA OPeNDAP dataset: {url}")

            try:
                ds = open_url(url)
                _ = ds[self.VARIABLE]
                NOAAOISSTSource._dataset_cache[year] = ds
                return ds
            except Exception as exc:
                if self._is_429_error(exc):
                    self._set_cooldown()
                    raise RateLimitError(f"NOAA returned 429: {exc}")
                # One retry for transient network errors
                logger.warning(f"[SST] First attempt failed: {exc}. Retrying once...")
                time.sleep(2)
                try:
                    ds = open_url(url)
                    _ = ds[self.VARIABLE]
                    NOAAOISSTSource._dataset_cache[year] = ds
                    return ds
                except Exception as exc2:
                    if self._is_429_error(exc2):
                        self._set_cooldown()
                        raise RateLimitError(f"NOAA returned 429: {exc2}")
                    raise exc2

    def is_available(self) -> bool:
        """Check whether NOAA OPeNDAP is reachable."""
        try:
            dataset = self._open(2026)
            return (
                self.VARIABLE in dataset
                and "time" in dataset
                and "lat" in dataset
                and "lon" in dataset
            )
        except RateLimitError:
            return False
        except Exception:
            return False

    def get_metadata(self) -> Dict[str, Any]:
        """Return metadata required by YARA (cached)."""
        with NOAAOISSTSource._metadata_lock:
            if NOAAOISSTSource._metadata_cache is not None:
                logger.info("[SST] Metadata Cache HIT (memory)")
                return NOAAOISSTSource._metadata_cache

            meta_file = os.path.join(CACHE_DIR, "metadata.json")
            if os.path.exists(meta_file):
                try:
                    with open(meta_file, "r") as f:
                        meta = json.load(f)
                    NOAAOISSTSource._metadata_cache = meta
                    logger.info("[SST] Metadata Cache HIT (disk)")
                    return meta
                except Exception as e:
                    logger.warning(f"[SST] Failed to read disk metadata cache: {e}")

            try:
                logger.info("[SST] Fetching NOAA OPeNDAP metadata...")
                dataset = self._open(2026)

                sst = dataset[self.VARIABLE]
                lat = dataset["lat"]
                lon = dataset["lon"]
                time_var = dataset["time"]

                meta = {
                    "source": "NOAA OISST v2.1",
                    "provider": "NOAA",
                    "protocol": "OPeNDAP",
                    "url": self._get_url_for_year(2026),
                    "variable": self.VARIABLE,
                    "dimensions": {
                        "time": len(time_var),
                        "lat": len(lat),
                        "lon": len(lon),
                    },
                    "coordinates": {
                        "latitude": {
                            "name": "lat",
                            "size": len(lat),
                            "first": float(np.asarray(lat[0]).item()),
                            "last": float(np.asarray(lat[-1]).item()),
                        },
                        "longitude": {
                            "name": "lon",
                            "size": len(lon),
                            "first": float(np.asarray(lon[0]).item()),
                            "last": float(np.asarray(lon[-1]).item()),
                        },
                    },
                    "sst": {
                        "name": self.VARIABLE,
                        "units": sst.attributes.get("units", "degC"),
                        "long_name": sst.attributes.get(
                            "long_name",
                            "Sea Surface Temperature",
                        ),
                    },
                    "time": {
                        "size": len(time_var),
                        "first": float(np.asarray(time_var[0]).item()),
                        "last": float(np.asarray(time_var[-1]).item()),
                    },
                }

                NOAAOISSTSource._metadata_cache = meta
                try:
                    with open(meta_file, "w") as f:
                        json.dump(meta, f)
                except Exception as e:
                    logger.warning(f"[SST] Failed to write disk metadata cache: {e}")

                return meta

            except RateLimitError:
                raise
            except Exception as exc:
                if os.path.exists(meta_file):
                    logger.warning(f"[SST] NOAA Error ({exc}). Using stale disk metadata cache.")
                    with open(meta_file, "r") as f:
                        return json.load(f)
                raise exc

    def _date_to_index(self, date_str: str, year: int, dataset) -> int:
        """
        Convert YYYY-MM-DD to a time index in the dataset.
        NOAA OISST daily datasets start on Jan 1 of each year.
        """
        target = datetime.strptime(date_str, "%Y-%m-%d")
        base = datetime(year, 1, 1)
        day_offset = (target - base).days

        n_times = len(dataset["time"])
        if day_offset < 0 or day_offset >= n_times:
            raise DateNotAvailableError(
                f"Date {date_str} is not available in the {year} dataset "
                f"(has {n_times} days, index would be {day_offset})."
            )
        return day_offset

    def get_by_date(self, date_str: str) -> Dict[str, Any]:
        """
        Retrieve SST grid for a specific date.

        Args:
            date_str: Date in YYYY-MM-DD format.

        Returns:
            Dict with SST grid data, coordinates, and statistics.

        Raises:
            RateLimitError: If NOAA is rate-limiting or we are in cooldown.
            DateNotAvailableError: If the date is outside the dataset range.
        """
        # Check memory cache first (no lock needed for read)
        with NOAAOISSTSource._date_cache_lock:
            if date_str in NOAAOISSTSource._date_cache:
                logger.info(f"[SST] Date cache HIT (memory): {date_str}")
                return NOAAOISSTSource._date_cache[date_str]

        # Check disk cache
        cache_file = os.path.join(CACHE_DIR, f"sst_{date_str}.json")
        if os.path.exists(cache_file):
            try:
                with open(cache_file, "r") as f:
                    data = json.load(f)
                with NOAAOISSTSource._date_cache_lock:
                    NOAAOISSTSource._date_cache[date_str] = data
                logger.info(f"[SST] Date cache HIT (disk): {date_str}")
                return data
            except Exception as e:
                logger.warning(f"[SST] Failed to load disk cache for {date_str}: {e}")

        # Fetch from NOAA
        self._check_cooldown()

        year = int(date_str.split("-")[0])
        logger.info(f"[SST] Cache MISS: Fetching SST for {date_str} from NOAA OPeNDAP...")

        try:
            dataset = self._open(year)
            time_index = self._date_to_index(date_str, year, dataset)

            sst = dataset[self.VARIABLE]

            # Single fetch attempt — no retry loop for the data slice
            try:
                values = np.asarray(sst[time_index, :, :]).astype(np.float32)
            except Exception as slice_err:
                if self._is_429_error(slice_err):
                    self._set_cooldown()
                    raise RateLimitError(f"NOAA returned 429 during data fetch: {slice_err}")
                raise slice_err

            values = np.squeeze(values)

            if values.ndim != 2:
                raise ValueError(f"Expected 2D SST grid, got shape {values.shape}")

            missing_value = sst.attributes.get("missing_value", -9.96921e36)

            values = np.where(
                np.isclose(values, missing_value),
                np.nan,
                values,
            )
            values = np.where(
                (values < -3.0) | (values > 45.0),
                np.nan,
                values,
            )

            valid = np.isfinite(values)

            # Standard NOAA OISST coordinate ranges (720 lat, 1440 lon)
            lat_list = [float(-89.875 + i * 0.25) for i in range(720)]
            lon_list = [float(0.125 + i * 0.25) for i in range(1440)]

            result = {
                "source": "NOAA OISST v2.1",
                "provider": "NOAA",
                "protocol": "OPeNDAP",
                "variable": self.VARIABLE,
                "date": date_str,
                "time_index": time_index,
                "latitude": lat_list,
                "longitude": lon_list,
                "values": np.nan_to_num(values, nan=-9999.0).tolist(),
                "missing_value": -9999.0,
                "units": sst.attributes.get("units", "degC"),
                "shape": list(values.shape),
                "statistics": {
                    "valid_points": int(valid.sum()),
                    "min": float(np.nanmin(values)) if np.any(valid) else None,
                    "max": float(np.nanmax(values)) if np.any(valid) else None,
                    "mean": float(np.nanmean(values)) if np.any(valid) else None,
                },
            }

            # Store in memory cache
            with NOAAOISSTSource._date_cache_lock:
                NOAAOISSTSource._date_cache[date_str] = result

            # Store on disk
            try:
                with open(cache_file, "w") as f:
                    json.dump(result, f)
                logger.info(f"[SST] Cached SST for {date_str} to disk.")
            except Exception as e:
                logger.warning(f"[SST] Failed to write disk cache for {date_str}: {e}")

            return result

        except (RateLimitError, DateNotAvailableError):
            raise
        except Exception as exc:
            if self._is_429_error(exc):
                self._set_cooldown()
                raise RateLimitError(f"NOAA returned 429: {exc}")
            # If we have stale cache for this exact date, use it
            if os.path.exists(cache_file):
                logger.warning(f"[SST] NOAA error ({exc}). Using stale cache for {date_str}.")
                with open(cache_file, "r") as f:
                    return json.load(f)
            raise exc

    def get_latest(self) -> Dict[str, Any]:
        """
        Retrieve the latest SST time slice.
        Kept for backward compatibility — delegates to get_by_date with most recent date.
        """
        try:
            # Try to determine the latest available date
            dataset = self._open(2026)
            n_times = len(dataset["time"])
            base = datetime(2026, 1, 1)
            latest_date = (base + timedelta(days=n_times - 1)).strftime("%Y-%m-%d")
            return self.get_by_date(latest_date)
        except (RateLimitError, DateNotAvailableError):
            raise
        except Exception:
            # Fallback: try yesterday's date
            yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            return self.get_by_date(yesterday)
