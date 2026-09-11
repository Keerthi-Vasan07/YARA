"""
Reader Registry.

Manages registration and lookup of dataset readers.
"""

import logging
from typing import Dict, Optional, Type

from .base_reader import BaseReader
from .netcdf_reader import NetCDFReader
from .zarr_reader import ZarrReader
from .csv_reader import CSVReader
from .text_reader import TextReader
from .json_reader import JSONReader

logger = logging.getLogger(__name__)


# Format to Reader mapping
READER_REGISTRY: Dict[str, Type[BaseReader]] = {
    'netcdf': NetCDFReader,
    'zarr': ZarrReader,
    'csv': CSVReader,
    'text': TextReader,
    'json': JSONReader,
}


def get_reader(format_name: str) -> Optional[Type[BaseReader]]:
    """
    Get a reader class by format name.
    
    Args:
        format_name: Format name (e.g., 'netcdf', 'zarr')
        
    Returns:
        Reader class or None if not found
    """
    return READER_REGISTRY.get(format_name)


def register_reader(format_name: str, reader_class: Type[BaseReader]) -> None:
    """
    Register a new reader class.
    
    Args:
        format_name: Format name
        reader_class: Reader class
    """
    READER_REGISTRY[format_name] = reader_class
    logger.info(f"[Registry] Registered reader for {format_name}")


def create_reader(format_name: str, path: str, **kwargs) -> Optional[BaseReader]:
    """
    Create a reader instance for the given format and path.
    
    Args:
        format_name: Format name
        path: Path to the dataset
        **kwargs: Additional arguments for the reader
        
    Returns:
        Reader instance or None if format not supported
    """
    reader_class = get_reader(format_name)
    
    if reader_class is None:
        logger.error(f"[Registry] No reader registered for format: {format_name}")
        return None
    
    try:
        reader = reader_class(path, **kwargs)
        logger.info(f"[Registry] Created {format_name} reader for {path}")
        return reader
    except Exception as e:
        logger.error(f"[Registry] Failed to create reader: {e}")
        return None


def get_supported_formats() -> list:
    """Get list of supported formats."""
    return list(READER_REGISTRY.keys())
