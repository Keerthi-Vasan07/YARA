"""
Variable discovery and CF standard name detection utilities for YARA.
Maps variables, detects units, aliases, and selects defaults.
"""

from typing import Dict, List, Optional, Tuple, Set
from .common_model import VariableInfo, VariableType

# CF standard name / variable alias dictionary
VARIABLE_ALIASES: Dict[str, List[str]] = {
    "sst": [
        "sst", "sea_surface_temperature", "temperature", "temp", "surfacetemperature",
        "analysed_sst", "surface_temperature", "tos", "thetao"
    ],
    "anom": [
        "anom", "sst_anomaly", "temperature_anomaly", "anom_sst", "anomaly"
    ],
    "err": [
        "err", "sst_error", "analysis_error", "error", "uncertainty"
    ],
    "ice": [
        "ice", "sea_ice_fraction", "sea_ice_area_fraction", "siconc", "ice_conc",
        "ice_fraction", "sic"
    ],
    "chl": [
        "chl", "chlorophyll", "chlor_a", "mass_concentration_of_chlorophyll_a_in_sea_water",
        "chlorophyll_a", "chla"
    ],
    "sla": [
        "sla", "sea_level_anomaly", "zos", "ssh", "sea_surface_height_above_sea_level",
        "adt", "surface_height"
    ],
    "u_velocity": [
        "u", "uo", "eastward_sea_water_velocity", "water_u", "eastward_velocity",
        "u_current", "u10", "eastward_wind"
    ],
    "v_velocity": [
        "v", "vo", "northward_sea_water_velocity", "water_v", "northward_velocity",
        "v_current", "v10", "northward_wind"
    ],
    "salinity": [
        "sal", "so", "sea_water_salinity", "salinity", "sos", "practical_salinity"
    ]
}

# Coordinate and metadata variable names to exclude from data variable lists
NON_DATA_VARIABLES: Set[str] = {
    "lat", "latitude", "lats", "lon", "longitude", "lons",
    "time", "time_bnds", "time_bounds", "lat_bnds", "lon_bnds", "lat_bounds", "lon_bounds",
    "zlev", "depth", "level", "altitude", "height",
    "crs", "spatial_ref", "grid_mapping", "proj", "lambert",
    "geostationary", "transverse_mercator", "stereographic"
}


def is_coordinate_or_metadata_var(var_name: str, attrs: Dict = None) -> bool:
    """Returns True if the variable is purely coordinate, bounds, or grid mapping."""
    clean = var_name.strip().lower()
    if clean in NON_DATA_VARIABLES:
        return True
    if clean.endswith("_bnds") or clean.endswith("_bounds"):
        return True
    if attrs:
        # Check standard_name / axis
        axis = str(attrs.get("axis", "")).upper()
        if axis in ("X", "Y", "Z", "T"):
            return True
        std_name = str(attrs.get("standard_name", "")).lower()
        if std_name in ("latitude", "longitude", "time", "depth", "grid_mapping_name"):
            return True
    return False


def match_variable_aliases(name: str, standard_name: Optional[str] = None) -> List[str]:
    """Finds all matching aliases for a given variable name and standard name."""
    matches = set()
    name_clean = name.strip().lower()
    std_clean = (standard_name or "").strip().lower()

    for canonical_name, aliases in VARIABLE_ALIASES.items():
        for alias in aliases:
            if alias == name_clean or alias == std_clean:
                matches.add(canonical_name)
                matches.add(alias)
            elif alias in name_clean or (std_clean and alias in std_clean):
                matches.add(canonical_name)

    return sorted(list(matches))


def pick_default_variable(variables: Dict[str, VariableInfo]) -> Optional[str]:
    """Selects the best default variable to display on initial ingestion."""
    if not variables:
        return None

    # Priority order: sst > chl > sla > u/v > ice > anom > first available
    priority = ["sst", "sea_surface_temperature", "chl", "chlorophyll", "sla", "ssh", "ice", "anom"]
    
    var_keys_lower = {k.lower(): k for k in variables.keys()}
    
    # Check direct name matches
    for p in priority:
        if p in var_keys_lower:
            return var_keys_lower[p]

    # Check aliases
    for p in priority:
        for var_name, var_info in variables.items():
            if p in var_info.aliases:
                return var_name

    # Check variables with 2D or 3D spatial grid
    grid_vars = [k for k, v in variables.items() if v.var_type in (VariableType.SCALAR_GRID, VariableType.VECTOR_GRID)]
    if grid_vars:
        return grid_vars[0]

    return list(variables.keys())[0]
