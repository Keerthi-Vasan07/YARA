"""
Format Detection.

Detects the format of a scientific dataset based on:
- File extension
- File signatures/content
- Directory structure (for Zarr)
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any


# Supported formats and their extensions
FORMAT_EXTENSIONS = {
    'netcdf': ['.nc', '.netcdf', '.nc4'],
    'csv': ['.csv'],
    'text': ['.txt', '.asc'],
    'json': ['.json'],
    'grib': ['.grib', '.grb', '.grib2'],
    'hdf5': ['.h5', '.hdf5'],
    'geotiff': ['.tif', '.tiff'],
    'bufr': ['.bufr'],
    'zarr': ['.zarr'],  # Can also be a directory
}

# Format priorities (for ambiguous cases)
FORMAT_PRIORITY = {
    'zarr': 1,
    'netcdf': 2,
    'hdf5': 3,
    'grib': 4,
    'geotiff': 5,
    'bufr': 6,
    'csv': 7,
    'json': 8,
    'text': 9,
}


class FormatDetector:
    """
    Detects the format of a scientific dataset.
    """
    
    def __init__(self):
        self._signature_cache: Dict[str, str] = {}
    
    def detect(self, path: str) -> Optional[str]:
        """
        Detect the format of a file or directory.
        
        Args:
            path: Path to the file or directory
            
        Returns:
            Format name (e.g., 'netcdf', 'zarr') or None if unknown
        """
        path_obj = Path(path)
        
        if not path_obj.exists():
            return None
        
        # Check if it's a Zarr directory first
        if path_obj.is_dir():
            if self._is_zarr_directory(path_obj):
                return 'zarr'
            return None
        
        # Check by extension
        ext = path_obj.suffix.lower()
        
        for format_name, extensions in FORMAT_EXTENSIONS.items():
            if ext in extensions:
                # Verify with content signature if possible
                if format_name == 'netcdf':
                    if self._verify_netcdf_signature(path):
                        return 'netcdf'
                elif format_name == 'hdf5':
                    if self._verify_hdf5_signature(path):
                        return 'hdf5'
                elif format_name == 'grib':
                    if self._verify_grib_signature(path):
                        return 'grib'
                elif format_name == 'geotiff':
                    if self._verify_geotiff_signature(path):
                        return 'geotiff'
                else:
                    return format_name
        
        # Try to detect by content for extensionless files
        return self._detect_by_content(path)
    
    def _is_zarr_directory(self, path: Path) -> bool:
        """Check if a directory is a Zarr dataset."""
        # Zarr v2: .zgroup file at root
        zgroup = path / '.zgroup'
        if zgroup.exists():
            return True
        
        # Zarr v3: zarr.json at root
        zarr_json = path / 'zarr.json'
        if zarr_json.exists():
            return True
        
        return False
    
    def _verify_netcdf_signature(self, path: str) -> bool:
        """Verify NetCDF signature by reading file header."""
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
                # NetCDF magic number: 'CDF\x01' or 'CDF\x02'
                if header[:3] == b'CDF':
                    return True
                # HDF5-based NetCDF starts with HDF5 magic
                if header == b'\x89HDF':
                    return True
        except Exception:
            pass
        return False
    
    def _verify_hdf5_signature(self, path: str) -> bool:
        """Verify HDF5 signature."""
        try:
            with open(path, 'rb') as f:
                header = f.read(8)
                # HDF5 magic number
                if header == b'\x89HDF\r\n\x1a\n':
                    return True
        except Exception:
            pass
        return False
    
    def _verify_grib_signature(self, path: str) -> bool:
        """Verify GRIB signature."""
        try:
            with open(path, 'rb') as f:
                header = f.read(4)
                # GRIB magic: 'GRIB'
                if header == b'GRIB':
                    return True
        except Exception:
            pass
        return False
    
    def _verify_geotiff_signature(self, path: str) -> bool:
        """Verify GeoTIFF signature."""
        try:
            with open(path, 'rb') as f:
                header = f.read(2)
                # TIFF byte order markers
                if header in (b'II', b'MM'):
                    return True
        except Exception:
            pass
        return False
    
    def _detect_by_content(self, path: str) -> Optional[str]:
        """Try to detect format by reading file content."""
        try:
            with open(path, 'rb') as f:
                header = f.read(100)
                
                # Check for various signatures
                if header[:3] == b'CDF':
                    return 'netcdf'
                if header == b'\x89HDF\r\n\x1a\n':
                    return 'hdf5'
                if header[:4] == b'GRIB':
                    return 'grib'
                if header[:2] in (b'II', b'MM'):
                    return 'geotiff'
                
                # Try text-based detection
                try:
                    with open(path, 'r', encoding='utf-8') as tf:
                        content = tf.read(500)
                        if content.strip().startswith('{') or content.strip().startswith('['):
                            return 'json'
                        if ',' in content and '\n' in content:
                            return 'csv'
                        return 'text'
                except UnicodeDecodeError:
                    pass
                    
        except Exception:
            pass
        
        return None


def detect_format(path: str) -> Optional[str]:
    """
    Convenience function to detect format.
    
    Args:
        path: Path to the file or directory
        
    Returns:
        Format name or None
    """
    detector = FormatDetector()
    return detector.detect(path)


def get_supported_formats() -> Dict[str, list]:
    """Get dictionary of supported formats and their extensions."""
    return FORMAT_EXTENSIONS.copy()
