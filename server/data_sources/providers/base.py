"""Provider-neutral models for remotely hosted scientific datasets."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np


class ProviderError(RuntimeError):
    """A safe, actionable error suitable for the online API response."""


@dataclass(frozen=True)
class VariableDefinition:
    id: str
    source_name: str
    name: str
    units: str
    kind: str = "scalar"
    category: str = "ocean"
    vector_group: str | None = None
    paired_component: str | None = None
    colormap: str = "viridis"
    vmin: float | None = None
    vmax: float | None = None
    log_scale: bool = False


@dataclass(frozen=True)
class DatasetDefinition:
    id: str
    name: str
    provider: str
    endpoint: str
    source: str
    description: str
    variables: tuple[VariableDefinition, ...]
    temporal_resolution: str
    spatial_resolution: str
    coverage: dict[str, float] = field(default_factory=dict)
    capabilities: dict[str, bool] = field(default_factory=dict)

    def public(self) -> dict[str, Any]:
        result = asdict(self)
        result["variables"] = [asdict(variable) for variable in self.variables]
        return result


@dataclass
class DatasetInspection:
    dataset_id: str
    coordinates: dict[str, str]
    dimensions: dict[str, int]
    time_range: tuple[str | None, str | None]
    timestamps: list[str]
    temporal_resolution: str
    coverage: dict[str, float]
    variables: list[dict[str, Any]]

    def public(self, *, include_timestamps: bool = False) -> dict[str, Any]:
        result = asdict(self)
        if not include_timestamps:
            result.pop("timestamps")
        return result


@dataclass
class NormalizedGrid:
    """Provider-neutral 2-D scalar frame consumed by the PNG/Cesium adapter."""

    dataset_id: str
    variable: VariableDefinition
    timestamp: str
    values: np.ndarray
    latitude: np.ndarray
    longitude: np.ndarray
    missing_value: float | None
    metadata: dict[str, Any]

    @property
    def min(self) -> float | None:
        finite = self.values[np.isfinite(self.values)]
        return float(finite.min()) if finite.size else None

    @property
    def max(self) -> float | None:
        finite = self.values[np.isfinite(self.values)]
        return float(finite.max()) if finite.size else None


class DatasetProvider(ABC):
    """The stable contract implemented by each online transport/provider."""

    @abstractmethod
    def inspect_dataset(self, dataset: DatasetDefinition) -> DatasetInspection: ...

    @abstractmethod
    def get_data(
        self, dataset: DatasetDefinition, variable_id: str, timestamp: str,
        *, lat_min: float, lat_max: float, lon_min: float, lon_max: float,
        max_pixels: int,
    ) -> NormalizedGrid: ...

    @abstractmethod
    def get_point_value(
        self, dataset: DatasetDefinition, variable_id: str, timestamp: str,
        *, latitude: float, longitude: float,
    ) -> dict[str, Any]: ...

    @abstractmethod
    def build_query(self, *args: Any, **kwargs: Any) -> str: ...
