"""
Copernicus Marine remote data engine for YARA.

IMPORTANT:
- Uses copernicusmarine.open_dataset() for Copernicus access.
- Does not download the global 179 TB dataset.
- Applies variable/time/spatial/depth subsetting before .load().
- Handles both 4-D variables and surface 2-D fields.
- Uses matplotlib.colormaps.get_cmap-compatible API to avoid the
  matplotlib.cm.get_cmap removal error seen in the previous server.
"""

from __future__ import annotations

import io
import logging
import math
import re
from functools import lru_cache
from typing import Any, Dict, Optional

import numpy as np
import matplotlib
from matplotlib import colormaps
from PIL import Image

try:
    import xarray as xr
    HAS_XARRAY = True
except ImportError:
    xr = None
    HAS_XARRAY = False

try:
    import copernicusmarine
    HAS_COPERNICUS = True
except ImportError:
    copernicusmarine = None
    HAS_COPERNICUS = False

logger = logging.getLogger(__name__)

def _require_dependencies():
    if not HAS_XARRAY:
        raise RuntimeError("xarray is not installed")
    if not HAS_COPERNICUS:
        raise RuntimeError("copernicusmarine is not installed")

def _safe_close(ds):
    try:
        ds.close()
    except Exception:
        pass

@lru_cache(maxsize=16)
def _open_dataset_cached(dataset_id: str, variable: str):
    _require_dependencies()
    logger.info("[COPERNICUS] Opening dataset=%s variable=%s", dataset_id, variable)
    return copernicusmarine.open_dataset(
        dataset_id=dataset_id,
        variables=[variable],
    )

def open_remote_dataset(
    variable: str,
    cfg: Dict[str, Any],
    *,
    minimum_longitude: float | None = None,
    maximum_longitude: float | None = None,
    minimum_latitude: float | None = None,
    maximum_latitude: float | None = None,
    minimum_depth: float | None = None,
    maximum_depth: float | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
):
    _require_dependencies()
    kwargs: Dict[str, Any] = {
        "dataset_id": cfg["dataset_id"],
        "variables": [variable],
    }
    optional = {
        "minimum_longitude": minimum_longitude,
        "maximum_longitude": maximum_longitude,
        "minimum_latitude": minimum_latitude,
        "maximum_latitude": maximum_latitude,
        "minimum_depth": minimum_depth,
        "maximum_depth": maximum_depth,
        "start_datetime": start_datetime,
        "end_datetime": end_datetime,
    }
    kwargs.update({k: v for k, v in optional.items() if v is not None})
    logger.info("[COPERNICUS] subset request=%s", kwargs)
    return copernicusmarine.open_dataset(**kwargs)

def inspect_dataset_metadata(variable: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    # IMPORTANT: ds comes from lru_cache — do NOT close it.
    ds = _open_dataset_cached(cfg["dataset_id"], variable)
    if variable not in ds.data_vars:
        raise ValueError(
            f"Variable '{variable}' not returned by dataset. "
            f"Available: {list(ds.data_vars)}"
        )
    da = ds[variable]
    result = {
        "variable_key": variable,
        "dataset_id": cfg["dataset_id"],
        "display_name": cfg["display_name"],
        "units": cfg["units_display"],
        "source": cfg["source"],
        "provider": cfg["provider"],
        "description": cfg["description"],
        "opendap_url": cfg["opendap_url"],
        "variable_name": variable,
        "variable_attrs": {str(k): str(v) for k, v in da.attrs.items()},
        "dimensions": list(da.dims),
        "shape": [int(x) for x in da.shape],
        "is_3d": bool(cfg.get("is_3d", False)),
        "vmin": cfg["vmin"],
        "vmax": cfg["vmax"],
        "log_scale": cfg.get("log_scale", False),
        "colormap": cfg.get("colormap", "viridis"),
        "spatial_resolution_deg": cfg["spatial_resolution_deg"],
    }
    for name in ("latitude", "lat"):
        if name in ds.coords:
            result["lat_dim"] = name
            result["n_lat"] = int(ds[name].size)
            result["lat_range"] = [
                float(np.nanmin(ds[name].values)),
                float(np.nanmax(ds[name].values)),
            ]
            break
    for name in ("longitude", "lon"):
        if name in ds.coords:
            result["lon_dim"] = name
            result["n_lon"] = int(ds[name].size)
            result["lon_range"] = [
                float(np.nanmin(ds[name].values)),
                float(np.nanmax(ds[name].values)),
            ]
            break
    for name in ("time", "datetime", "date"):
        if name in ds.coords:
            result["time_dim"] = name
            vals = np.asarray(ds[name].values)
            result["n_times"] = int(vals.size)
            if vals.size:
                result["time_range"] = [str(vals.flat[0]), str(vals.flat[-1])]
            break
    return result

def get_available_times(variable: str, cfg: Dict[str, Any]) -> list[str]:
    # IMPORTANT: _open_dataset_cached uses lru_cache — do NOT close the returned
    # dataset object, or the cache entry becomes a closed/invalid handle.
    ds = _open_dataset_cached(cfg["dataset_id"], variable)
    name = next((n for n in ("time", "datetime", "date") if n in ds.coords), None)
    if not name:
        return []
    values = np.asarray(ds[name].values)
    out = []
    for v in values.flat:
        try:
            out.append(np.datetime_as_string(np.datetime64(v), unit="s"))
        except Exception:
            out.append(str(v))
    return out

@lru_cache(maxsize=64)
def _get_latest_time_cached(dataset_id: str, variable: str) -> Optional[str]:
    """Cache the latest timestamp per (dataset, variable) to avoid re-opening
    the full global dataset on every render_to_png call."""
    ds = _open_dataset_cached(dataset_id, variable)
    name = next((n for n in ("time", "datetime", "date") if n in ds.coords), None)
    if not name or ds[name].size == 0:
        return None
    try:
        return np.datetime_as_string(np.datetime64(ds[name].values[-1]), unit="s")
    except Exception:
        return str(ds[name].values[-1])

def get_latest_time(variable: str, cfg: Dict[str, Any]) -> Optional[str]:
    return _get_latest_time_cached(cfg["dataset_id"], variable)

def _coord_name(ds, candidates):
    for name in candidates:
        if name in ds.coords:
            return name
    for name in ds.variables:
        low = name.lower()
        for candidate in candidates:
            if candidate.lower() == low:
                return name
    return None

def _time_select(ds, requested: str | None):
    name = _coord_name(ds, ("time", "datetime", "date"))
    if not name or ds[name].size == 0:
        return ds, None
    if requested in (None, "", "latest"):
        actual = ds[name].values[-1]
    else:
        try:
            target = np.datetime64(requested)
            actual = ds[name].sel({name: target}, method="nearest").values
        except Exception:
            actual = ds[name].values[-1]
    return ds.sel({name: actual}), str(actual)

def _slice_for_coord(coord, low, high):
    values = np.asarray(coord.values)
    if values.size < 2:
        return slice(low, high)
    ascending = bool(values[0] <= values[-1])
    return slice(low, high) if ascending else slice(high, low)

def _normalise_lon(lon: float) -> float:
    x = ((float(lon) + 180.0) % 360.0) - 180.0
    return x

def _subset(
    ds,
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    requested_date: str | None,
    depth_min: float | None = None,
    depth_max: float | None = None,
):
    lat_name = _coord_name(ds, ("latitude", "lat"))
    lon_name = _coord_name(ds, ("longitude", "lon"))
    if lat_name:
        ds = ds.sel({lat_name: _slice_for_coord(ds[lat_name], lat_min, lat_max)})
    if lon_name:
        # Most Copernicus grids are -180..180. Handle 0..360 safely.
        lon_values = np.asarray(ds[lon_name].values)
        qmin, qmax = lon_min, lon_max
        if lon_values.size and np.nanmax(lon_values) > 180:
            qmin, qmax = lon_min % 360, lon_max % 360
        ds = ds.sel({lon_name: _slice_for_coord(ds[lon_name], qmin, qmax)})
    depth_name = _coord_name(ds, ("depth", "deptht", "lev"))
    if depth_name and depth_min is not None and depth_max is not None:
        ds = ds.sel({depth_name: _slice_for_coord(ds[depth_name], depth_min, depth_max)})
    ds, matched = _time_select(ds, requested_date)
    return ds, matched

def _downsample(da, lat_name: str | None, lon_name: str | None, max_pixels: int):
    if not lat_name or not lon_name:
        return da
    try:
        ny = int(da.sizes[lat_name])
        nx = int(da.sizes[lon_name])
        if ny <= max_pixels and nx <= max_pixels:
            return da
        factor = max(1, int(math.ceil(max(ny, nx) / max_pixels)))
        return da.isel({lat_name: slice(None, None, factor),
                        lon_name: slice(None, None, factor)})
    except Exception:
        return da

# UI-compatible named palettes. These are intentionally kept here as
# visualization definitions only: they never alter the scientific values.
_NAMED_COLOR_STOPS = {
    "thermal": [
        (0.00, "#0a1929"), (0.17, "#1565c0"), (0.34, "#00acc1"),
        (0.50, "#66bb6a"), (0.67, "#cddc39"), (0.83, "#ff9800"),
        (1.00, "#f44336"),
    ],
    "viridis": [
        (0.00, "#440154"), (0.25, "#3b528b"), (0.50, "#21918c"),
        (0.75, "#5ec962"), (1.00, "#fde725"),
    ],
    "plasma": [
        (0.00, "#0d0887"), (0.25, "#7e03a8"), (0.50, "#cc4778"),
        (0.75, "#f89540"), (1.00, "#f0f921"),
    ],
    "coolwarm": [
        (0.00, "#3b4cc0"), (0.20, "#7092d0"), (0.40, "#c9d7e9"),
        (0.60, "#f0cdba"), (0.80, "#d67163"), (1.00, "#b40426"),
    ],
}

def _parse_hex_color(value: str) -> tuple[int, int, int]:
    color = str(value).strip()
    if color.startswith("#"):
        color = color[1:]
    if len(color) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", color):
        raise ValueError(f"Invalid gradient color '{value}'")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))

def _parse_gradient(value: str):
    """Parse the UI's gradient(#rrggbb@0.0,#rrggbb@1.0) format."""
    if not isinstance(value, str) or not value.startswith("gradient(") or not value.endswith(")"):
        return None
    content = value[len("gradient("):-1].strip()
    if not content:
        raise ValueError("Custom gradient is empty")

    stops = []
    for part in content.split(","):
        if "@" not in part:
            raise ValueError(f"Invalid gradient stop '{part}'")
        color_text, position_text = part.rsplit("@", 1)
        try:
            position = float(position_text)
        except ValueError as exc:
            raise ValueError(f"Invalid gradient position '{position_text}'") from exc
        if not 0.0 <= position <= 1.0:
            raise ValueError("Gradient stop positions must be between 0 and 1")
        stops.append((position, _parse_hex_color(color_text)))

    if len(stops) < 2:
        raise ValueError("Custom gradient requires at least two stops")
    stops.sort(key=lambda item: item[0])
    if stops[0][0] != 0.0 or stops[-1][0] != 1.0:
        raise ValueError("Custom gradient must have stops at positions 0 and 1")
    if any(stops[i][0] == stops[i - 1][0] for i in range(1, len(stops))):
        raise ValueError("Gradient stop positions must be unique")
    return stops

def _stops_to_rgba(norm: np.ndarray, stops):
    """Vectorized linear RGB interpolation over arbitrary color stops."""
    positions = np.asarray([p for p, _ in stops], dtype=np.float64)
    colors = np.asarray([c for _, c in stops], dtype=np.float64)
    flat = np.clip(norm, 0.0, 1.0).reshape(-1)

    idx = np.searchsorted(positions, flat, side="right") - 1
    idx = np.clip(idx, 0, len(positions) - 2)
    left_p = positions[idx]
    right_p = positions[idx + 1]
    ratio = np.divide(
        flat - left_p,
        right_p - left_p,
        out=np.zeros_like(flat),
        where=(right_p - left_p) != 0,
    )
    rgb = colors[idx] * (1.0 - ratio[:, None]) + colors[idx + 1] * ratio[:, None]
    return rgb.reshape((*norm.shape, 3))

def _resolve_color_stops(cmap_name: str | None, cfg: Dict[str, Any]):
    requested = cmap_name or cfg.get("colormap", "viridis")
    custom = _parse_gradient(requested)
    if custom is not None:
        return custom

    named = _NAMED_COLOR_STOPS.get(str(requested).lower())
    if named is not None:
        return [(position, _parse_hex_color(color)) for position, color in named]

    # Preserve support for any standard matplotlib palette.
    cmap = colormaps.get_cmap(requested)
    sample = np.linspace(0.0, 1.0, 256)
    rgba = cmap(sample)
    return [(float(p), tuple((row[:3] * 255).astype(np.uint8))) for p, row in zip(sample, rgba)]

def _render_array_to_png(values, cfg, *, vmin=None, vmax=None, cmap_name=None):
    arr = np.asarray(values, dtype=np.float64).squeeze()
    while arr.ndim > 2:
        arr = arr[0]
    if arr.ndim != 2:
        raise RuntimeError(f"Expected a 2-D render slice, got shape {arr.shape}")
    arr = np.flipud(arr)
    valid = np.isfinite(arr)
    lo = float(cfg["vmin"] if vmin is None else vmin)
    hi = float(cfg["vmax"] if vmax is None else vmax)
    if not np.isfinite(lo) or not np.isfinite(hi):
        raise ValueError("Color scale limits must be finite")
    if not hi > lo:
        hi = lo + 1.0

    # IMPORTANT: normalization and color mapping happen AFTER the real
    # Copernicus numeric values have been retrieved. The source data is never
    # changed by a palette/color-wheel operation.
    norm = np.clip((arr - lo) / (hi - lo), 0.0, 1.0)
    stops = _resolve_color_stops(cmap_name, cfg)
    rgb = _stops_to_rgba(np.nan_to_num(norm, nan=0.0), stops)
    rgba = np.empty((*arr.shape, 4), dtype=np.uint8)
    rgba[..., :3] = np.clip(rgb, 0, 255).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buf, format="PNG", optimize=True)
    return buf.getvalue()

def render_to_png(
    variable: str,
    cfg: Dict[str, Any],
    date: str,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    max_pixels: int = 2048,
    colormap: str | None = None,
    vmin: float | None = None,
    vmax: float | None = None,
):
    target_date = date
    if target_date in (None, "", "latest"):
        latest_val = get_latest_time(variable, cfg)
        if latest_val:
            target_date = latest_val

    # CRITICAL PERFORMANCE FIX:
    # For 3D (depth-dependent) variables, restrict to the shallowest level
    # BEFORE opening the dataset. Without this, copernicusmarine downloads all
    # 50 depth levels at full global resolution (~1.7 GB), causing the request
    # to hang indefinitely. Surface-only rendering needs only the top level.
    is_3d = bool(cfg.get("is_3d", False))
    kwargs_depth: Dict[str, Any] = {}
    if is_3d:
        kwargs_depth = {"minimum_depth": 0.0, "maximum_depth": 1.0}

    # Open the requested spatial/time/depth subset through the Toolbox.
    ds = open_remote_dataset(
        variable, cfg,
        minimum_longitude=lon_min, maximum_longitude=lon_max,
        minimum_latitude=lat_min, maximum_latitude=lat_max,
        start_datetime=None if target_date in (None, "", "latest") else str(target_date)[:19],
        end_datetime=None if target_date in (None, "", "latest") else str(target_date)[:19],
        **kwargs_depth,
    )
    try:
        ds, matched = _time_select(ds, target_date)
        da = ds[variable]
        lat_name = _coord_name(ds, ("latitude", "lat"))
        lon_name = _coord_name(ds, ("longitude", "lon"))
        da = _downsample(da, lat_name, lon_name, max_pixels)
        # For depth-dependent fields, surface rendering uses the shallowest
        # available depth unless the caller supplies a depth-specific endpoint.
        depth_name = _coord_name(ds, ("depth", "deptht", "lev"))
        if depth_name and depth_name in da.dims:
            da = da.isel({depth_name: 0})
        values = da.load().values
        png = _render_array_to_png(values, cfg, vmin=vmin, vmax=vmax,
                                   cmap_name=colormap)
        return png, matched or target_date or date, {
            "west": float(lon_min), "south": float(lat_min),
            "east": float(lon_max), "north": float(lat_max),
            "width": int(np.asarray(values).shape[-1]),
            "height": int(np.asarray(values).shape[-2]),
        }
    finally:
        _safe_close(ds)

def query_point(
    variable: str,
    cfg: Dict[str, Any],
    date: str,
    lon: float,
    lat: float,
):
    target_date = date
    if target_date in (None, "", "latest"):
        latest_val = get_latest_time(variable, cfg)
        if latest_val:
            target_date = latest_val

    # Small remote subset around the clicked location.
    lon = _normalise_lon(lon)
    is_3d = bool(cfg.get("is_3d", False))
    kwargs_depth: Dict[str, Any] = {}
    if is_3d:
        kwargs_depth = {"minimum_depth": 0.0, "maximum_depth": 1.0}

    ds = open_remote_dataset(
        variable, cfg,
        minimum_longitude=max(-180.0, lon - 0.1),
        maximum_longitude=min(180.0, lon + 0.1),
        minimum_latitude=max(-90.0, lat - 0.1),
        maximum_latitude=min(90.0, lat + 0.1),
        start_datetime=None if target_date in (None, "", "latest") else str(target_date)[:19],
        end_datetime=None if target_date in (None, "", "latest") else str(target_date)[:19],
        **kwargs_depth,
    )
    try:
        ds, matched = _time_select(ds, target_date)
        da = ds[variable]
        lat_name = _coord_name(ds, ("latitude", "lat"))
        lon_name = _coord_name(ds, ("longitude", "lon"))
        time_name = _coord_name(ds, ("time", "datetime", "date"))
        if lat_name:
            da = da.sel({lat_name: lat}, method="nearest")
        if lon_name:
            qlon = lon
            vals = np.asarray(ds[lon_name].values)
            if vals.size and np.nanmax(vals) > 180:
                qlon = lon % 360
            da = da.sel({lon_name: qlon}, method="nearest")
        result = {
            "variable": variable,
            "variable_name": cfg["display_name"],
            "units": cfg["units_display"],
            "requested_lat": float(lat),
            "requested_lon": float(lon),
            "dataset_id": cfg["dataset_id"],
            "provider": cfg["provider"],
            "source": cfg["source"],
            "date_requested": date,
            "date_matched": matched or date,
        }
        if lat_name and lat_name in da.coords:
            result["matched_lat"] = float(np.asarray(da[lat_name].values).squeeze())
        if lon_name and lon_name in da.coords:
            mlon = float(np.asarray(da[lon_name].values).squeeze())
            result["matched_lon"] = mlon - 360 if mlon > 180 else mlon
        depth_name = _coord_name(ds, ("depth", "deptht", "lev"))
        if depth_name and depth_name in da.dims:
            vals = np.asarray(da.load().values).squeeze()
            result["depth_values"] = [float(x) for x in np.asarray(ds[depth_name].values).flat]
            result["values"] = [
                None if not np.isfinite(x) else float(x)
                for x in np.asarray(vals).flat
            ]
        else:
            val = np.asarray(da.load().values).squeeze()
            x = val.item() if np.asarray(val).size else np.nan
            result["value"] = None if not np.isfinite(x) else float(x)
        if time_name and time_name in da.coords:
            result["date"] = str(np.asarray(da[time_name].values).squeeze())
        return result
    finally:
        _safe_close(ds)
