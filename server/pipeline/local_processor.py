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
    max_val: Optional[float] = None
) -> bytes:
    """
    Renders a SliceData 2D array into a transparent RGBA PNG image.
    NaNs and nodata are transparent (alpha=0), allowing MapTiler land basemap to show through.
    """
    data = slice_data.data
    mask = slice_data.mask if slice_data.mask is not None else np.isnan(data)

    # Determine display range
    v_min = min_val if min_val is not None else slice_data.min_val
    v_max = max_val if max_val is not None else slice_data.max_val
    if v_max <= v_min:
        v_max = v_min + 1.0

    # Normalize to [0.0, 1.0]
    norm = np.clip((data - v_min) / (v_max - v_min), 0.0, 1.0)
    norm[mask] = 0.0

    # Apply colormap
    cmap = get_colormap_for_variable(slice_data.variable_name, colormap_name)
    rgba = cmap(norm)  # returns shape (H, W, 4) in [0.0, 1.0]

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
