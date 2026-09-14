"""Thread-safe two-tier LRU frame cache with complete, canonical parameter keys."""
from pathlib import Path
from collections import OrderedDict
from threading import RLock
from hashlib import sha256
from tempfile import NamedTemporaryFile
import json
import logging

logger = logging.getLogger(__name__)
CACHE_DIR = Path("cache/frames")
MAX_MEMORY_FRAMES = 120


class FrameCache:
    def __init__(self, cache_dir=CACHE_DIR, max_memory_frames=MAX_MEMORY_FRAMES):
        self.cache_dir = Path(cache_dir)
        self.max_memory_frames = max_memory_frames
        self._memory_cache = OrderedDict()
        self._lock = RLock()
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _prefix(self, dataset_id):
        return sha256(dataset_id.encode()).hexdigest()[:24] + "_"

    def _make_key(self, dataset_id, variable, time_index, colormap=None, min_val=None, max_val=None, analysis=None, revision=None):
        options = analysis.model_dump() if analysis is not None else None
        payload = [3, dataset_id, variable, time_index, colormap, min_val, max_val, options, revision]
        return self._prefix(dataset_id) + sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()

    def get(self, dataset_id, variable, time_index, colormap=None, min_val=None, max_val=None, analysis=None, revision=None):
        key = self._make_key(dataset_id, variable, time_index, colormap, min_val, max_val, analysis, revision)
        with self._lock:
            if key in self._memory_cache:
                self._memory_cache.move_to_end(key)
                return self._memory_cache[key]
            path = self.cache_dir / f"{key}.png"
            if path.exists():
                try:
                    data = path.read_bytes()
                    self._remember(key, data)
                    return data
                except OSError as exc:
                    logger.warning("Could not read cached frame: %s", exc)
        return None

    def _remember(self, key, data):
        self._memory_cache[key] = data
        self._memory_cache.move_to_end(key)
        while len(self._memory_cache) > self.max_memory_frames:
            self._memory_cache.popitem(last=False)

    def put(self, dataset_id, variable, time_index, png_bytes, colormap=None, min_val=None, max_val=None, analysis=None, revision=None):
        key = self._make_key(dataset_id, variable, time_index, colormap, min_val, max_val, analysis, revision)
        with self._lock:
            self._remember(key, png_bytes)
            temp = None
            try:
                with NamedTemporaryFile(dir=self.cache_dir, suffix=".tmp", delete=False) as stream:
                    temp = Path(stream.name)
                    stream.write(png_bytes)
                temp.replace(self.cache_dir / f"{key}.png")
            except OSError as exc:
                logger.warning("Could not persist frame: %s", exc)
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)

    def clear(self, dataset_id=None):
        with self._lock:
            prefix = self._prefix(dataset_id) if dataset_id is not None else ""
            for key in list(self._memory_cache):
                if key.startswith(prefix):
                    del self._memory_cache[key]
            for path in self.cache_dir.glob(f"{prefix}*.png"):
                path.unlink(missing_ok=True)


frame_cache = FrameCache()
