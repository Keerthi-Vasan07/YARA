"""
Copernicus Marine remote data access for YARA.

Uses:
    copernicusmarine.open_dataset()
    xarray
    dask

Data is requested remotely and subsetted before values are loaded.
"""

from __future__ import annotations

import io
import math
import logging
from functools import lru_cache
from typing import Any, Dict, Tuple, Sequence

import numpy as np
import matplotlib

logger = logging.getLogger(__name__)


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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _require_dependencies():
    if not HAS_XARRAY:
        raise RuntimeError("xarray is not installed")

    if not HAS_COPERNICUS:
        raise RuntimeError(
            "copernicusmarine is not installed"
        )


def _dataset_id(cfg: Dict[str, Any]) -> str:
    return cfg["dataset_id"]


@lru_cache(maxsize=16)
def _open_dataset_cached(
    dataset_id: str,
    variable: str,
):
    """
    Open the Copernicus dataset lazily.

    IMPORTANT:
    This does NOT download the full dataset.
    xarray/Dask keeps the remote arrays lazy.
    """

    _require_dependencies()

    logger.info(
        "[COPERNICUS] Opening dataset=%s variable=%s",
        dataset_id,
        variable,
    )

    ds = copernicusmarine.open_dataset(
        dataset_id=dataset_id,
        variables=[variable],
    )

    return ds


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
    """
    Open only the requested Copernicus subset.

    Latitude bounds are safely clamped to the dataset's actual coordinate
    range so the frontend does not need to know dataset-specific limits.
    """

    _require_dependencies()

    # --- Safe latitude clamping against actual dataset bounds ---
    # The cached dataset gives us the real lat range without a new network call.
    if minimum_latitude is not None or maximum_latitude is not None:
        try:
            cached_ds = _open_dataset_cached(_dataset_id(cfg), variable)
            if "latitude" in cached_ds.coords:
                lat_vals = cached_ds["latitude"].values
                ds_lat_min = float(lat_vals.min())
                ds_lat_max = float(lat_vals.max())
                if minimum_latitude is not None:
                    clamped_min = max(minimum_latitude, ds_lat_min)
                    if clamped_min != minimum_latitude:
                        logger.info(
                            "[COPERNICUS] Clamped minimum_latitude %.2f → %.2f (dataset range)",
                            minimum_latitude, clamped_min,
                        )
                    minimum_latitude = clamped_min
                if maximum_latitude is not None:
                    clamped_max = min(maximum_latitude, ds_lat_max)
                    if clamped_max != maximum_latitude:
                        logger.info(
                            "[COPERNICUS] Clamped maximum_latitude %.2f → %.2f (dataset range)",
                            maximum_latitude, clamped_max,
                        )
                    maximum_latitude = clamped_max
        except Exception as exc:
            logger.debug("[COPERNICUS] Could not clamp lat bounds: %s", exc)

    kwargs: Dict[str, Any] = {
        "dataset_id": _dataset_id(cfg),
        "variables": [variable],
    }

    if minimum_longitude is not None:
        kwargs["minimum_longitude"] = minimum_longitude

    if maximum_longitude is not None:
        kwargs["maximum_longitude"] = maximum_longitude

    if minimum_latitude is not None:
        kwargs["minimum_latitude"] = minimum_latitude

    if maximum_latitude is not None:
        kwargs["maximum_latitude"] = maximum_latitude

    if minimum_depth is not None:
        kwargs["minimum_depth"] = minimum_depth

    if maximum_depth is not None:
        kwargs["maximum_depth"] = maximum_depth

    if start_datetime is not None:
        kwargs["start_datetime"] = start_datetime

    if end_datetime is not None:
        kwargs["end_datetime"] = end_datetime

    logger.info(
        "[COPERNICUS] subset request: %s",
        kwargs,
    )

    return copernicusmarine.open_dataset(**kwargs)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def inspect_dataset_metadata(
    variable: str,
    cfg: Dict[str, Any],
) -> Dict[str, Any]:

    ds = _open_dataset_cached(
        _dataset_id(cfg),
        variable,
    )

    try:
        data = ds[variable]

        dimensions = {}

        for dim in data.dims:
            coord = ds.coords.get(dim)

            info: Dict[str, Any] = {
                "size": int(ds.sizes[dim]),
            }

            if coord is not None:
                try:
                    values = coord.values

                    if values.size:
                        info["min"] = str(values.min())
                        info["max"] = str(values.max())
                except Exception:
                    pass

            dimensions[dim] = info

        return {
            "variable": variable,
            "display_name": cfg["display_name"],
            "dataset_id": cfg["dataset_id"],
            "units": cfg["units"],
            "units_display": cfg["units_display"],
            "dimensions": dimensions,
            "shape": list(data.shape),
            "dtype": str(data.dtype),
            "description": cfg["description"],
            "source": cfg["source"],
            "provider": cfg["provider"],
        }

    finally:
        # Dataset remains cached/lazy.
        pass


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

def get_latest_time(
    variable: str,
    cfg: Dict[str, Any],
) -> str:

    ds = _open_dataset_cached(
        _dataset_id(cfg),
        variable,
    )

    if "time" not in ds.coords:
        raise ValueError(
            f"Dataset for '{variable}' does not contain a time coordinate"
        )

    latest = ds["time"].values[-1]

    return str(np.datetime_as_string(latest, unit="D"))


def get_available_times(
    variable: str,
    cfg: Dict[str, Any],
):

    ds = _open_dataset_cached(
        _dataset_id(cfg),
        variable,
    )

    if "time" not in ds.coords:
        return []

    values = ds["time"].values

    return [
        str(np.datetime_as_string(value, unit="D"))
        for value in values
    ]


# ---------------------------------------------------------------------------
# Date matching
# ---------------------------------------------------------------------------

def _select_date(ds, date: str):
    """
    Select exact date where possible.
    Otherwise select nearest available timestamp.
    """

    if "time" not in ds.coords:
        return ds, None

    requested = np.datetime64(date)

    try:
        selected = ds.sel(
            time=requested,
            method="nearest",
        )

        matched = selected["time"].values

        if np.ndim(matched):
            matched = matched.item()

        matched = str(
            np.datetime_as_string(
                np.datetime64(matched),
                unit="D",
            )
        )

        return selected, matched

    except Exception as exc:
        raise ValueError(
            f"Unable to match date '{date}': {exc}"
        ) from exc


# ---------------------------------------------------------------------------
# Colormap helpers
# ---------------------------------------------------------------------------

# Supported matplotlib palettes exposed to the frontend.  We deliberately use
# matplotlib.colormaps (Matplotlib 3.7+) and never cm.get_cmap(), which was
# removed in newer Matplotlib releases.
BUILTIN_COLORMAPS = {
    "viridis": "viridis",
    "plasma": "plasma",
    "inferno": "inferno",
    "magma": "magma",
    "cividis": "cividis",
    "turbo": "turbo",
    "coolwarm": "coolwarm",
    "RdYlBu_r": "RdYlBu_r",
    "Spectral_r": "Spectral_r",
    "Blues": "Blues",
    "YlOrRd": "YlOrRd",
    "BuPu": "BuPu",
}

CUSTOM_COLORMAPS = {
    "thermal": [
        "#0a1929", "#1565c0", "#00acc1", "#66bb6a",
        "#cddc39", "#ff9800", "#f44336",
    ],
}


def _hex_to_rgb(value: str) -> Tuple[float, float, float]:
    value = value.strip().lstrip("#")
    if len(value) != 6 or not all(c in "0123456789abcdefABCDEF" for c in value):
        raise ValueError(f"Invalid gradient color '{value}'")
    return (
        int(value[0:2], 16) / 255.0,
        int(value[2:4], 16) / 255.0,
        int(value[4:6], 16) / 255.0,
    )


def _build_custom_colormap(colors: Sequence[str], name: str = "yara_custom"):
    from matplotlib.colors import LinearSegmentedColormap
    rgb = [_hex_to_rgb(c) for c in colors]
    return LinearSegmentedColormap.from_list(name, rgb, N=256)


def _get_colormap(name: str):
    """Resolve a frontend colormap name or gradient(...) expression."""
    requested = (name or "viridis").strip()

    if requested.startswith("gradient(") and requested.endswith(")"):
        content = requested[len("gradient("):-1]
        colors = []
        for item in content.split(","):
            item = item.strip()
            if "@" in item:
                color, _position = item.rsplit("@", 1)
            else:
                color = item
            colors.append(color.strip())
        if len(colors) >= 2:
            return _build_custom_colormap(colors)

    if requested in CUSTOM_COLORMAPS:
        return _build_custom_colormap(CUSTOM_COLORMAPS[requested], requested)

    return matplotlib.colormaps.get(
        BUILTIN_COLORMAPS.get(requested, "viridis"),
        matplotlib.colormaps["viridis"],
    )


# ---------------------------------------------------------------------------
# PNG rendering
# ---------------------------------------------------------------------------

def render_to_png(
    variable: str,
    cfg: Dict[str, Any],
    date: str,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    max_pixels: int,
    colormap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
) -> Tuple[bytes, str, Dict[str, Any]]:

    logger.info("[YARA OPeNDAP] Opening remote dataset: variable=%s  dataset=%s",
                variable, cfg.get("dataset_id", "unknown"))

    ds = open_remote_dataset(
        variable,
        cfg,
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        start_datetime=date,
        end_datetime=date,
    )

    logger.info("[YARA OPeNDAP] Selecting requested date: %s", date)
    ds, matched = _select_date(ds, date)
    logger.info("[YARA OPeNDAP] Matched date in dataset: %s", matched)

    data = ds[variable]

    logger.info("[YARA DATA] Selecting variable: %s", variable)
    logger.info("[YARA DATA] Reading scientific variable: %s  dims=%s", variable, list(data.dims))

    # If the variable has depth, default to surface.
    if "depth" in data.dims:
        data = data.isel(depth=0)
        logger.info("[YARA DATA] Depth dimension detected — using surface level (depth=0)")

    # Remove singleton dimensions.
    data = data.squeeze(drop=True)

    if "latitude" not in data.dims or "longitude" not in data.dims:
        raise ValueError(
            f"Variable '{variable}' cannot be rendered as a geographic frame"
        )

    # Extract coordinate arrays before any slicing
    lat_values = data["latitude"].values
    lon_values = data["longitude"].values

    if lat_values.size == 0 or lon_values.size == 0:
        raise ValueError(f"No spatial coordinates found for '{variable}' on {date}")

    logger.info("[YARA OPeNDAP] Spatial extent: lat=[%.3f, %.3f]  lon=[%.3f, %.3f]  shape=[%d, %d]",
                float(lat_values.min()), float(lat_values.max()),
                float(lon_values.min()), float(lon_values.max()),
                lat_values.size, lon_values.size)

    # Derive dlat and dlon dynamically from actual coordinate arrays
    if len(lat_values) > 1:
        dlat = abs(float(lat_values[1] - lat_values[0]))
    else:
        dlat = float(cfg.get("spatial_resolution_deg", 0.08333333333333333))

    if len(lon_values) > 1:
        dlon = abs(float(lon_values[1] - lon_values[0]))
    else:
        dlon = float(cfg.get("spatial_resolution_deg", 0.08333333333333333))

    # Calculate exact outer cell-edge bounds
    edge_lat_min = float(np.min(lat_values)) - dlat / 2.0
    edge_lat_max = float(np.max(lat_values)) + dlat / 2.0
    edge_lon_min = float(np.min(lon_values)) - dlon / 2.0
    edge_lon_max = float(np.max(lon_values)) + dlon / 2.0

    # Downsample only if necessary.
    lat_size = data.sizes["latitude"]
    lon_size = data.sizes["longitude"]

    if lat_size * lon_size > max_pixels * max_pixels:

        lat_stride = max(
            1,
            int(np.ceil(lat_size / max_pixels)),
        )

        lon_stride = max(
            1,
            int(np.ceil(lon_size / max_pixels)),
        )

        logger.info("[YARA OPeNDAP] Downsampling grid: stride=[%d, %d]  original=[%d, %d]",
                    lat_stride, lon_stride, lat_size, lon_size)

        data = data.isel(
            latitude=slice(None, None, lat_stride),
            longitude=slice(None, None, lon_stride),
        )

    logger.info("[YARA OPeNDAP] Loading data subset from remote OPeNDAP...")

    # Load ONLY this requested subset.
    arr = data.load().values.astype(np.float32)

    arr = np.squeeze(arr)

    logger.info("[YARA OPeNDAP] Scientific data loaded — shape=%s", arr.shape)

    # Replace invalid values.
    finite = np.isfinite(arr)

    if not finite.any():
        raise ValueError(
            f"No valid data available for '{variable}' on {date}"
        )

    # Value range comes from the frontend when supplied; otherwise use
    # the scientific default registered for this variable.
    vmin_val = float(cfg["vmin"] if vmin is None else vmin)
    vmax_val = float(cfg["vmax"] if vmax is None else vmax)

    if not np.isfinite(vmin_val) or not np.isfinite(vmax_val):
        raise ValueError("Color scale limits must be finite numbers.")
    if vmin_val >= vmax_val:
        raise ValueError("Color scale minimum must be smaller than maximum.")

    logger.info("[YARA RASTER] Applying colormap: %s  range=[%.3f, %.3f]", colormap, vmin_val, vmax_val)

    # Normalize values to the requested display range.
    normalized = (arr - vmin_val) / (vmax_val - vmin_val)
    normalized = np.clip(normalized, 0.0, 1.0)

    # Resolve the same palette selected in the frontend.
    cmap = _get_colormap(colormap)

    # Map normalized values through the selected colormap.
    colored = cmap(normalized)
    rgba = (colored * 255).astype(np.uint8)

    # Set alpha to 0 for non-finite values (NaN / fill values)
    rgba[..., 3] = np.where(
        finite,
        255,
        0,
    ).astype(np.uint8)

    # Flip latitude if latitude increases from South to North so row 0 is North (top of image)
    try:
        if len(lat_values) > 1 and lat_values[0] < lat_values[-1]:
            rgba = np.flipud(rgba)
    except Exception:
        pass

    try:
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Pillow is required for PNG rendering"
        ) from exc

    logger.info("[YARA RASTER] Encoding PNG: size=%dx%d", rgba.shape[1], rgba.shape[0])

    image = Image.fromarray(rgba, mode="RGBA")

    buffer = io.BytesIO()

    image.save(
        buffer,
        format="PNG",
        optimize=True,
    )

    bounds_dict = {
        "west": edge_lon_min,
        "south": edge_lat_min,
        "east": edge_lon_max,
        "north": edge_lat_max,
        "width": int(rgba.shape[1]),
        "height": int(rgba.shape[0]),
    }

    logger.info("[YARA RASTER] Raster generation complete — %d bytes", len(buffer.getvalue()))

    return buffer.getvalue(), matched or date, bounds_dict



# ---------------------------------------------------------------------------
# Point query
# ---------------------------------------------------------------------------

def query_point(
    variable: str,
    cfg: Dict[str, Any],
    date: str,
    lon: float,
    lat: float,
):
    """
    Query the value of a variable at a specific geographic point.

    Returns the observation along with:
    - requested vs actual matched coordinates
    - 1° × 1° display grid box (metadata/geometry, NOT resampling)
    - dataset and source information

    The 1° grid is the geographic grid cell containing the clicked point,
    computed as [floor(coord), floor(coord)+1].  The actual dataset remains
    at its native resolution (~0.083°).  This distinction is scientifically
    important: the grid is display geometry, not an aggregation operation.
    """

    ds = open_remote_dataset(
        variable,
        cfg,
        minimum_longitude=lon - 0.1,
        maximum_longitude=lon + 0.1,
        minimum_latitude=lat - 0.1,
        maximum_latitude=lat + 0.1,
        start_datetime=date,
        end_datetime=date,
    )

    ds, matched = _select_date(ds, date)

    data = ds[variable]

    # --- Select nearest grid cell and extract matched coordinates ---
    matched_lon: float | None = None
    matched_lat: float | None = None

    if "longitude" in data.dims:
        data = data.sel(longitude=lon, method="nearest")
        try:
            matched_lon = float(data["longitude"].values)
        except Exception:
            pass

    if "latitude" in data.dims:
        data = data.sel(latitude=lat, method="nearest")
        try:
            matched_lat = float(data["latitude"].values)
        except Exception:
            pass

    # --- 1° × 1° display grid (NOT resampling) ---
    grid_lat_min = math.floor(lat)
    grid_lat_max = grid_lat_min + 1
    grid_lon_min = math.floor(lon)
    grid_lon_max = grid_lon_min + 1

    result: Dict[str, Any] = {
        "variable": variable,
        "display_name": cfg["display_name"],
        "dataset_id": cfg["dataset_id"],
        "requested_date": date,
        "matched_date": matched or date,
        # Requested coordinates (what the user clicked)
        "requested_lat": lat,
        "requested_lon": lon,
        # Actual dataset matched coordinates (native resolution)
        "matched_lat": matched_lat,
        "matched_lon": matched_lon,
        # Legacy fields kept for backward compatibility
        "longitude": lon,
        "latitude": lat,
        "units": cfg["units_display"],
        "source": cfg.get("source", "Copernicus Marine Service"),
        "provider": cfg.get("provider", "Copernicus"),
        # 1° × 1° display grid box (geometry only, NOT data resampling)
        "grid": {
            "lat_min": grid_lat_min,
            "lat_max": grid_lat_max,
            "lon_min": grid_lon_min,
            "lon_max": grid_lon_max,
            "lat_resolution": 1.0,
            "lon_resolution": 1.0,
        },
    }

    # Depth-dependent variables return all depth values.
    if "depth" in data.dims:

        values = data.load().values

        depth_values = ds["depth"].values

        result["depth_values"] = [
            float(v) for v in depth_values
        ]

        result["values"] = [
            None if not np.isfinite(v) else float(v)
            for v in values
        ]

        # Use the surface (first depth) value as the primary value
        if len(values) > 0:
            v = float(values[0])
            result["value"] = None if not np.isfinite(v) else v
        else:
            result["value"] = None

    else:

        value = data.load().values

        value = np.asarray(value).squeeze()

        if value.size == 0:
            result["value"] = None
        else:
            value = float(value)

            result["value"] = (
                None
                if not np.isfinite(value)
                else value
            )

    return result