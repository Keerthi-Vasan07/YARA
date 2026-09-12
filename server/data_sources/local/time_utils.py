"""
Time parsing and temporal resolution detection utilities for YARA.
Extracts timestamps, computes sampling deltas, and classifies datasets.
"""

from typing import List, Tuple, Optional, Any
import numpy as np
import pandas as pd
from datetime import datetime, timezone
from .common_model import TimeAxisInfo, TemporalResolution


def to_iso_string(dt_val: Any) -> str:
    """Converts diverse datetime types (numpy.datetime64, pandas.Timestamp, cftime, str) to ISO-8601 string."""
    if dt_val is None:
        return ""
    if isinstance(dt_val, str):
        # Validate or standardize
        try:
            return pd.to_datetime(dt_val).isoformat()
        except Exception:
            return dt_val

    # Handle pandas / numpy datetime
    try:
        ts = pd.to_datetime(dt_val)
        if hasattr(ts, "tz") and ts.tz is not None:
            ts = ts.tz_convert("UTC")
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # Handle cftime or objects with year, month, day, hour, minute, second
    if hasattr(dt_val, "year") and hasattr(dt_val, "month") and hasattr(dt_val, "day"):
        h = getattr(dt_val, "hour", 0)
        m = getattr(dt_val, "minute", 0)
        s = getattr(dt_val, "second", 0)
        return f"{dt_val.year:04d}-{dt_val.month:02d}-{dt_val.day:02d}T{h:02d}:{m:02d}:{s:02d}Z"

    return str(dt_val)


def analyze_time_axis(time_values: Any, dim_name: str = "time") -> TimeAxisInfo:
    """
    Parses time coordinate values, determines ISO strings, start/end dates,
    and classifies temporal resolution.
    """
    if time_values is None:
        return TimeAxisInfo(
            dim_name=dim_name,
            timestamps=[],
            resolution=TemporalResolution.SINGLE,
            count=0
        )

    # Flatten if multi-dim
    vals = np.asarray(time_values).ravel()
    if len(vals) == 0:
        return TimeAxisInfo(
            dim_name=dim_name,
            timestamps=[],
            resolution=TemporalResolution.SINGLE,
            count=0
        )

    iso_list = [to_iso_string(v) for v in vals]
    count = len(iso_list)

    if count == 1:
        return TimeAxisInfo(
            dim_name=dim_name,
            timestamps=iso_list,
            resolution=TemporalResolution.SINGLE,
            step_seconds=None,
            start_time=iso_list[0],
            end_time=iso_list[0],
            count=1
        )

    # Convert to pandas timestamps to compute differences
    try:
        parsed_dates = pd.to_datetime(iso_list)
        diffs = np.diff(parsed_dates.values).astype("timedelta64[s]").astype(float)
        
        if len(diffs) == 0:
            avg_step = None
            resolution = TemporalResolution.SINGLE
        else:
            avg_step = float(np.median(diffs))
            step_std = float(np.std(diffs))
            is_regular = (step_std / (avg_step + 1e-6)) < 0.15

            if not is_regular and (avg_step < 2500000):  # not regular monthly/yearly
                resolution = TemporalResolution.IRREGULAR
            elif avg_step < 1800:
                resolution = TemporalResolution.SUB_HOURLY
            elif 1800 <= avg_step <= 5400:  # ~1 hour
                resolution = TemporalResolution.HOURLY
            elif 5400 < avg_step <= 18000:  # ~3-4 hours
                resolution = TemporalResolution.THREE_HOURLY
            elif 18000 < avg_step <= 120000:  # ~1 day
                resolution = TemporalResolution.DAILY
            elif 120000 < avg_step <= 3000000:  # ~1 month
                resolution = TemporalResolution.MONTHLY
            else:
                resolution = TemporalResolution.IRREGULAR

        return TimeAxisInfo(
            dim_name=dim_name,
            timestamps=iso_list,
            resolution=resolution,
            step_seconds=avg_step,
            start_time=iso_list[0],
            end_time=iso_list[-1],
            count=count
        )
    except Exception:
        # Fallback if dates cannot be parsed into timedeltas
        return TimeAxisInfo(
            dim_name=dim_name,
            timestamps=iso_list,
            resolution=TemporalResolution.IRREGULAR,
            step_seconds=None,
            start_time=iso_list[0] if iso_list else None,
            end_time=iso_list[-1] if iso_list else None,
            count=count
        )
