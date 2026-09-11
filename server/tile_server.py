"""
Tile server for numeric COG tiles with server-side colormap rendering.

Serves XYZ tiles from numeric COGs, applying colormaps at request time.
Supports both SST (linear scale) and CHL (log scale) visualization.
Includes contour line rendering with labels.
"""

import io
import json
import math
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Optional
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import rasterio
from rasterio.windows import Window
from functools import lru_cache
from scipy import ndimage

# Module-level import for contour rendering (avoid per-request import overhead)
try:
    from skimage import measure as skimage_measure
    HAS_SKIMAGE = True
except ImportError:
    HAS_SKIMAGE = False

# Try to import cmocean for better colormaps
try:
    import cmocean
    HAS_CMOCEAN = True
except ImportError:
    HAS_CMOCEAN = False

# ---------------------------------------------------------------------------
# GDAL / rasterio configuration for fast remote COG reads
# ---------------------------------------------------------------------------
import os as _os

# Enable GDAL block cache (default ~5 MB, raise to 200 MB)
_os.environ.setdefault("GDAL_CACHEMAX", "200")
# Allow GDAL to issue multiple range-request reads at once
_os.environ.setdefault("GDAL_HTTP_MULTIPLEX", "YES")
# Merge small range requests into fewer larger ones (16 KB default → 2 MB)
_os.environ.setdefault("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
_os.environ.setdefault("GDAL_INGESTED_BYTES_AT_OPEN", "32768")
# Header/directory info cached for 1 hour (avoids repeated HEAD requests)
_os.environ.setdefault("VSI_CACHE", "TRUE")
_os.environ.setdefault("VSI_CACHE_SIZE", "50000000")  # 50 MB
# Honour COG header ordering (skip needless seeks)
_os.environ.setdefault("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")

# Load dataset configuration
DATASETS_CONFIG = Path(__file__).parent / "datasets.json"

# Contour levels for SST (°C) - coarse (2°C intervals)
SST_CONTOUR_LEVELS_COARSE = [-2, 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30, 32]
# Contour levels for SST (°C) - fine (1°C intervals, for higher zoom)
SST_CONTOUR_LEVELS_FINE = list(range(-2, 33, 1))
# Contour levels for CHL (mg/m³) - log scale
CHL_CONTOUR_LEVELS = [0.01, 0.03, 0.1, 0.3, 1, 3, 10, 30, 100]

# ---------------------------------------------------------------------------
# Pre-computed transparent tile (avoids re-encoding on every empty response)
# ---------------------------------------------------------------------------
def _make_transparent_png() -> bytes:
    img = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()

TRANSPARENT_TILE_PNG = _make_transparent_png()

# ---------------------------------------------------------------------------
# Thread-local rasterio dataset cache.
# GDAL file handles are NOT safe to share across threads, but re-opening the
# COG header on every request (~250ms for /vsicurl/) is the main bottleneck.
# By giving each thread its own cache of open handles we get both safety
# and speed.
# ---------------------------------------------------------------------------
_tl = threading.local()
_TL_CACHE_MAX = 10  # Open handles per thread


def _get_thread_local_dataset(cog_path: str) -> rasterio.DatasetReader:
    """Return a thread-local cached dataset handle."""
    cache: OrderedDict = getattr(_tl, "ds_cache", None)  # type: ignore[assignment]
    if cache is None:
        cache = OrderedDict()
        _tl.ds_cache = cache

    if cog_path in cache:
        cache.move_to_end(cog_path)
        return cache[cog_path]

    ds = rasterio.open(cog_path)
    cache[cog_path] = ds
    while len(cache) > _TL_CACHE_MAX:
        _, evicted = cache.popitem(last=False)
        try:
            evicted.close()
        except Exception:
            pass
    return ds


# ---------------------------------------------------------------------------
# Rendered tile LRU cache – stores the final PNG/WebP bytes.
# Key: (cog_path, z, x, y, vmin, vmax, fmt)  Value: bytes
# Max ~2000 tiles ≈ 60-120 MB for 256×256 PNGs.
# ---------------------------------------------------------------------------
_TILE_CACHE_MAX = 2000
_tile_cache: OrderedDict[tuple, bytes] = OrderedDict()
_tile_cache_lock = threading.Lock()


def _get_cached_tile(key: tuple) -> Optional[bytes]:
    with _tile_cache_lock:
        if key in _tile_cache:
            _tile_cache.move_to_end(key)
            return _tile_cache[key]
    return None


def _put_cached_tile(key: tuple, data: bytes) -> None:
    with _tile_cache_lock:
        _tile_cache[key] = data
        _tile_cache.move_to_end(key)
        while len(_tile_cache) > _TILE_CACHE_MAX:
            _tile_cache.popitem(last=False)


def get_contour_levels(variable: str, zoom: int) -> list:
    """Get appropriate contour levels based on zoom level."""
    if variable == "sst":
        # Use finer 1°C intervals at z >= 5
        return SST_CONTOUR_LEVELS_FINE if zoom >= 5 else SST_CONTOUR_LEVELS_COARSE
    else:
        return CHL_CONTOUR_LEVELS


@lru_cache(maxsize=1)
def load_datasets_config() -> dict:
    """Load the datasets configuration."""
    with open(DATASETS_CONFIG) as f:
        return json.load(f)


def get_colormap(name: str, n_colors: int = 256) -> np.ndarray:
    """
    Get a colormap as RGBA array.
    
    Args:
        name: Colormap name ('thermal', 'algae', 'ice', 'balance', etc.)
        n_colors: Number of colors in the colormap
    
    Returns:
        RGBA array of shape (n_colors, 4) with values 0-255
    """
    if HAS_CMOCEAN:
        if name == "thermal":
            cmap = cmocean.cm.thermal
        elif name == "algae":
            cmap = cmocean.cm.algae
        elif name == "balance":
            cmap = cmocean.cm.balance
        elif name == "ice":
            cmap = cmocean.cm.ice
        elif name == "deep":
            cmap = cmocean.cm.deep
        else:
            cmap = cmocean.cm.thermal
    else:
        # Fallback to matplotlib
        import matplotlib.pyplot as plt
        if name == "thermal":
            cmap = plt.cm.turbo
        elif name == "algae":
            cmap = plt.cm.viridis
        elif name == "balance":
            cmap = plt.cm.RdBu_r  # Red-blue diverging
        elif name == "ice":
            cmap = plt.cm.Blues_r  # Light blue to dark blue
        else:
            cmap = plt.cm.turbo
    
    # Generate colormap array
    colors = cmap(np.linspace(0, 1, n_colors))
    return (colors * 255).astype(np.uint8)


def tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """
    Convert XYZ tile coordinates to geographic bounds.
    
    Args:
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
    
    Returns:
        (west, south, east, north) in EPSG:4326
    """
    n = 2 ** z
    west = x / n * 360 - 180
    east = (x + 1) / n * 360 - 180
    
    # Y coordinate uses TMS convention (origin at bottom)
    # Convert to lat using Web Mercator projection
    def tile_lat(y, n):
        lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
        return math.degrees(lat_rad)
    
    north = tile_lat(y, n)
    south = tile_lat(y + 1, n)
    
    return (west, south, east, north)


def normalize_value(
    value: float,
    vmin: float,
    vmax: float,
    scale: str = "linear"
) -> float:
    """
    Normalize a value to 0-1 range.
    
    Args:
        value: Input value
        vmin: Minimum value for colormap
        vmax: Maximum value for colormap
        scale: 'linear' or 'log'
    
    Returns:
        Normalized value between 0 and 1
    """
    if scale == "log":
        # Log scale for CHL (handle zeros/negatives)
        if value <= 0:
            return 0.0
        log_val = math.log10(value)
        log_min = math.log10(max(vmin, 1e-10))
        log_max = math.log10(vmax)
        normalized = (log_val - log_min) / (log_max - log_min)
    else:
        # Linear scale for SST
        normalized = (value - vmin) / (vmax - vmin)
    
    return max(0.0, min(1.0, normalized))


def apply_colormap(
    data: np.ndarray,
    colormap: np.ndarray,
    vmin: float,
    vmax: float,
    scale: str = "linear",
    nodata: Optional[float] = None
) -> np.ndarray:
    """
    Apply colormap to numeric data.
    
    Args:
        data: 2D numeric array
        colormap: RGBA colormap array (256, 4)
        vmin: Minimum value for colormap
        vmax: Maximum value for colormap
        scale: 'linear' or 'log'
        nodata: Nodata value to treat as transparent
    
    Returns:
        RGBA image array (height, width, 4)
    """
    height, width = data.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    
    # Create mask for valid data
    if nodata is not None:
        if np.isnan(nodata):
            valid = ~np.isnan(data)
        else:
            valid = data != nodata
    else:
        valid = ~np.isnan(data)
    
    # Handle empty data
    if not valid.any():
        return rgba
    
    # Normalize values
    if scale == "log":
        # Log scale - work in log space
        safe_data = np.where(valid & (data > 0), data, 1e-10)
        log_data = np.log10(safe_data)
        log_min = math.log10(max(vmin, 1e-10))
        log_max = math.log10(vmax)
        normalized = (log_data - log_min) / (log_max - log_min)
    else:
        # Linear scale
        normalized = (data.astype(np.float32) - vmin) / (vmax - vmin)
    
    # Clamp to 0-1
    normalized = np.clip(normalized, 0, 1)
    
    # Map to colormap indices
    indices = (normalized * (len(colormap) - 1)).astype(np.int32)
    indices = np.clip(indices, 0, len(colormap) - 1)
    
    # Apply colors
    for i in range(3):  # R, G, B
        rgba[:, :, i] = np.where(valid, colormap[indices, i], 0)
    
    # Alpha channel - 255 for valid, 0 for nodata
    rgba[:, :, 3] = np.where(valid, 255, 0)
    
    return rgba


def draw_contours(
    img: Image.Image,
    data: np.ndarray,
    levels: list[float],
    nodata: Optional[float] = None,
    line_color: tuple = (255, 255, 255, 220),
    line_width: int = 2,
    label_color: tuple = (255, 255, 200, 255),
    show_labels: bool = True
) -> Image.Image:
    """
    Draw contour lines on an image.
    
    Uses marching squares algorithm via scipy to find contour paths.
    
    Args:
        img: PIL Image to draw on
        data: 2D numeric array (same size as image)
        levels: List of contour values
        nodata: Nodata value to mask
        line_color: RGBA tuple for contour lines
        line_width: Line width in pixels
        label_color: RGBA tuple for labels
        show_labels: Whether to draw value labels
    
    Returns:
        Modified PIL Image
    """
    if not HAS_SKIMAGE:
        return img
    
    draw = ImageDraw.Draw(img, 'RGBA')
    height, width = data.shape
    
    # Create valid mask
    if nodata is not None:
        if np.isnan(nodata):
            valid = ~np.isnan(data)
        else:
            valid = data != nodata
    else:
        valid = ~np.isnan(data)
    
    # Skip if mostly invalid
    if valid.sum() < 100:
        return img
    
    # Fill invalid areas with nearest valid values before smoothing
    # This prevents dark bleeding at coastlines
    filled_data = data.copy()
    if not valid.all():
        from scipy.ndimage import distance_transform_edt
        # Get indices of nearest valid pixel for each invalid pixel
        indices = distance_transform_edt(~valid, return_distances=False, return_indices=True)
        filled_data = data[indices[0], indices[1]]
    
    # Smooth data slightly for cleaner contours
    smoothed = ndimage.gaussian_filter(filled_data, sigma=1.0)
    # Restore NaN for invalid areas (contours won't cross them)
    smoothed = np.where(valid, smoothed, np.nan)
    
    for level in levels:
        try:
            # Find contours at this level
            contours = skimage_measure.find_contours(smoothed, level)
            
            for contour in contours:
                if len(contour) < 3:
                    continue
                
                # Convert to image coordinates (y, x) -> (x, y)
                points = [(float(p[1]), float(p[0])) for p in contour]
                
                # Draw contour line
                if len(points) >= 2:
                    draw.line(points, fill=line_color, width=line_width)
                
                # Add label at midpoint
                if show_labels and len(contour) > 20:
                    mid_idx = len(contour) // 2
                    label_x, label_y = points[mid_idx]
                    
                    # Only label if inside tile bounds with more margin
                    if 10 < label_x < width - 35 and 10 < label_y < height - 20:
                        label = f"{int(level)}°C" if level == int(level) else f"{level:.1f}°C"
                        
                        # Draw label with bold outline for readability
                        try:
                            # Try to use a larger, bolder font
                            try:
                                font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
                            except Exception:
                                try:
                                    font = ImageFont.truetype("/System/Library/Fonts/HelveticaNeue.ttc", 20)
                                except Exception:
                                    font = ImageFont.load_default()
                            
                            # Strong outline - 3px spread, dark gray for sharp edges
                            outline_color = (40, 40, 40, 255)
                            for dx in [-3, -2, -1, 0, 1, 2, 3]:
                                for dy in [-3, -2, -1, 0, 1, 2, 3]:
                                    if abs(dx) + abs(dy) <= 3 and (dx != 0 or dy != 0):
                                        draw.text((label_x + dx, label_y + dy), label, fill=outline_color, font=font)
                            
                            # Main text - pure white for maximum visibility
                            text_color = (255, 255, 255, 255)
                            draw.text((label_x, label_y), label, fill=text_color, font=font)
                        except Exception:
                            pass
                            
        except Exception:
            # Skip this level if contour finding fails
            continue
    
    return img


class TileReader:
    """Read tiles from a COG file using thread-local cached dataset handles."""
    
    def __init__(self, cog_path: str | Path):
        self.cog_path = str(cog_path)
        self._ds: Optional[rasterio.DatasetReader] = None
    
    def open(self):
        """Open the COG dataset (thread-local cache)."""
        if self._ds is None:
            self._ds = _get_thread_local_dataset(self.cog_path)
        return self._ds
    
    def close(self):
        """No-op — handle lifetime managed by thread-local cache."""
        self._ds = None
    
    def read_tile(
        self,
        z: int,
        x: int,
        y: int,
        tile_size: int = 256
    ) -> Optional[np.ndarray]:
        """
        Read a tile from the COG.
        
        Args:
            z: Zoom level
            x: Tile X coordinate
            y: Tile Y coordinate
            tile_size: Output tile size in pixels
        
        Returns:
            2D numpy array or None if tile is outside bounds
        """
        ds = self.open()
        
        # Get tile bounds
        west, south, east, north = tile_bounds(z, x, y)
        
        # Check if tile intersects COG bounds
        cog_bounds = ds.bounds
        if (east <= cog_bounds.left or west >= cog_bounds.right or
            north <= cog_bounds.bottom or south >= cog_bounds.top):
            return None
        
        # Calculate the window in pixel coordinates
        # Transform from geographic to pixel coordinates
        row_start, col_start = ds.index(west, north)
        row_end, col_end = ds.index(east, south)
        
        # Ensure valid window
        row_start = max(0, min(row_start, ds.height))
        row_end = max(0, min(row_end, ds.height))
        col_start = max(0, min(col_start, ds.width))
        col_end = max(0, min(col_end, ds.width))
        
        if row_start >= row_end or col_start >= col_end:
            return None
        
        # Read and resample to tile size
        window = Window(
            col_off=col_start,
            row_off=row_start,
            width=col_end - col_start,
            height=row_end - row_start
        )
        
        data = ds.read(
            1,
            window=window,
            out_shape=(tile_size, tile_size),
            resampling=rasterio.enums.Resampling.bilinear
        )
        
        return data
    
    @property
    def nodata(self) -> Optional[float]:
        """Get the nodata value."""
        ds = self.open()
        return ds.nodata
    
    @property
    def dtype(self) -> str:
        """Get the data type."""
        ds = self.open()
        return str(ds.dtypes[0])


def render_rgb_tile(
    cog_path: str | Path,
    z: int,
    x: int,
    y: int,
    tile_size: int = 256
) -> Optional[bytes]:
    """
    Render a tile from an RGBA COG file directly (no colormap).
    
    Used for ocean color RGB composites where the COG already contains
    pre-rendered RGBA pixels.
    
    Args:
        cog_path: Path to the RGBA COG file
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        tile_size: Tile size in pixels
    
    Returns:
        PNG bytes or None if tile is outside bounds
    """
    try:
        with rasterio.open(cog_path) as ds:
            # Get tile bounds
            west, south, east, north = tile_bounds(z, x, y)
            
            # Check if tile intersects COG bounds
            cog_bounds = ds.bounds
            if (east <= cog_bounds.left or west >= cog_bounds.right or
                north <= cog_bounds.bottom or south >= cog_bounds.top):
                return None
            
            # Calculate the window in pixel coordinates
            row_start, col_start = ds.index(west, north)
            row_end, col_end = ds.index(east, south)
            
            # Ensure valid window
            row_start = max(0, min(row_start, ds.height))
            row_end = max(0, min(row_end, ds.height))
            col_start = max(0, min(col_start, ds.width))
            col_end = max(0, min(col_end, ds.width))
            
            if row_start >= row_end or col_start >= col_end:
                return None
            
            window = Window(
                col_off=col_start,
                row_off=row_start,
                width=col_end - col_start,
                height=row_end - row_start
            )
            
            # Read all bands (RGBA)
            n_bands = ds.count
            if n_bands >= 4:
                # Read RGBA
                data = ds.read(
                    [1, 2, 3, 4],
                    window=window,
                    out_shape=(4, tile_size, tile_size),
                    resampling=rasterio.enums.Resampling.bilinear
                )
                # Transpose to (H, W, C) for PIL
                rgba = np.transpose(data, (1, 2, 0))
            elif n_bands == 3:
                # Read RGB, add full alpha
                data = ds.read(
                    [1, 2, 3],
                    window=window,
                    out_shape=(3, tile_size, tile_size),
                    resampling=rasterio.enums.Resampling.bilinear
                )
                rgb = np.transpose(data, (1, 2, 0))
                alpha = np.full((tile_size, tile_size, 1), 255, dtype=np.uint8)
                rgba = np.concatenate([rgb, alpha], axis=2)
            else:
                return None
            
            # Convert to PIL and save
            img = Image.fromarray(rgba.astype(np.uint8), mode="RGBA")
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            return buf.getvalue()
            
    except Exception as e:
        print(f"Error rendering RGB tile: {e}")
        return None


def render_tile(
    cog_path: str | Path,
    z: int,
    x: int,
    y: int,
    variable: str = "sst",
    tile_size: int = 256,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    contours: bool = True,
    output_format: str = "png",
    threshold_min: Optional[float] = None,
    threshold_max: Optional[float] = None,
) -> Optional[bytes]:
    """
    Render a tile as PNG or WebP.
    
    Args:
        cog_path: Path to the COG file
        z: Zoom level
        x: Tile X coordinate
        y: Tile Y coordinate
        variable: Variable name ('sst' or 'chl')
        tile_size: Tile size in pixels
        vmin: Optional minimum value override
        vmax: Optional maximum value override
        contours: Whether to draw contour lines
        output_format: 'png' or 'webp'
        threshold_min: If set, values below this become transparent
        threshold_max: If set, values above this become transparent
    
    Returns:
        Image bytes or None if tile is empty
    """
    config = load_datasets_config().get(variable, {})
    
    # Get colormap settings
    cmap_name = config.get("colormap", "thermal")
    scale = config.get("scale", "linear")
    default_range = config.get("range", [-2, 35] if variable == "sst" else [0.01, 100])
    
    vmin = vmin if vmin is not None else default_range[0]
    vmax = vmax if vmax is not None else default_range[1]
    
    # Check rendered tile cache (only for non-threshold requests)
    use_cache = threshold_min is None and threshold_max is None
    if use_cache:
        cache_key = (str(cog_path), z, x, y, vmin, vmax, output_format)
        cached = _get_cached_tile(cache_key)
        if cached is not None:
            return cached
    
    # Special handling for RGB files (e.g., rrs ocean color composite)
    if cmap_name == "rgb" or variable == "rrs":
        result = render_rgb_tile(cog_path, z, x, y, tile_size)
        if result is not None and use_cache:
            _put_cached_tile(cache_key, result)
        return result
    
    # Read tile data
    reader = TileReader(cog_path)
    try:
        data = reader.read_tile(z, x, y, tile_size)
        if data is None:
            return None
        
        nodata = reader.nodata
        dtype = reader.dtype
        
        # Decode based on variable encoding
        if variable == "sst" and dtype == "int16":
            data = data.astype(np.float32) * 0.01
            nodata = -32768 * 0.01 if nodata == -32768 else nodata
        elif variable == "sla" and dtype == "int16":
            data = data.astype(np.float32) * 0.001
            nodata = -32768 * 0.001 if nodata == -32768 else nodata
        elif variable == "sic" and dtype == "uint8":
            data = data.astype(np.float32)
            data = np.where(data <= 15, 255, data)
            nodata = 255
        elif variable == "chl":
            data = data.astype(np.float32)
            nodata = np.nan
        elif variable == "kd490":
            data = data.astype(np.float32)
            nodata = np.nan
        
        # Get colormap
        colormap = get_colormap(cmap_name)
        
        # Apply colormap
        rgba = apply_colormap(data, colormap, vmin, vmax, scale, nodata)
        
        # Apply threshold masking - make values outside threshold range transparent
        if threshold_min is not None or threshold_max is not None:
            # Create mask for valid data
            valid_mask = ~np.isnan(data) if np.issubdtype(data.dtype, np.floating) else (data != nodata if nodata is not None else np.ones_like(data, dtype=bool))
            
            # Apply threshold filters
            mask = valid_mask.copy()
            if threshold_min is not None:
                mask = mask & (data >= threshold_min)
            if threshold_max is not None:
                mask = mask & (data <= threshold_max)
            
            # Set alpha to 0 for pixels outside threshold
            rgba[:, :, 3] = np.where(mask, rgba[:, :, 3], 0)
        
        # Convert to PIL Image
        img = Image.fromarray(rgba, mode="RGBA")
        
        # Add contours if enabled and zoom level is appropriate (z >= 6)
        if contours and z >= 6:
            levels = get_contour_levels(variable, z)
            valid_mask = data != nodata if nodata else ~np.isnan(data)
            if valid_mask.any():
                data_min, data_max = data[valid_mask].min(), data[valid_mask].max()
                tile_levels = [l for l in levels if data_min <= l <= data_max]
                if tile_levels:
                    show_labels = z >= 7
                    img = draw_contours(img, data, tile_levels, nodata, show_labels=show_labels)
        
        # Encode to output format
        buf = io.BytesIO()
        if output_format == "webp":
            img.save(buf, format="WEBP", quality=85, method=4)
        else:
            img.save(buf, format="PNG", optimize=True)
        result = buf.getvalue()
        
        # Store in tile cache
        if use_cache:
            _put_cached_tile(cache_key, result)
        return result
    
    finally:
        reader.close()


# FastAPI integration
def add_tile_routes(app):
    """Add tile serving routes to a FastAPI app."""
    from fastapi import HTTPException
    from fastapi.responses import Response
    from .config import settings
    
    @app.get("/tiles/{variable}/{date}/{z}/{x}/{y}.png")
    async def get_tile(
        variable: str,
        date: str,
        z: int,
        x: int,
        y: int,
        stream: str = "auto",
        vmin: Optional[float] = None,
        vmax: Optional[float] = None
    ):
        """
        Get a map tile for a variable and date.
        
        Args:
            variable: sst or chl
            date: YYYY-MM-DD
            z: Zoom level
            x: Tile X
            y: Tile Y
            stream: nrt, rep, or auto (default)
            vmin: Optional min value for colormap
            vmax: Optional max value for colormap
        """
        # Get COG path from config (handles local or Azure)
        cog_path = settings.get_cog_path(variable, date)
        
        # For local paths, check existence
        if settings.products_source == "local" and not Path(cog_path).exists():
            raise HTTPException(404, f"No data for {variable} on {date}")
        
        try:
            png_data = render_tile(cog_path, z, x, y, variable, vmin=vmin, vmax=vmax)
        except rasterio.errors.RasterioIOError as e:
            # Remote COG access failed (404 on Azure, etc.)
            raise HTTPException(404, f"No data for {variable} on {date}")
        
        if png_data is None:
            # Return transparent tile
            return Response(
                content=b"",
                media_type="image/png",
                status_code=204
            )
        
        return Response(
            content=png_data,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400"}
        )
    
    return app


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 5:
        print("Usage: python tile_server.py <cog_path> <z> <x> <y> [variable]")
        sys.exit(1)
    
    cog_path = Path(sys.argv[1])
    z, x, y = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    variable = sys.argv[5] if len(sys.argv) > 5 else "sst"
    
    png_data = render_tile(cog_path, z, x, y, variable)
    
    if png_data:
        output = Path(f"tile_{z}_{x}_{y}.png")
        output.write_bytes(png_data)
        print(f"Written: {output}")
    else:
        print("Empty tile (outside bounds)")
