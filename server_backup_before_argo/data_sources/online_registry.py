"""
YARA ONLINE DATASET REGISTRY
Canonical Copernicus Marine Global Ocean Physics reanalysis.

Primary dataset:
    cmems_mod_glo_phy_my_0.083deg_P1D-m

Product:
    GLOBAL_MULTIYEAR_PHY_001_030

All 11 variables are exposed through the same logical YARA online-data
interface. Remote access is performed by erddap_opendap.py using the
Copernicus Marine Python Toolbox (open_dataset), which returns an xarray
Dataset backed by lazy remote/Dask arrays.
"""

from typing import Any, Dict

COPERNICUS_DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"
COPERNICUS_OPENDAP_URL = (
    "https://my.cmems-du.eu/thredds/dodsC/"
    + COPERNICUS_DATASET_ID
)

COPERNICUS_DATASET = {
    "dataset_id": COPERNICUS_DATASET_ID,
    "product_id": "GLOBAL_MULTIYEAR_PHY_001_030",
    "display_name": "Global Ocean Physics Reanalysis",
    "temporal_resolution": "daily",
    "spatial_resolution_deg": 0.083333,
    "source": "Copernicus Marine Service",
    "provider": "Copernicus",
    "access": "OPeNDAP / Copernicus Marine Toolbox / xarray",
    "opendap_url": COPERNICUS_OPENDAP_URL,
}

_DEFAULT_COLOR_STOPS = [
    (0.00, 0, 20, 80),
    (0.20, 0, 100, 180),
    (0.40, 0, 180, 220),
    (0.60, 80, 210, 150),
    (0.75, 220, 220, 50),
    (0.90, 255, 100, 0),
    (1.00, 180, 0, 0),
]

ONLINE_DATASETS: Dict[str, Dict[str, Any]] = {
    "thetao": {
        "variable_key": "thetao", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "thetao", "display_name": "Sea Water Potential Temperature",
        "units": "degrees_C", "units_display": "°C",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "depth", "latitude", "longitude"], "is_3d": True,
        "vmin": -2.0, "vmax": 35.0, "log_scale": False,
        "colormap": "plasma", "colorbar_label": "Sea Water Potential Temperature (°C)",
        "description": "Three-dimensional sea water potential temperature.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL,
        "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "so": {
        "variable_key": "so", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "so", "display_name": "Sea Water Salinity",
        "units": "1", "units_display": "PSU",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "depth", "latitude", "longitude"], "is_3d": True,
        "vmin": 30.0, "vmax": 40.0, "log_scale": False,
        "colormap": "viridis", "colorbar_label": "Sea Water Salinity (PSU)",
        "description": "Three-dimensional sea water salinity.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "uo": {
        "variable_key": "uo", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "uo", "display_name": "Eastward Sea Water Velocity",
        "units": "m s-1", "units_display": "m/s",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "depth", "latitude", "longitude"], "is_3d": True,
        "vmin": -2.0, "vmax": 2.0, "log_scale": False,
        "colormap": "coolwarm", "colorbar_label": "U Current (m/s)",
        "description": "Eastward sea water velocity.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "vo": {
        "variable_key": "vo", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "vo", "display_name": "Northward Sea Water Velocity",
        "units": "m s-1", "units_display": "m/s",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "depth", "latitude", "longitude"], "is_3d": True,
        "vmin": -2.0, "vmax": 2.0, "log_scale": False,
        "colormap": "coolwarm", "colorbar_label": "V Current (m/s)",
        "description": "Northward sea water velocity.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "zos": {
        "variable_key": "zos", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "zos", "display_name": "Sea Surface Height Above Geoid",
        "units": "m", "units_display": "m",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": -2.0, "vmax": 2.0, "log_scale": False,
        "colormap": "coolwarm", "colorbar_label": "Sea Surface Height (m)",
        "description": "Sea surface height above geoid.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "mlotst": {
        "variable_key": "mlotst", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "mlotst", "display_name": "Ocean Mixed Layer Thickness",
        "units": "m", "units_display": "m",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": 0.0, "vmax": 500.0, "log_scale": False,
        "colormap": "viridis", "colorbar_label": "Mixed Layer Thickness (m)",
        "description": "Ocean mixed layer thickness.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "bottomT": {
        "variable_key": "bottomT", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "bottomT", "display_name": "Bottom Temperature",
        "units": "degrees_C", "units_display": "°C",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": -2.0, "vmax": 35.0, "log_scale": False,
        "colormap": "plasma", "colorbar_label": "Bottom Temperature (°C)",
        "description": "Sea water temperature at the ocean bottom.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "siconc": {
        "variable_key": "siconc", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "siconc", "display_name": "Sea Ice Concentration",
        "units": "1", "units_display": "fraction",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": 0.0, "vmax": 1.0, "log_scale": False,
        "colormap": "viridis", "colorbar_label": "Sea Ice Concentration",
        "description": "Sea ice concentration fraction.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "sithick": {
        "variable_key": "sithick", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "sithick", "display_name": "Sea Ice Thickness",
        "units": "m", "units_display": "m",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": 0.0, "vmax": 10.0, "log_scale": False,
        "colormap": "viridis", "colorbar_label": "Sea Ice Thickness (m)",
        "description": "Sea ice thickness.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "usi": {
        "variable_key": "usi", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "usi", "display_name": "Sea Ice Eastward Velocity",
        "units": "m s-1", "units_display": "m/s",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": -1.0, "vmax": 1.0, "log_scale": False,
        "colormap": "coolwarm", "colorbar_label": "Sea Ice U Velocity (m/s)",
        "description": "Eastward sea ice velocity.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
    "vsi": {
        "variable_key": "vsi", "dataset_id": COPERNICUS_DATASET_ID,
        "variable": "vsi", "display_name": "Sea Ice Northward Velocity",
        "units": "m s-1", "units_display": "m/s",
        "temporal_resolution": "daily", "spatial_resolution_deg": 0.083333,
        "dimensions": ["time", "latitude", "longitude"], "is_3d": False,
        "vmin": -1.0, "vmax": 1.0, "log_scale": False,
        "colormap": "coolwarm", "colorbar_label": "Sea Ice V Velocity (m/s)",
        "description": "Northward sea ice velocity.",
        "source": "Copernicus Marine Service", "provider": "Copernicus",
        "opendap_url": COPERNICUS_OPENDAP_URL, "color_stops": _DEFAULT_COLOR_STOPS,
    },
}

def get_dataset_config(variable: str) -> Dict[str, Any]:
    key = str(variable).strip()
    if key not in ONLINE_DATASETS:
        raise KeyError(key)
    return ONLINE_DATASETS[key]

def list_variables() -> list[str]:
    return list(ONLINE_DATASETS.keys())
