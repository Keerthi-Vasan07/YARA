"""
Gradient colormap engine for YARA local-dataset scientific rendering.
Builds matplotlib colormaps from user-defined gradient stops, and provides
exact/range filter-mask logic shared between PNG rendering and the frame-stats endpoint.

Keep in sync with src/utils/gradientColormap.ts (the frontend color-bar preview
reimplements the same normalize+interpolate logic in TypeScript since it cannot
share code across the language boundary).
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from matplotlib.colors import LinearSegmentedColormap, Colormap

DEFAULT_GRADIENT_STOPS: List[Dict[str, Any]] = [
    {"position": 0.0, "color": "#0a1929"},
    {"position": 0.5, "color": "#00acc1"},
    {"position": 1.0, "color": "#f44336"},
]


def sort_and_validate_stops(stops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Clamps positions to [0,1], sorts by position, and requires at least 2 stops."""
    if not stops or len(stops) < 2:
        return list(DEFAULT_GRADIENT_STOPS)
    cleaned = []
    for s in stops:
        pos = float(np.clip(float(s["position"]), 0.0, 1.0))
        color = str(s["color"])
        cleaned.append({"position": pos, "color": color})
    cleaned.sort(key=lambda s: s["position"])
    return cleaned


def build_colormap_from_stops(stops: List[Dict[str, Any]]) -> Colormap:
    """Builds a matplotlib LinearSegmentedColormap from validated gradient stops."""
    cleaned = sort_and_validate_stops(stops)
    colors = [(s["position"], s["color"]) for s in cleaned]
    return LinearSegmentedColormap.from_list("custom_gradient", colors)


def normalize_value(value, v_min: float, v_max: float):
    """Clamps (value - v_min) / (v_max - v_min) into [0, 1]. Works on scalars or arrays."""
    if v_max <= v_min:
        v_max = v_min + 1.0
    return np.clip((value - v_min) / (v_max - v_min), 0.0, 1.0)


def stops_cache_token(stops: Optional[List[Dict[str, Any]]]) -> str:
    """Deterministic short token for use in FrameCache keys."""
    if not stops:
        return "nograd"
    cleaned = sort_and_validate_stops(stops)
    return "-".join(f"{s['position']:.4f}:{s['color']}" for s in cleaned)


def resolve_colormap(
    colormap_name: Optional[str],
    gradient_stops: Optional[List[Dict[str, Any]]],
    var_name: str,
    fallback_resolver,
) -> Colormap:
    """
    Decision order: gradient stops (if provided) > named colormap > variable heuristic.
    `fallback_resolver` is local_processor.get_colormap_for_variable, injected to avoid
    a circular import between local_processor.py and this module.
    """
    if gradient_stops:
        return build_colormap_from_stops(gradient_stops)
    return fallback_resolver(var_name, colormap_name)


def compute_filter_mask_and_count(
    data: np.ndarray,
    base_mask: np.ndarray,
    filter_mode: str = "none",
    exact_value: Optional[float] = None,
    exact_tolerance: Optional[float] = None,
    range_min: Optional[float] = None,
    range_max: Optional[float] = None,
) -> Tuple[np.ndarray, int, int]:
    """
    Combines the base (NaN/land) mask with an exact-value or range filter mask.
    Returns (combined_mask, matching_cells, total_cells).
    """
    total_cells = int(data.size)

    if filter_mode == "exact":
        if exact_value is None:
            raise ValueError("exact_value is required when filter_mode='exact'")
        tolerance = exact_tolerance if exact_tolerance is not None else 0.0
        filter_mask = np.abs(data - exact_value) > tolerance
    elif filter_mode == "range":
        if range_min is None or range_max is None:
            raise ValueError("range_min and range_max are required when filter_mode='range'")
        if range_min > range_max:
            raise ValueError("range_min must be <= range_max")
        filter_mask = (data < range_min) | (data > range_max)
    else:
        filter_mask = np.zeros_like(base_mask, dtype=bool)

    combined_mask = base_mask | filter_mask
    matching_cells = int(np.count_nonzero(~combined_mask))
    return combined_mask, matching_cells, total_cells
