"""
Playback Manager and Prefetching Engine for YARA.
Coordinates pre-rendering and buffer management for high-speed playback.
"""

from typing import List, Optional
import asyncio
import logging

from ..data_sources.local.registry import registry
from .local_processor import render_slice_to_png
from .frame_cache import frame_cache
from .gradient_colormap import stops_cache_token

logger = logging.getLogger(__name__)


class PlaybackManager:
    """Manages prefetching and high-speed frame access for playback."""

    def get_or_render_frame(
        self,
        dataset_id: str,
        variable: Optional[str] = None,
        time_index: int = 0,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        filter_mode: str = "none",
        exact_value: Optional[float] = None,
        exact_tolerance: Optional[float] = None,
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        gradient_stops: Optional[list] = None
    ) -> bytes:
        reader = registry.get_reader(dataset_id)
        var_name = variable or reader._dataset_info.default_variable
        grad_token = stops_cache_token(gradient_stops)

        # Check cache
        cached = frame_cache.get(
            dataset_id, var_name, time_index, colormap, min_val, max_val,
            filter_mode, exact_value, exact_tolerance, range_min, range_max, grad_token
        )
        if cached:
            return cached

        # Render on the fly
        slice_data = reader.read_frame(var_name, time_index)
        png_bytes = render_slice_to_png(
            slice_data, colormap_name=colormap, min_val=min_val, max_val=max_val,
            filter_mode=filter_mode, exact_value=exact_value, exact_tolerance=exact_tolerance,
            range_min=range_min, range_max=range_max, gradient_stops=gradient_stops
        )

        # Store in cache
        frame_cache.put(
            dataset_id, var_name, time_index, png_bytes, colormap, min_val, max_val,
            filter_mode, exact_value, exact_tolerance, range_min, range_max, grad_token
        )
        return png_bytes

    async def prefetch_range(
        self,
        dataset_id: str,
        variable: Optional[str] = None,
        start_index: int = 0,
        count: int = 10,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        filter_mode: str = "none",
        exact_value: Optional[float] = None,
        exact_tolerance: Optional[float] = None,
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        gradient_stops: Optional[list] = None
    ) -> int:
        """Prefetches up to `count` upcoming frames in background."""
        reader = registry.get_reader(dataset_id)
        var_name = variable or reader._dataset_info.default_variable
        total_times = reader._dataset_info.time_axis.count
        grad_token = stops_cache_token(gradient_stops)

        prefetched = 0
        for idx in range(start_index, min(start_index + count, total_times)):
            # If already cached, continue
            if frame_cache.get(
                dataset_id, var_name, idx, colormap, min_val, max_val,
                filter_mode, exact_value, exact_tolerance, range_min, range_max, grad_token
            ):
                continue

            try:
                # Yield to event loop to avoid blocking
                await asyncio.sleep(0.001)
                self.get_or_render_frame(
                    dataset_id, var_name, idx, colormap, min_val, max_val,
                    filter_mode, exact_value, exact_tolerance, range_min, range_max, gradient_stops
                )
                prefetched += 1
            except Exception as e:
                logger.warning(f"Error prefetching frame {idx} for {dataset_id}: {e}")

        return prefetched


# Global playback manager
playback_manager = PlaybackManager()
