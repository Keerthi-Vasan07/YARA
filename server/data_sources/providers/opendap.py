"""Generic OPeNDAP provider backed by xarray's pydap engine.

The code intentionally discovers coordinate names and dimension ordering from
the remote CF metadata.  Registry entries identify scientific variables, not
array order or provider-specific query syntax.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from .base import DatasetDefinition, DatasetInspection, DatasetProvider, NormalizedGrid, ProviderError, VariableDefinition

try:
    import xarray as xr
except ImportError:  # pragma: no cover - exercised by deployment configuration
    xr = None


COORDINATE_ALIASES = {
    "latitude": {"lat", "latitude", "nav_lat", "y"},
    "longitude": {"lon", "longitude", "nav_lon", "x"},
    "time": {"time", "datetime", "date", "time_counter", "TIME"},
}


def _timestamp(value: Any, attrs: dict[str, Any] | None = None) -> str:
    """Return a UI-safe UTC timestamp without silently changing its instant."""
    if value is None:
        return ""
    value = np.asarray(value).item() if np.asarray(value).ndim == 0 else value
    if isinstance(value, (int, float, np.integer, np.floating)):
        if np.isnan(value):
            return ""
        units = (attrs or {}).get("units")
        if not units or "since" not in str(units):
            raise ProviderError("The dataset time coordinate has numeric values without CF time units.")
        if xr is None:
            raise ProviderError("xarray is required to decode CF time coordinates.")
        value = xr.coding.times.decode_cf_datetime(
            np.asarray([value]), units=str(units), calendar=(attrs or {}).get("calendar", "standard")
        )[0]
    if hasattr(value, "isoformat") and callable(getattr(value, "isoformat")):
        try:
            iso = value.isoformat()
            if "T" in iso:
                return iso[:19] + "Z"
            return iso + "Z"
        except Exception:
            pass
    if hasattr(value, "strftime") and callable(getattr(value, "strftime")) and not isinstance(value, np.datetime64):
        try:
            return value.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass
    try:
        text = np.datetime_as_string(np.datetime64(value), unit="s")
        return text.replace("Z", "") + "Z"
    except Exception:
        text = str(value).strip().replace(" ", "T")
        if text.endswith("Z"):
            text = text[:-1]
        return (text[:19] if len(text) >= 19 and "T" in text else text) + "Z"


def _timestamps(coordinate) -> list[str]:
    if coordinate is None:
        return []
    encoding = getattr(coordinate, "encoding", {}) or {}
    attrs_dict = getattr(coordinate, "attrs", {}) or {}
    attrs = {**encoding, **attrs_dict}
    values = getattr(coordinate, "values", None)
    if values is None:
        return []
    return [_timestamp(value, attrs) for value in values]


def _resolution(timestamps: list[str]) -> str:
    if len(timestamps) < 2:
        return "single"
    values = np.array([np.datetime64(value) for value in timestamps])
    seconds = np.diff(values).astype("timedelta64[s]").astype(int)
    if not len(seconds):
        return "single"
    median = int(np.median(seconds))
    return f"PT{median}S" if median < 86400 else f"P{max(1, round(median / 86400))}D"


class OPeNDAPProvider(DatasetProvider):
    name = "opendap"

    @staticmethod
    @lru_cache(maxsize=12)
    def _open(endpoint: str):
        if xr is None:
            raise ProviderError("Online data support requires xarray and pydap.")
        try:
            return xr.open_dataset(endpoint, engine="pydap", decode_times=True, cache=False)
        except Exception as exc:
            raise ProviderError(f"Unable to open OPeNDAP endpoint: {exc}") from exc

    @staticmethod
    def _coordinate_names(ds) -> dict[str, str]:
        if ds is None:
            raise ProviderError("Dataset object is None.")
        coords = getattr(ds, "coords", None)
        dims = getattr(ds, "dims", None)
        variables = getattr(ds, "variables", None) or getattr(ds, "data_vars", None)

        candidates = []
        if coords is not None:
            candidates.extend(list(coords.keys()))
        if dims is not None:
            dim_list = list(dims.keys()) if isinstance(dims, dict) else list(dims)
            for d in dim_list:
                if d not in candidates:
                    candidates.append(d)

        result: dict[str, str] = {}
        for role, aliases in COORDINATE_ALIASES.items():
            for name in candidates:
                variable = coords.get(name) if coords is not None else None
                if variable is None and variables is not None and name in variables:
                    variable = variables.get(name)
                attrs = getattr(variable, "attrs", {}) if variable is not None else {}
                if attrs is None:
                    attrs = {}
                axis = str(attrs.get("axis", "")).upper()
                standard_name = str(attrs.get("standard_name", "")).lower()
                if (name.lower() in {alias.lower() for alias in aliases}
                        or standard_name == role
                        or (role == "latitude" and axis == "Y")
                        or (role == "longitude" and axis == "X")
                        or (role == "time" and axis == "T")):
                    result[role] = name
                    break
        missing = {"latitude", "longitude", "time"} - set(result)
        if missing:
            raise ProviderError(f"Dataset is missing recognizable coordinate(s): {', '.join(sorted(missing))}.")
        return result

    @staticmethod
    def _definition_variable(dataset: DatasetDefinition, variable_id: str) -> VariableDefinition:
        for variable in dataset.variables:
            if variable.id == variable_id:
                return variable
        raise ProviderError(f"Variable '{variable_id}' is not available in dataset '{dataset.id}'.")

    def inspect_dataset(self, dataset: DatasetDefinition) -> DatasetInspection:
        ds = self._open(dataset.endpoint)
        coords = self._coordinate_names(ds)
        time_values = ds[coords["time"]].values
        timestamps = _timestamps(ds[coords["time"]])
        lat = np.asarray(ds[coords["latitude"]].values, dtype=float)
        lon = np.asarray(ds[coords["longitude"]].values, dtype=float)
        variables: list[dict[str, Any]] = []
        for registered in dataset.variables:
            if registered.source_name not in ds:
                continue
            data = ds[registered.source_name]
            item = {
                "id": registered.id,
                "source_name": registered.source_name,
                "name": data.attrs.get("long_name", registered.name),
                "units": data.attrs.get("units", registered.units),
                "type": registered.kind,
                "category": registered.category,
                "vector_group": registered.vector_group,
                "paired_component": registered.paired_component,
                "dimensions": list(data.dims),
                "shape": list(data.shape),
            }
            variables.append(item)
        if not variables:
            raise ProviderError(f"None of the configured variables are exposed by '{dataset.id}'.")
        return DatasetInspection(
            dataset_id=dataset.id,
            coordinates=coords,
            dimensions={name: int(size) for name, size in ds.sizes.items()},
            time_range=(timestamps[0] if timestamps else None, timestamps[-1] if timestamps else None),
            timestamps=timestamps,
            temporal_resolution=_resolution(timestamps),
            coverage={"north": float(np.nanmax(lat)), "south": float(np.nanmin(lat)), "east": float(np.nanmax(lon)), "west": float(np.nanmin(lon))},
            variables=variables,
        )

    def _select_time(self, ds, time_name: str, timestamp: str):
        values = _timestamps(ds[time_name])
        accepted = {timestamp, timestamp.replace("Z", ""), timestamp[:10]}
        matches = [index for index, value in enumerate(values) if value in accepted or value[:10] in accepted]
        if not matches:
            raise ProviderError(f"Timestamp '{timestamp}' is not available for this dataset.")
        return ds.isel({time_name: matches[0]}), values[matches[0]]

    @staticmethod
    def _coordinate_slice(values: np.ndarray, low: float, high: float) -> slice:
        ascending = values[0] <= values[-1]
        start = int(np.searchsorted(values if ascending else values[::-1], low, side="left"))
        stop = int(np.searchsorted(values if ascending else values[::-1], high, side="right"))
        if not ascending:
            size = len(values)
            return slice(max(0, size - stop), min(size, size - start))
        return slice(max(0, start), min(len(values), stop))

    def build_query(self, dataset: DatasetDefinition, variable_id: str, timestamp: str, **_: Any) -> str:
        variable = self._definition_variable(dataset, variable_id)
        # This is a descriptive query identifier; xarray/pydap builds the DAP
        # constraint expression after the inspected dimension order is known.
        return f"{dataset.endpoint}?{variable.source_name}[time={timestamp}]"

    def get_data(self, dataset: DatasetDefinition, variable_id: str, timestamp: str, *, lat_min: float, lat_max: float, lon_min: float, lon_max: float, max_pixels: int) -> NormalizedGrid:
        if lat_min > lat_max or lon_min > lon_max:
            raise ProviderError("Spatial minimum must not exceed maximum.")
        ds = self._open(dataset.endpoint)
        names = self._coordinate_names(ds)
        definition = self._definition_variable(dataset, variable_id)
        if definition.kind != "scalar":
            raise ProviderError(f"'{variable_id}' is a vector component; scalar rendering is not implemented yet.")
        if definition.source_name not in ds:
            raise ProviderError(f"Remote dataset does not expose '{definition.source_name}'.")
        selected, matched_time = self._select_time(ds, names["time"], timestamp)
        data = selected[definition.source_name]
        for dimension in list(data.dims):
            if dimension not in {names["latitude"], names["longitude"]}:
                data = data.isel({dimension: 0})
        # Dimension order varies across providers; the normalized model is
        # always [latitude, longitude], independent of the remote array order.
        data = data.transpose(names["latitude"], names["longitude"])
        lat_values = np.asarray(data[names["latitude"]].values, dtype=float)
        lon_values = np.asarray(data[names["longitude"]].values, dtype=float)
        # Normalize request bounds only for selecting a 0..360 longitude axis.
        query_min, query_max = lon_min, lon_max
        if np.nanmin(lon_values) >= 0 and lon_min < 0:
            # A wrapped request is safely rendered as the complete longitude span.
            query_min, query_max = float(np.nanmin(lon_values)), float(np.nanmax(lon_values))
        indexers = {
            names["latitude"]: self._coordinate_slice(lat_values, lat_min, lat_max),
            names["longitude"]: self._coordinate_slice(lon_values, query_min, query_max),
        }
        data = data.isel(indexers)
        lat_values = np.asarray(data[names["latitude"]].values, dtype=float)
        lon_values = np.asarray(data[names["longitude"]].values, dtype=float)
        if not len(lat_values) or not len(lon_values):
            raise ProviderError("The requested spatial bounds contain no dataset grid cells.")
        stride = max(1, int(np.ceil(max(len(lat_values), len(lon_values)) / max_pixels)))
        data = data.isel({names["latitude"]: slice(None, None, stride), names["longitude"]: slice(None, None, stride)})
        values = np.asarray(data.load().values, dtype=np.float32).squeeze()
        if values.ndim != 2:
            raise ProviderError(f"Variable '{variable_id}' does not reduce to a 2-D geographic surface.")
        fill = data.attrs.get("_FillValue", data.attrs.get("missing_value"))
        if fill is not None and np.isfinite(fill):
            values[np.isclose(values, float(fill))] = np.nan
        valid_min, valid_max = data.attrs.get("valid_min"), data.attrs.get("valid_max")
        if valid_min is not None:
            values[values < float(valid_min)] = np.nan
        if valid_max is not None:
            values[values > float(valid_max)] = np.nan
        lat_values = np.asarray(data[names["latitude"]].values, dtype=float)
        lon_values = np.asarray(data[names["longitude"]].values, dtype=float)
        if np.nanmin(lon_values) >= 0:
            lon_values = np.where(lon_values > 180, lon_values - 360, lon_values)
            order = np.argsort(lon_values)
            lon_values, values = lon_values[order], values[:, order]
        return NormalizedGrid(dataset.id, definition, matched_time, values, lat_values, lon_values, float(fill) if fill is not None and np.isfinite(fill) else None, {"dimensions": list(data.dims), "source_name": definition.source_name})

    def get_point_value(self, dataset: DatasetDefinition, variable_id: str, timestamp: str, *, latitude: float, longitude: float) -> dict[str, Any]:
        grid = self.get_data(dataset, variable_id, timestamp, lat_min=latitude - 0.5, lat_max=latitude + 0.5, lon_min=longitude - 0.5, lon_max=longitude + 0.5, max_pixels=2048)
        yi = int(np.nanargmin(np.abs(grid.latitude - latitude)))
        xi = int(np.nanargmin(np.abs(grid.longitude - longitude)))
        value = grid.values[yi, xi]
        return {"dataset_id": dataset.id, "variable": variable_id, "timestamp": grid.timestamp, "units": grid.variable.units, "requested_lat": latitude, "requested_lon": longitude, "matched_lat": float(grid.latitude[yi]), "matched_lon": float(grid.longitude[xi]), "value": None if not np.isfinite(value) else float(value)}
