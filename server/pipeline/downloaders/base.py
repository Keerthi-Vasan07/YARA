"""
Base Downloader Class

Abstract base for variable-specific downloaders.
"""

import logging
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Literal

from server.pipeline.config import get_config, VariableConfig

logger = logging.getLogger(__name__)


class BaseDownloader(ABC):
    """Base class for ECV variable downloaders."""
    
    variable: str = ""  # Override in subclass
    
    def __init__(self):
        self.config = get_config()
        self.var_config = self.config.get_variable_config(self.variable)
    
    def download_and_convert(
        self,
        date: str,
        stream: Literal["nrt", "rep", "auto"] = "auto",
        force: bool = False,
    ) -> dict[str, Any] | None:
        """
        Download data for a date and convert to COG.
        
        Args:
            date: Date string (YYYY-MM-DD)
            stream: Data stream (nrt, rep, or auto)
            force: Force re-download even if exists
            
        Returns:
            Dict with stats and metadata, or None on failure
        """
        cog_path = self.config.get_cog_path(self.variable, date)
        
        # Check if already exists
        if cog_path.exists() and not force:
            logger.info(f"Already exists: {cog_path}")
            return {"status": "exists", "path": str(cog_path)}
        
        # Determine which stream to use
        if stream == "auto":
            stream = self._select_stream(date)
        
        # Create temp directory for download
        with tempfile.TemporaryDirectory(prefix=f"arco3d_{self.variable}_") as temp_dir:
            temp_path = Path(temp_dir)
            
            # Download
            nc_path = self._download(date, stream, temp_path)
            if nc_path is None:
                # Try fallback stream (both directions)
                fallback = "rep" if stream == "nrt" else "nrt"
                logger.info(f"{stream.upper()} download failed, trying {fallback.upper()}...")
                nc_path = self._download(date, fallback, temp_path)
                if nc_path is not None:
                    stream = fallback  # Update stream for metadata
                
                if nc_path is None:
                    logger.error(f"Download failed for {self.variable}/{date}")
                    return None
            
            # Convert to COG
            stats = self._convert(nc_path, cog_path, date)
            if stats is None:
                logger.error(f"Conversion failed for {self.variable}/{date}")
                return None
            
            return {
                "status": "success",
                "path": str(cog_path),
                "stream": stream,
                "stats": stats,
            }
    
    def _select_stream(self, date: str) -> Literal["nrt", "rep"]:
        """Select appropriate stream based on date."""
        from datetime import datetime, timedelta
        
        # Parse date
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return "rep"
        
        # Use NRT for recent dates, REP for historical
        # Typically REP data lags 1-3 months behind
        cutoff = datetime.now() - timedelta(days=90)
        
        if dt > cutoff:
            return "nrt"
        return "rep"
    
    @abstractmethod
    def _download(self, date: str, stream: str, temp_dir: Path) -> Path | None:
        """
        Download data for a date.
        
        Override in subclass to implement variable-specific download logic.
        
        Returns:
            Path to downloaded file(s), or None on failure
        """
        pass
    
    @abstractmethod
    def _convert(self, nc_path: Path, cog_path: Path, date: str) -> dict[str, Any] | None:
        """
        Convert downloaded data to COG.
        
        Override in subclass to implement variable-specific conversion.
        
        Returns:
            Statistics dict, or None on failure
        """
        pass
