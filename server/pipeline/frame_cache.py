"""
Two-Tier Frame Cache for YARA Fast Playback.
Maintains in-memory LRU cache and persistent disk cache for rendered PNG frames.
"""

from pathlib import Path
from typing import Optional, Dict
from collections import OrderedDict
import logging

logger = logging.getLogger(__name__)

CACHE_DIR = Path("cache/frames")
MAX_MEMORY_FRAMES = 120  # Store up to 120 uncompressed/compressed frames in RAM


class FrameCache:
    """Manages memory and disk caching for scientific visualization frames."""

    def __init__(self, cache_dir: Path = CACHE_DIR, max_memory_frames: int = MAX_MEMORY_FRAMES):
        self.cache_dir = cache_dir
        self.max_memory_frames = max_memory_frames
        self._memory_cache: OrderedDict[str, bytes] = OrderedDict()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _make_key(
        self,
        dataset_id: str,
        variable: str,
        time_index: int,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        filter_mode: str = "none",
        exact_value: Optional[float] = None,
        exact_tolerance: Optional[float] = None,
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        gradient_token: Optional[str] = None
    ) -> str:
        cmap_str = colormap or "default"
        scale_str = f"{min_val}_{max_val}" if (min_val is not None and max_val is not None) else "auto"
        filt_str = filter_mode
        if filter_mode == "exact":
            filt_str += f"_{exact_value}_{exact_tolerance}"
        elif filter_mode == "range":
            filt_str += f"_{range_min}_{range_max}"
        grad_str = gradient_token or "nograd"
        return f"{dataset_id}_{variable}_t{time_index}_{cmap_str}_{scale_str}_{filt_str}_{grad_str}"

    def get(
        self,
        dataset_id: str,
        variable: str,
        time_index: int,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        filter_mode: str = "none",
        exact_value: Optional[float] = None,
        exact_tolerance: Optional[float] = None,
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        gradient_token: Optional[str] = None
    ) -> Optional[bytes]:
        key = self._make_key(
            dataset_id, variable, time_index, colormap, min_val, max_val,
            filter_mode, exact_value, exact_tolerance, range_min, range_max, gradient_token
        )

        # 1. Check memory cache (fastest)
        if key in self._memory_cache:
            self._memory_cache.move_to_end(key)
            return self._memory_cache[key]

        # 2. Check disk cache
        disk_path = self.cache_dir / f"{key}.png"
        if disk_path.exists():
            try:
                data = disk_path.read_bytes()
                # Promote to memory cache
                self.put(
                    dataset_id, variable, time_index, data, colormap, min_val, max_val,
                    filter_mode, exact_value, exact_tolerance, range_min, range_max, gradient_token
                )
                return data
            except Exception as e:
                logger.warning(f"Failed to read disk frame cache for {key}: {e}")

        return None

    def put(
        self,
        dataset_id: str,
        variable: str,
        time_index: int,
        png_bytes: bytes,
        colormap: Optional[str] = None,
        min_val: Optional[float] = None,
        max_val: Optional[float] = None,
        filter_mode: str = "none",
        exact_value: Optional[float] = None,
        exact_tolerance: Optional[float] = None,
        range_min: Optional[float] = None,
        range_max: Optional[float] = None,
        gradient_token: Optional[str] = None
    ):
        key = self._make_key(
            dataset_id, variable, time_index, colormap, min_val, max_val,
            filter_mode, exact_value, exact_tolerance, range_min, range_max, gradient_token
        )

        # Save to memory cache with LRU eviction
        self._memory_cache[key] = png_bytes
        self._memory_cache.move_to_end(key)
        if len(self._memory_cache) > self.max_memory_frames:
            self._memory_cache.popitem(last=False)

        # Save to disk asynchronously/safely
        disk_path = self.cache_dir / f"{key}.png"
        try:
            disk_path.write_bytes(png_bytes)
        except Exception as e:
            logger.debug(f"Failed to write disk cache for {key}: {e}")

    def clear(self, dataset_id: Optional[str] = None):
        """Clears memory cache and optionally disk cache."""
        if dataset_id is None:
            self._memory_cache.clear()
            for f in self.cache_dir.glob("*.png"):
                try:
                    f.unlink()
                except Exception:
                    pass
        else:
            keys_to_del = [k for k in self._memory_cache if k.startswith(dataset_id)]
            for k in keys_to_del:
                del self._memory_cache[k]
            for f in self.cache_dir.glob(f"{dataset_id}_*.png"):
                try:
                    f.unlink()
                except Exception:
                    pass


# Global frame cache instance
frame_cache = FrameCache()
