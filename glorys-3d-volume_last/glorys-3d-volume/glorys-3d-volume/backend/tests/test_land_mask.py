"""
test_land_mask.py

Comprehensive test suite verifying global land-sea boundary masking:
1. geo_service: land fraction, 2D masking, and point land queries.
2. volume_service: rejection of 100% continental landmass and coastal NaN void carving.
3. column_profile_service: detection of dry land coordinates during vertical probing.
"""

import json
import struct
import numpy as np
import pytest

from backend.services.geo_service import (
    check_region_land_fraction,
    get_2d_land_mask,
    is_point_land,
    normalize_lon,
)
from backend.services.volume_service import (
    generate_synthetic_ocean_volume,
    extract_volume_safe,
)
from backend.column_profile_service import extract_vertical_profile_sync


def test_is_point_land():
    # Continental Eastern Europe: 49.1N, 22.8E
    assert is_point_land(49.1, 22.8) is True
    # Inland Sahara: 25.0N, 15.0E
    assert is_point_land(25.0, 15.0) is True
    # Indian Ocean: 10.0N, 75.0E
    assert is_point_land(10.0, 75.0) is False
    # Central Pacific: 0.0N, -140.0E
    assert is_point_land(0.0, -140.0) is False


def test_check_region_land_fraction():
    # Eastern Europe pure land
    ee_frac = check_region_land_fraction(48.0, 52.0, 20.0, 25.0, samples=20)
    assert ee_frac == 1.0

    # Open Indian Ocean
    ocean_frac = check_region_land_fraction(-10.0, 0.0, 70.0, 80.0, samples=20)
    assert ocean_frac == 0.0

    # Coastal Black Sea
    coastal_frac = check_region_land_fraction(40.0, 45.0, 28.0, 33.0, samples=20)
    assert 0.1 < coastal_frac < 0.9


def test_get_2d_land_mask():
    lats = np.array([45.0, 46.0, 47.0])
    lons = np.array([22.0, 23.0, 24.0, 25.0])
    mask = get_2d_land_mask(lats, lons)
    assert mask.shape == (3, 4)
    assert mask.dtype == bool
    assert bool(mask.all()) is True  # All on land in Eastern Europe


def test_synthetic_volume_rejection_on_pure_land():
    with pytest.raises(ValueError) as exc_info:
        generate_synthetic_ocean_volume(
            min_lat=48.0,
            max_lat=52.0,
            min_lon=20.0,
            max_lon=25.0,
            variable="thetao",
        )
    assert "Terrestrial Landmass Selected" in str(exc_info.value)


@pytest.mark.asyncio
async def test_extract_volume_safe_rejection_on_pure_land():
    with pytest.raises(ValueError) as exc_info:
        await extract_volume_safe(
            min_lat=48.0,
            max_lat=51.0,
            min_lon=21.0,
            max_lon=24.0,
            date_str="2026-06-23",
            variable="thetao",
        )
    assert "Terrestrial Landmass Selected" in str(exc_info.value)


def test_synthetic_volume_coastal_carving():
    # Coastal Black Sea: 40..45N, 28..33E
    pkt = generate_synthetic_ocean_volume(
        min_lat=40.0,
        max_lat=45.0,
        min_lon=28.0,
        max_lon=33.0,
        variable="thetao",
        dims=(31, 31, 15),
    )
    assert len(pkt) > 4
    meta_len = struct.unpack(">I", pkt[:4])[0]
    meta = json.loads(pkt[4 : 4 + meta_len].decode("utf-8"))
    raw = np.frombuffer(pkt[4 + meta_len :], dtype=np.float32)

    assert meta["has_land_mask"] is True
    assert 0.1 < meta["land_fraction"] < 0.9

    nan_count = int(np.isnan(raw).sum())
    valid_count = int(np.sum(~np.isnan(raw)))
    assert nan_count > 0, "Land voxels must be carved out as NaN"
    assert valid_count > 0, "Ocean voxels must have valid Float32 values"


def test_column_profile_land_detection():
    # Probing Eastern Europe continental coordinate
    res = extract_vertical_profile_sync(49.1, 22.8)
    assert res.get("is_land") is True
    assert len(res.get("profile", [])) == 0
    assert "Terrestrial Landmass" in res.get("message", "")
