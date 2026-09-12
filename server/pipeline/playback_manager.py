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
        max_val: Optional[float] = None
    ) -> bytes:
        reader = registry.get_reader(dataset_id)
        var_name = variable or reader._dataset_info.default_variable

        # Check cache
        cached = frame_cache.get(dataset_id, var_name, time_index, colormap, min_val, max_val)
        if cached:
            return cached

        # Render on the fly
        slice_data = reader.read_frame(var_name, time_index)
        png_bytes = render_slice_to_png(slice_data, colormap_name=colormap, min_val=min_val, max_val=max_val)

        # Store in cache
        frame_cache.put(dataset_id, var_name, time_index, png_bytes, colormap, min_val, max_val)
        return png_bytes

    async def prefetch_range(
        self,
        dataset_id: str,
        variable: Optional[str] = None,
        start_index: int = 0,
        count: int = 10,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None
    ) -> int:
        """Prefetches up to `count` upcoming frames in background."""
        reader = registry.get_reader(dataset_id)
        var_name = variable or reader._dataset_info.default_variable
        total_times = reader._dataset_info.time_axis.count

        prefetched = 0
        for idx in range(start_index, min(start_index + count, total_times)):
            # If already cached, continue
            if frame_cache.get(dataset_id, var_name, idx, colormap, min_val, max_val):
                continue

            try:
                # Yield to event loop to avoid blocking
                await asyncio.sleep(0.001)
                self.get_or_render_frame(dataset_id, var_name, idx, colormap, min_val, max_val)
                prefetched += 1
            except Exception as e:
                logger.warning(f"Error prefetching frame {idx} for {dataset_id}: {e}")

        return prefetched


# Global playback manager
playback_manager = PlaybackManager()
