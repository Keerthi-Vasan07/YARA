"""
Variable-specific downloaders for ECV data.
"""

from server.pipeline.downloaders.base import BaseDownloader
from server.pipeline.downloaders.sst import SSTDownloader
from server.pipeline.downloaders.sic import SICDownloader
from server.pipeline.downloaders.sla import SLADownloader
from server.pipeline.downloaders.chl import CHLDownloader
from server.pipeline.downloaders.kd490 import Kd490Downloader
from server.pipeline.downloaders.rrs import RrsDownloader

# Map variable names to downloader classes
DOWNLOADERS: dict[str, type[BaseDownloader]] = {
    "sst": SSTDownloader,
    "sic": SICDownloader,
    "sla": SLADownloader,
    "chl": CHLDownloader,
    "kd490": Kd490Downloader,
    "rrs": RrsDownloader,
}


def get_downloader(variable: str) -> BaseDownloader:
    """Get downloader instance for a variable."""
    if variable not in DOWNLOADERS:
        raise ValueError(f"Unknown variable: {variable}. Valid: {list(DOWNLOADERS.keys())}")
    return DOWNLOADERS[variable]()


__all__ = [
    "BaseDownloader",
    "SSTDownloader",
    "SICDownloader",
    "SLADownloader",
    "CHLDownloader",
    "Kd490Downloader",
    "RrsDownloader",
    "DOWNLOADERS",
    "get_downloader",
]
