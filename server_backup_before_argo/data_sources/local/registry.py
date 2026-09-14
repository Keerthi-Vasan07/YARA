"""
Dataset Reader Registry and Lifecycle Manager for YARA.
Maps formats to readers, manages active reader instances, and manages dataset state.
"""

from pathlib import Path
from typing import Dict, Optional, Type, List, Tuple
import logging

from .common_model import DatasetFormat, DatasetInfo
from .detector import detect_dataset_format
from .base_reader import BaseScientificReader
from .netcdf_reader import NetCDFReader
from .zarr_reader import ZarrReader
from .geotiff_reader import GeoTIFFReader
from .hdf5_reader import HDF5Reader
from .csv_reader import CSVReader
from .text_reader import TextASCIIReader
from .json_reader import JSONReader
from .grib_reader import GRIBReader
from .bufr_reader import BUFRReader

logger = logging.getLogger(__name__)

READER_MAP: Dict[DatasetFormat, Type[BaseScientificReader]] = {
    DatasetFormat.NETCDF: NetCDFReader,
    DatasetFormat.ZARR: ZarrReader,
    DatasetFormat.GEOTIFF: GeoTIFFReader,
    DatasetFormat.HDF5: HDF5Reader,
    DatasetFormat.CSV: CSVReader,
    DatasetFormat.TEXT_ASCII: TextASCIIReader,
    DatasetFormat.JSON: JSONReader,
    DatasetFormat.GRIB: GRIBReader,
    DatasetFormat.BUFR: BUFRReader,
}


class DatasetRegistry:
    """Manages registered datasets, reader instances, and active dataset state."""

    def __init__(self):
        self._readers: Dict[str, BaseScientificReader] = {}
        self._active_dataset_id: Optional[str] = None
        self._registered_files: Dict[str, Path] = {}

    def get_reader_class(self, fmt: DatasetFormat) -> Optional[Type[BaseScientificReader]]:
        return READER_MAP.get(fmt)

    def register_file(self, file_path: Path, dataset_id: Optional[str] = None) -> Tuple[DatasetInfo, BaseScientificReader]:
        """Registers a local file or directory, detects format, and returns metadata and reader."""
        file_path = Path(file_path).resolve()
        if not file_path.exists():
            raise FileNotFoundError(f"Dataset path does not exist: {file_path}")

        fmt, reason = detect_dataset_format(file_path)
        if fmt == DatasetFormat.UNKNOWN:
            raise ValueError(f"Unsupported scientific dataset format: {reason}")

        reader_cls = self.get_reader_class(fmt)
        if not reader_cls:
            raise ValueError(f"No reader implementation for format: {fmt}")

        # Use exact name (including .zarr or .nc) to prevent ID collisions
        ds_id = dataset_id or file_path.name
        reader = reader_cls(file_path, dataset_id=ds_id)
        info = reader.inspect()

        # Store
        self._registered_files[ds_id] = file_path
        self._readers[ds_id] = reader
        logger.info(f"Registered dataset '{ds_id}' ({fmt.value}): {len(info.variables)} vars, {info.time_axis.count} times")
        return info, reader

    def get_reader(self, dataset_id: str) -> BaseScientificReader:
        if dataset_id in self._readers:
            return self._readers[dataset_id]
        if dataset_id in self._registered_files:
            _, reader = self.register_file(self._registered_files[dataset_id], dataset_id)
            return reader
        # Fallback: check if dataset_id matches any registered file by stem or name
        for reg_id, file_path in list(self._registered_files.items()):
            if reg_id == dataset_id or file_path.name == dataset_id or file_path.stem == dataset_id:
                if reg_id in self._readers:
                    return self._readers[reg_id]
                _, reader = self.register_file(file_path, reg_id)
                return reader
        raise KeyError(f"Dataset '{dataset_id}' is not registered.")

    def set_active(self, dataset_id: Optional[str]) -> Optional[DatasetInfo]:
        """Sets the active local dataset. If None, deactivates local mode (switches to Online)."""
        if dataset_id is None:
            self._active_dataset_id = None
            logger.info("Local dataset mode deactivated. Switched to Online Mode.")
            return None

        reader = self.get_reader(dataset_id)
        self._active_dataset_id = reader.dataset_id
        logger.info(f"Activated local dataset: {self._active_dataset_id}")
        return reader._dataset_info

    def get_active(self) -> Tuple[Optional[str], Optional[DatasetInfo]]:
        """Returns (active_dataset_id, DatasetInfo) or (None, None)."""
        if not self._active_dataset_id:
            return None, None
        try:
            reader = self.get_reader(self._active_dataset_id)
            return self._active_dataset_id, reader._dataset_info
        except Exception:
            self._active_dataset_id = None
            return None, None

    def list_datasets(self) -> List[DatasetInfo]:
        """Lists metadata for all registered datasets."""
        results = []
        for ds_id in list(self._registered_files.keys()):
            try:
                reader = self.get_reader(ds_id)
                if reader and reader._dataset_info:
                    results.append(reader._dataset_info)
            except Exception as e:
                logger.warning(f"Error reading dataset {ds_id}: {e}")
        return results

    def scan_directory(self, dir_path: Path):
        """Scans a directory (e.g. local_dataset/) and automatically registers all valid scientific datasets."""
        dir_path = Path(dir_path)
        if not dir_path.exists() or not dir_path.is_dir():
            return

        for item in sorted(dir_path.iterdir()):
            # Skip hidden files or temp files
            if item.name.startswith(".") or item.name.startswith("__"):
                continue
            try:
                fmt, _ = detect_dataset_format(item)
                if fmt != DatasetFormat.UNKNOWN:
                    ds_id = item.name
                    if ds_id not in self._registered_files:
                        self.register_file(item, dataset_id=ds_id)
            except Exception as e:
                logger.warning(f"Scan skipped {item.name}: {e}")

    def close_all(self):
        """Closes all readers."""
        for reader in self._readers.values():
            try:
                reader.close()
            except Exception:
                pass
        self._readers.clear()


# Global registry singleton
registry = DatasetRegistry()
