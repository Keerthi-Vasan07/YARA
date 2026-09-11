"""
Time Utilities.

Functions for extracting and parsing time axes from scientific datasets.
"""

from typing import Optional, Tuple, List, Union
from datetime import datetime, timedelta
import numpy as np
import xarray as xr


def parse_cf_time(
    time_values: np.ndarray,
    units: Optional[str] = None,
) -> Tuple[Optional[np.ndarray], Optional[datetime], Optional[datetime]]:
    """
    Parse CF-convention time coordinates.
    
    Args:
        time_values: Numeric time values
        units: Time units string (e.g., 'days since 1970-01-01')
        
    Returns:
        Tuple of (datetime_array, min_time, max_time)
    """
    if time_values is None or len(time_values) == 0:
        return None, None, None
    
    # If already datetime objects, return as-is
    if isinstance(time_values[0], datetime):
        times = np.array(time_values)
        return times, np.min(times), np.max(times)
    
    # Try to parse using xarray's cftime
    try:
        import cftime
        
        if units:
            # Parse CF convention
            times = []
            for val in time_values:
                dt = cftime.num2date(val, units)
                times.append(dt)
            times_np = np.array(times)
            return times_np, np.min(times_np), np.max(times_np)
    except ImportError:
        pass
    except Exception:
        pass
    
    # Fallback: try common epoch conversions
    try:
        # Check if units contain epoch info
        if units:
            if 'seconds since' in units:
                epoch_str = units.split('since')[1].strip()
                epoch = _parse_epoch(epoch_str)
                times = [epoch + timedelta(seconds=float(v)) for v in time_values]
            elif 'minutes since' in units:
                epoch_str = units.split('since')[1].strip()
                epoch = _parse_epoch(epoch_str)
                times = [epoch + timedelta(minutes=float(v)) for v in time_values]
            elif 'hours since' in units:
                epoch_str = units.split('since')[1].strip()
                epoch = _parse_epoch(epoch_str)
                times = [epoch + timedelta(hours=float(v)) for v in time_values]
            elif 'days since' in units:
                epoch_str = units.split('since')[1].strip()
                epoch = _parse_epoch(epoch_str)
                times = [epoch + timedelta(days=float(v)) for v in time_values]
            else:
                # Unknown units, return numeric
                return time_values, float(np.min(time_values)), float(np.max(time_values))
            
            times_np = np.array(times)
            return times_np, np.min(times_np), np.max(times_np)
    except Exception:
        pass
    
    # Last resort: return numeric values
    return time_values, float(np.min(time_values)), float(np.max(time_values))


def _parse_epoch(epoch_str: str) -> datetime:
    """Parse an epoch date string."""
    epoch_str = epoch_str.strip()
    
    # Common formats
    formats = [
        '%Y-%m-%d',
        '%Y-%m-%d %H:%M:%S',
        '%Y/%m/%d',
        '%d-%m-%Y',
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(epoch_str, fmt)
        except ValueError:
            continue
    
    # Default to Unix epoch
    return datetime(1970, 1, 1)


def extract_time_axis(ds: xr.Dataset) -> Tuple[Optional[np.ndarray], Optional[str], Optional[datetime], Optional[datetime]]:
    """
    Extract time axis from an xarray Dataset.
    
    Args:
        ds: xarray Dataset
        
    Returns:
        Tuple of (time_values, units, min_time, max_time)
    """
    time_names = ['time', 't', 'datetime', 'date_time']
    
    for name in time_names:
        if name in ds.coords:
            coord = ds.coords[name]
            time_values = coord.values
            units = coord.attrs.get('units', '')
            
            parsed, time_min, time_max = parse_cf_time(time_values, units)
            return parsed, units, time_min, time_max
    
    # Try standard_name
    for coord_name in ds.coords:
        if ds.coords[coord_name].attrs.get('standard_name') == 'time':
            coord = ds.coords[coord_name]
            time_values = coord.values
            units = coord.attrs.get('units', '')
            
            parsed, time_min, time_max = parse_cf_time(time_values, units)
            return parsed, units, time_min, time_max
    
    return None, None, None, None


def detect_temporal_resolution(time_axis: np.ndarray) -> Optional[str]:
    """
    Detect the temporal resolution of a time axis.
    
    Args:
        time_axis: Array of datetime objects
        
    Returns:
        Resolution string ('hourly', 'daily', 'monthly', etc.) or None
    """
    if time_axis is None or len(time_axis) < 2:
        return None
    
    # Calculate time differences
    if isinstance(time_axis[0], datetime):
        diffs = []
        for i in range(1, min(len(time_axis), 10)):
            diff = (time_axis[i] - time_axis[i-1]).total_seconds()
            diffs.append(diff)
        
        if not diffs:
            return 'single'
        
        avg_diff = np.mean(diffs)
        
        # Classify resolution
        if avg_diff < 60:
            return 'sub-minute'
        elif avg_diff < 3600:
            return 'minutely'
        elif avg_diff < 7200:
            return 'hourly'
        elif avg_diff < 86400 * 1.5:
            return 'daily'
        elif avg_diff < 86400 * 8:
            return '3-hourly'
        elif avg_diff < 86400 * 31:
            return 'weekly'
        elif avg_diff < 86400 * 62:
            return 'monthly'
        else:
            return 'yearly'
    
    return None


def format_time_axis_iso(time_axis: np.ndarray) -> List[str]:
    """
    Format a time axis as ISO format strings.
    
    Args:
        time_axis: Array of datetime objects or numeric values
        
    Returns:
        List of ISO format strings
    """
    if time_axis is None or len(time_axis) == 0:
        return []
    
    result = []
    for t in time_axis:
        if isinstance(t, datetime):
            result.append(t.isoformat())
        elif isinstance(t, np.datetime64):
            result.append(str(t))
        else:
            result.append(str(t))
    
    return result
