"""
Format detection layer for YARA.
Detects scientific data formats using magic byte inspection, directory layout,
and file extension heuristics.
"""

from pathlib import Path
from typing import Union, Tuple
import os
from .common_model import DatasetFormat


def detect_dataset_format(path_or_str: Union[str, Path]) -> Tuple[DatasetFormat, str]:
    """
    Detects dataset format from path.
    Returns (DatasetFormat, explanation/details).
    """
    path = Path(path_or_str)
    if not path.exists():
        return DatasetFormat.UNKNOWN, f"Path does not exist: {path}"

    # 1. Directory inspection (Zarr)
    if path.is_dir():
        # Explicitly check directory names ending with .zarr
        if path.suffix.lower() == ".zarr" or path.name.lower().endswith(".zarr"):
            return DatasetFormat.ZARR, "Detected Zarr dataset directory by name"

        # Check Zarr v2 or v3 markers
        zgroup = path / ".zgroup"
        zattrs = path / ".zattrs"
        zarr_json = path / "zarr.json"
        zarray = path / ".zarray"
        if zgroup.exists() or zattrs.exists() or zarr_json.exists() or zarray.exists():
            return DatasetFormat.ZARR, "Detected Zarr root directory by metadata markers"

        # Check if immediate child subdirectories contain Zarr arrays or groups
        try:
            for child in path.iterdir():
                if child.is_dir() and ((child / ".zarray").exists() or (child / "zarr.json").exists() or (child / ".zgroup").exists()):
                    return DatasetFormat.ZARR, "Detected Zarr group containing child array stores"
        except Exception:
            pass

        return DatasetFormat.UNKNOWN, "Directory does not contain recognized scientific dataset markers (e.g. Zarr)"

    # 2. File inspection via magic bytes
    ext = path.suffix.lower()
    try:
        with open(path, "rb") as f:
            header = f.read(16)
    except Exception as e:
        return DatasetFormat.UNKNOWN, f"Cannot read file header: {e}"

    # NetCDF Classic (CDF1 / CDF2)
    if header.startswith(b"CDF\x01") or header.startswith(b"CDF\x02"):
        return DatasetFormat.NETCDF, "Detected NetCDF Classic header"

    # HDF5 / NetCDF4 (starts with \x89HDF\r\n\x1a\n)
    if header.startswith(b"\x89HDF\r\n\x1a\n"):
        if ext in (".nc", ".netcdf"):
            return DatasetFormat.NETCDF, "Detected NetCDF-4 (HDF5 container)"
        return DatasetFormat.HDF5, "Detected HDF5 container"

    # GeoTIFF / TIFF (II*\x00 little endian or MM\x00* big endian)
    if header.startswith(b"II*\x00") or header.startswith(b"MM\x00*"):
        return DatasetFormat.GEOTIFF, "Detected TIFF/GeoTIFF header"

    # GRIB / GRIB2 (starts with 'GRIB')
    if header.startswith(b"GRIB"):
        return DatasetFormat.GRIB, "Detected GRIB binary header"

    # BUFR (starts with 'BUFR')
    if header.startswith(b"BUFR"):
        return DatasetFormat.BUFR, "Detected BUFR binary header"

    # 3. Extension and text-content heuristics
    if ext in (".nc", ".netcdf"):
        return DatasetFormat.NETCDF, "Identified by .nc extension"
    if ext in (".h5", ".hdf5", ".he5"):
        return DatasetFormat.HDF5, "Identified by HDF5 extension"
    if ext in (".tif", ".tiff"):
        return DatasetFormat.GEOTIFF, "Identified by TIFF extension"
    if ext in (".grib", ".grb", ".grib2"):
        return DatasetFormat.GRIB, "Identified by GRIB extension"
    if ext in (".bufr",):
        return DatasetFormat.BUFR, "Identified by BUFR extension"
    if ext in (".csv",):
        return DatasetFormat.CSV, "Identified by CSV extension"
    if ext in (".asc", ".txt"):
        return DatasetFormat.TEXT_ASCII, "Identified by ASCII/Text extension"
    if ext in (".json", ".geojson"):
        if path.name.lower() in ("zarr.json", "manifest.json"):
            return DatasetFormat.UNKNOWN, "Standalone Zarr metadata file is not a standalone GeoJSON dataset"
        return DatasetFormat.JSON, "Identified by JSON extension"

    return DatasetFormat.UNKNOWN, f"Unrecognized file format with extension '{ext}'"
