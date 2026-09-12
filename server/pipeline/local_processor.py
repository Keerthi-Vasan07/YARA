"""
Local Scientific Visualization Processor for YARA.
Renders 2D scientific data arrays into transparent RGBA PNG images with scientific colormaps.
"""

import io
from typing import Optional, Tuple
import numpy as np
from PIL import Image
import matplotlib.cm as cm

# Try cmocean for oceanographic palettes
try:
    import cmocean
    HAS_CMOCEAN = True
except ImportError:
    HAS_CMOCEAN = False

from ..data_sources.local.common_model import SliceData
from .gradient_colormap import (
    resolve_colormap,
    normalize_value,
    compute_filter_mask_and_count,
)


def get_colormap_for_variable(var_name: str, requested_colormap: Optional[str] = None):
    """Selects an appropriate scientific colormap based on variable name or request."""
    if requested_colormap:
        try:
            return cm.get_cmap(requested_colormap)
        except Exception:
            pass

    clean_var = var_name.lower()
    if HAS_CMOCEAN:
        if any(k in clean_var for k in ("sst", "temp", "thermal")):
            return cmocean.cm.thermal
        if any(k in clean_var for k in ("ice", "sic", "concentration")):
            return cmocean.cm.ice
        if any(k in clean_var for k in ("chl", "chlorophyll", "algae")):
            return cmocean.cm.algae
        if any(k in clean_var for k in ("anom", "anomaly", "diff")):
            return cmocean.cm.balance
        if any(k in clean_var for k in ("u", "v", "speed", "velocity", "wind")):
            return cmocean.cm.speed
        if any(k in clean_var for k in ("sal", "haline", "salinity")):
            return cmocean.cm.haline
        if any(k in clean_var for k in ("err", "uncertainty")):
            return cmocean.cm.matter

    # Matplotlib fallbacks
    if any(k in clean_var for k in ("sst", "temp")):
        return cm.get_cmap("inferno")
    if any(k in clean_var for k in ("ice",)):
        return cm.get_cmap("Blues_r")
    if any(k in clean_var for k in ("chl",)):
        return cm.get_cmap("viridis")
    if any(k in clean_var for k in ("anom",)):
        return cm.get_cmap("coolwarm")

    return cm.get_cmap("viridis")


def render_slice_to_png(
    slice_data: SliceData,
    colormap_name: Optional[str] = None,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    filter_mode: str = "none",
    exact_value: Optional[float] = None,
    exact_tolerance: Optional[float] = None,
    range_min: Optional[float] = None,
    range_max: Optional[float] = None,
    gradient_stops: Optional[list] = None,
) -> bytes:
    """
    Renders a SliceData 2D array into a transparent RGBA PNG image.
    NaNs and nodata are transparent (alpha=0), allowing MapTiler land basemap to show through.

    filter_mode="none": unfiltered, linear min_val..max_val scale (unchanged default behavior).
    filter_mode="exact": only cells within exact_tolerance of exact_value are rendered
      (as a single flat color); everything else is transparent.
    filter_mode="range": only cells within [range_min, range_max] are rendered, colored
      by a CONTINUOUS gradient over that range; everything else is transparent.
    """
    data = slice_data.data
    base_mask = slice_data.mask if slice_data.mask is not None else np.isnan(data)

    combined_mask, _matching, _total = compute_filter_mask_and_count(
        data, base_mask, filter_mode, exact_value, exact_tolerance, range_min, range_max
    )

    cmap = resolve_colormap(colormap_name, gradient_stops, slice_data.variable_name, get_colormap_for_variable)

    if filter_mode == "exact":
        # Flat single color for every matching cell, sampled at the exact value's position
        # within the display range (falls back to slice min/max if no explicit scale given).
        v_min = min_val if min_val is not None else slice_data.min_val
        v_max = max_val if max_val is not None else slice_data.max_val
        t = float(normalize_value(exact_value, v_min, v_max))
        flat_rgba = np.array(cmap(t))
        rgba = np.tile(flat_rgba, (*data.shape, 1))
    elif filter_mode == "range":
        norm = normalize_value(data, range_min, range_max)
        norm[combined_mask] = 0.0
        rgba = cmap(norm)
    else:
        v_min = min_val if min_val is not None else slice_data.min_val
        v_max = max_val if max_val is not None else slice_data.max_val
        norm = normalize_value(data, v_min, v_max)
        norm[combined_mask] = 0.0
        rgba = cmap(norm)

    # Convert to uint8 [0, 255]
    rgba_uint8 = (rgba * 255.0).astype(np.uint8)

    # Set invalid/masked/filtered-out cells strictly to transparent [0, 0, 0, 0]
    rgba_uint8[combined_mask] = [0, 0, 0, 0]

    # Create PIL Image
    img = Image.fromarray(rgba_uint8, mode="RGBA")

    # Serialize to PNG in memory
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
