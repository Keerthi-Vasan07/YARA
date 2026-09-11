from abc import ABC, abstractmethod
from typing import Any, Dict


class DataSource(ABC):
    """
    Common interface for every YARA scientific data source.
    """

    @abstractmethod
    def get_metadata(self) -> Dict[str, Any]:
        """Return dataset and variable metadata."""
        raise NotImplementedError

    @abstractmethod
    def get_latest(self) -> Dict[str, Any]:
        """Return the latest available data."""
        raise NotImplementedError

    @abstractmethod
    def is_available(self) -> bool:
        """Check whether the data source is reachable."""
        raise NotImplementedError
