"""Offline unit tests for the generic online provider.

Live endpoints are deliberately not part of this suite; they are exercised by
the optional ``live-online`` marker in deployment environments.
"""

import numpy as np
import pytest

from server.data_sources.providers.base import DatasetDefinition, ProviderError, VariableDefinition
from server.data_sources.providers.opendap import OPeNDAPProvider


@pytest.fixture
def dataset_definition():
    return DatasetDefinition(
        id="fixture", name="Fixture", provider="opendap", endpoint="fixture://dataset",
        source="test", description="offline fixture", temporal_resolution="P1D", spatial_resolution="1°",
        variables=(VariableDefinition("salinity", "salt", "Salinity", "PSU", vmin=30, vmax=40),),
    )


@pytest.fixture
def remote_dataset():
    xr = pytest.importorskip("xarray")
    return xr.Dataset(
        {"salt": (("nav_lon", "TIME", "nav_lat"), np.array([[[30, -999], [31, 32]], [[33, 34], [35, 36]]], dtype=np.float32), {"_FillValue": -999.0, "units": "PSU"})},
        coords={
            "TIME": ("TIME", np.array(["2025-01-01T12:00:00", "2025-01-02T12:00:00"], dtype="datetime64[s]"), {"axis": "T"}),
            "nav_lat": ("nav_lat", np.array([-1.0, 1.0]), {"standard_name": "latitude"}),
            "nav_lon": ("nav_lon", np.array([-2.0, 2.0]), {"standard_name": "longitude"}),
        },
    )


def test_inspection_discovers_cf_coordinate_aliases(monkeypatch, dataset_definition, remote_dataset):
    monkeypatch.setattr(OPeNDAPProvider, "_open", staticmethod(lambda _: remote_dataset))
    inspection = OPeNDAPProvider().inspect_dataset(dataset_definition)
    assert inspection.coordinates == {"time": "TIME", "latitude": "nav_lat", "longitude": "nav_lon"}
    assert inspection.variables[0]["dimensions"] == ["nav_lon", "TIME", "nav_lat"]
    assert inspection.timestamps == ["2025-01-01T12:00:00Z", "2025-01-02T12:00:00Z"]


def test_normalization_transposes_masks_and_requires_exact_timestamp(monkeypatch, dataset_definition, remote_dataset):
    monkeypatch.setattr(OPeNDAPProvider, "_open", staticmethod(lambda _: remote_dataset))
    provider = OPeNDAPProvider()
    grid = provider.get_data(dataset_definition, "salinity", "2025-01-01T12:00:00Z", lat_min=-2, lat_max=2, lon_min=-3, lon_max=3, max_pixels=10)
    assert grid.values.shape == (2, 2)
    assert grid.values[0, 0] == 30
    assert np.isnan(grid.values[1, 0])
    with pytest.raises(ProviderError, match="not available"):
        provider.get_data(dataset_definition, "salinity", "2025-02-01T00:00:00Z", lat_min=-2, lat_max=2, lon_min=-3, lon_max=3, max_pixels=10)


def test_registry_is_dataset_first():
    from server.data_sources.online_registry import ONLINE_DATASETS
    assert {"noaa_oisst_v21_2025", "noaa_smap_sss_nrt", "noaa_modis_chlorophyll_nrt"} <= set(ONLINE_DATASETS)
    assert all(dataset.provider == "opendap" for dataset in ONLINE_DATASETS.values())
