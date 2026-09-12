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
from .gradient_colormap import AnalysisOptions, analyze_slice, gradient_rgba, rgb


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
    analysis: Optional[AnalysisOptions] = None
) -> bytes:
    """
    Renders a SliceData 2D array into a transparent RGBA PNG image.
    NaNs and nodata are transparent (alpha=0), allowing MapTiler land basemap to show through.
    """
    analysis = analysis or AnalysisOptions()
    data, matching, _ = analyze_slice(slice_data, analysis)
    mask = ~matching
    v_min = min_val if min_val is not None else slice_data.min_val
    v_max = max_val if max_val is not None else slice_data.max_val
    if analysis.mode == "range":
        v_min, v_max = analysis.range_min, analysis.range_max
    if not np.isfinite(v_min) or not np.isfinite(v_max) or v_min > v_max:
        raise ValueError("Color scale must be finite with minimum <= maximum")
    norm = np.clip((data - v_min) / (v_max - v_min if v_max > v_min else 1), 0, 1)
    norm[mask] = 0
    if analysis.mode == "exact":
        rgba = np.ones((*data.shape, 4), dtype=float)
        rgba[..., :3] = rgb(analysis.flat_color)
    elif analysis.stops or analysis.mode == "range":
        rgba = gradient_rgba(norm, analysis.stops)
    else:
        cmap = get_colormap_for_variable(slice_data.variable_name, colormap_name)
        rgba = cmap(norm)

    # Convert to uint8 [0, 255]
    rgba_uint8 = (rgba * 255.0).astype(np.uint8)

    # Set invalid/masked cells strictly to transparent [0, 0, 0, 0]
    rgba_uint8[mask] = [0, 0, 0, 0]

    # Create PIL Image
    img = Image.fromarray(rgba_uint8, mode="RGBA")

    # Serialize to PNG in memory
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
