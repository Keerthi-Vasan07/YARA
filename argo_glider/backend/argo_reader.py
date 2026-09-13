try:
    import truststore
    truststore.inject_into_ssl()
except ImportError:
    pass

from dataclasses import dataclass, field
from datetime import datetime, timezone
import io
import threading
from typing import Optional

import pandas as pd
import requests
import urllib3

from .config import (
    ERDDAP_BASE_URL,
    ERDDAP_VARIABLES,
    DATA_START_DATE,
    SURFACE_PRESSURE_MAX,
    MAX_TOTAL_OBSERVATIONS,
    MAX_OBSERVATIONS_PER_FLOAT,
    ARGO_CACHE_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
)


@dataclass
class FloatObservation:
    lat: float
    lon: float
    time: str
    temperature: Optional[float] = None
    salinity: Optional[float] = None
    pressure: Optional[float] = None
    cycle: Optional[int] = None
    index: int = 0


@dataclass
class FloatTrajectory:
    float_id: str
    source: str = "INCOIS ERDDAP"
    points: list[FloatObservation] = field(default_factory=list)


_CACHE = {
    "timestamp": None,
    "data": [],
}
_LOCK = threading.Lock()


def _parse_float(v):
    if v is None or pd.isna(v):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _parse_int(v):
    if v is None or pd.isna(v):
        return None
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _fetch_incois_argo() -> list[FloatTrajectory]:
    query_vars = ",".join(ERDDAP_VARIABLES)
    url = f"{ERDDAP_BASE_URL}.csv?{query_vars}&time>={DATA_START_DATE}&PRES<={SURFACE_PRESSURE_MAX}&orderBy(%22PLATFORM_NUMBER,time%22)"

    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        resp.raise_for_status()
    except (requests.exceptions.SSLError, Exception):
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, verify=False)
        resp.raise_for_status()

    # ERDDAP CSV has row 0 as header, row 1 as units
    df = pd.read_csv(io.StringIO(resp.text), skiprows=[1])

    if df.empty:
        return []

    # Rename columns to standard lowercase
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if "platform" in cl:
            col_map[c] = "platform_number"
        elif cl == "time":
            col_map[c] = "time"
        elif "lat" in cl:
            col_map[c] = "latitude"
        elif "lon" in cl:
            col_map[c] = "longitude"
        elif "temp" in cl:
            col_map[c] = "temp"
        elif "psal" in cl or "sal" in cl:
            col_map[c] = "psal"
        elif "pres" in cl:
            col_map[c] = "pres"
        elif "cycle" in cl:
            col_map[c] = "cycle_number"

    df = df.rename(columns=col_map)

    # Filter invalid coords
    if "latitude" not in df.columns or "longitude" not in df.columns:
        return []

    df = df.dropna(subset=["latitude", "longitude"])
    df = df[
        (df["latitude"] >= -90)
        & (df["latitude"] <= 90)
        & (df["longitude"] >= -180)
        & (df["longitude"] <= 180)
    ]

    if MAX_TOTAL_OBSERVATIONS and len(df) > MAX_TOTAL_OBSERVATIONS:
        df = df.head(MAX_TOTAL_OBSERVATIONS)

    platform_col = "platform_number" if "platform_number" in df.columns else df.columns[0]

    trajectories = []
    for platform_id, group in df.groupby(platform_col):
        if MAX_OBSERVATIONS_PER_FLOAT and len(group) > MAX_OBSERVATIONS_PER_FLOAT:
            group = group.tail(MAX_OBSERVATIONS_PER_FLOAT)

        points = []
        for idx, row in enumerate(group.itertuples()):
            time_str = str(getattr(row, "time", "")) if pd.notna(getattr(row, "time", None)) else ""
            points.append(
                FloatObservation(
                    lat=float(row.latitude),
                    lon=float(row.longitude),
                    time=time_str,
                    temperature=_parse_float(getattr(row, "temp", None)),
                    salinity=_parse_float(getattr(row, "psal", None)),
                    pressure=_parse_float(getattr(row, "pres", None)),
                    cycle=_parse_int(getattr(row, "cycle_number", None)),
                    index=idx,
                )
            )

        if points:
            trajectories.append(
                FloatTrajectory(
                    float_id=str(platform_id),
                    source="INCOIS ERDDAP",
                    points=points,
                )
            )

    return trajectories


def get_float_trajectories(force_refresh: bool = False, limit: Optional[int] = None) -> list[FloatTrajectory]:
    now = datetime.now(timezone.utc)

    with _LOCK:
        if (
            not force_refresh
            and _CACHE["timestamp"] is not None
            and (now - _CACHE["timestamp"]).total_seconds() < ARGO_CACHE_SECONDS
        ):
            data = _CACHE["data"]
        else:
            try:
                data = _fetch_incois_argo()
                _CACHE["data"] = data
                _CACHE["timestamp"] = now
            except Exception as e:
                print(f"[ArgoReader] Error fetching INCOIS ERDDAP: {e}")
                data = _CACHE["data"] if _CACHE["data"] else []

    if limit and limit > 0:
        return data[:limit]
    return data
