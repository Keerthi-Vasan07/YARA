"""Local playback reuses the renderer and includes all analysis options in cache keys."""
import asyncio
from threading import RLock
from ..data_sources.local.registry import registry
from .local_processor import render_slice_to_png
from .frame_cache import frame_cache


class PlaybackManager:
    def __init__(self):
        # netCDF/HDF libraries may not support concurrent access to the same handle.
        self.lock = RLock()

    def revision(self, reader):
        path = reader.file_path
        files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
        return [(str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size) for p in files]

    def get_or_render_frame(self, dataset_id, variable=None, time_index=0, colormap=None,
                            min_val=None, max_val=None, analysis=None):
        with self.lock:
            reader = registry.get_reader(dataset_id)
            name = variable or reader._dataset_info.default_variable
            revision = self.revision(reader)
            cached = frame_cache.get(dataset_id, name, time_index, colormap, min_val, max_val, analysis, revision)
            if cached is not None:
                return cached
            frame = reader.read_frame(name, time_index)
            png = render_slice_to_png(frame, colormap, min_val, max_val, analysis)
            frame_cache.put(dataset_id, name, time_index, png, colormap, min_val, max_val, analysis, revision)
            return png

    async def prefetch_range(self, dataset_id, variable=None, start_index=0, count=10,
                             colormap=None, min_val