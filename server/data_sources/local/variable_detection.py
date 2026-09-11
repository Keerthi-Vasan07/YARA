"""
Variable Detection.

Functions for detecting and mapping scientific variables in datasets.
"""

from typing import List, Optional, Dict, Any
import numpy as np
import xarray as xr

from .common_model import Variable


# CF standard names for common oceanographic/atmospheric variables
STANDARD_NAME_MAP = {
    # Temperature
    'sea_surface_temperature': ['sst', 'temperature', 'temp'],
    'sea_water_temperature': ['water_temp', 'ocean_temp'],
    'air_temperature': ['air_temp', 'ta'],
    
    # Currents
    'sea_water_x_velocity': ['u', 'water_u', 'ucurr'],
    'sea_water_y_velocity': ['v', 'water_v', 'vcurr'],
    'eastward_sea_water_velocity': ['u', 'water_u'],
    'northward_sea_water_velocity': ['v', 'water_v'],
    
    # Wind
    'wind_speed': ['wspd', 'wind_speed'],
    'wind_direction': ['wdir', 'wind_dir'],
    'x_wind': ['uwind', 'wind_u'],
    'y_wind': ['vwind', 'wind_v'],
    
    # Salinity
    'sea_surface_salinity': ['sss', 'salinity'],
    'sea_water_salinity': ['salt', 'sal'],
    
    # Sea level
    'sea_level_anomaly': ['sla', 'ssh'],
    'sea_surface_height_above_geoid': ['adt', 'ssh'],
    
    # Ice
    'sea_ice_area_fraction': ['sic', 'ice_conc', 'ice_fraction'],
    'sea_ice_thickness': ['sit', 'ice_thick'],
    
    # Chlorophyll
    'mass_concentration_of_chlorophyll_in_sea_water': ['chl', 'chlorophyll'],
    'chlorophyll_mass_concentration': ['chl', 'chlor'],
    
    # Diffuse attenuation
    'diffuse_attenuation_coefficient_of_downwelling_shortwave_radiation_in_sea_water': ['kd490', 'kd'],
    
    # Other
    'pressure': ['pres', 'pressure'],
    'density': ['dens', 'density', 'sigma_t'],
}


# Reverse map: variable name -> standard name
VARIABLE_TO_STANDARD = {}
for std_name, aliases in STANDARD_NAME_MAP.items():
    for alias in aliases:
        VARIABLE_TO_STANDARD[alias.lower()] = std_name


def detect_scientific_variables(ds: xr.Dataset) -> List[Variable]:
    """
    Detect scientific variables in an xarray Dataset.
    
    Uses CF standard names, long names, and variable names to identify
    scientific variables.
    
    Args:
        ds: xarray Dataset
        
    Returns:
        List of Variable objects
    """
    variables = []
    
    for var_name in ds.data_vars:
        var = ds[var_name]
        
        # Skip coordinate variables
        if var_name in ds.coords:
            continue
        
        # Get metadata
        std_name = var.attrs.get('standard_name')
        long_name = var.attrs.get('long_name')
        units = var.attrs.get('units')
        
        # Try to map to standard name
        if not std_name:
            std_name = map_variable_name(var_name)
        
        # Determine dimensions
        dims = list(var.dims)
        
        # Compute statistics if feasible
        min_val = None
        max_val = None
        fill_value = var.attrs.get('_FillValue', var.attrs.get('missing_value'))
        
        if var.size < 1e6:
            try:
                data = var.values
                valid_data = data[~np.isnan(data)]
                if fill_value is not None:
                    valid_data = valid_data[valid_data != fill_value]
                if len(valid_data) > 0:
                    min_val = float(np.min(valid_data))
                    max_val = float(np.max(valid_data))
            except Exception:
                pass
        
        variable = Variable(
            name=var_name,
            standard_name=std_name,
            long_name=long_name or var_name,
            units=units,
            dimensions=dims,
            dtype=str(var.dtype),
            min=min_val,
            max=max_val,
            fill_value=float(fill_value) if fill_value is not None else None,
        )
        
        variables.append(variable)
    
    return variables


def map_variable_name(var_name: str) -> Optional[str]:
    """
    Map a variable name to its CF standard name.
    
    Args:
        var_name: Variable name from dataset
        
    Returns:
        CF standard name or None if not found
    """
    var_lower = var_name.lower()
    
    # Direct match
    if var_lower in VARIABLE_TO_STANDARD:
        return VARIABLE_TO_STANDARD[var_lower]
    
    # Partial match
    for alias, std_name in VARIABLE_TO_STANDARD.items():
        if alias in var_lower or var_lower in alias:
            return std_name
    
    return None


def get_variable_metadata(
    ds: xr.Dataset,
    variable_name: str,
) -> Optional[Dict[str, Any]]:
    """
    Get metadata for a specific variable.
    
    Args:
        ds: xarray Dataset
        variable_name: Name of the variable
        
    Returns:
        Dictionary with variable metadata or None if not found
    """
    if variable_name not in ds.data_vars:
        return None
    
    var = ds[variable_name]
    
    return {
        'name': variable_name,
        'standard_name': var.attrs.get('standard_name'),
        'long_name': var.attrs.get('long_name'),
        'units': var.attrs.get('units'),
        'dimensions': list(var.dims),
        'dtype': str(var.dtype),
        'attributes': dict(var.attrs),
    }


def find_primary_variable(ds: xr.Dataset, category: str) -> Optional[str]:
    """
    Find the primary variable for a given category.
    
    Args:
        ds: xarray Dataset
        category: Category name ('temperature', 'currents', 'wind', etc.)
        
    Returns:
        Variable name or None
    """
    category_vars = {
        'temperature': ['sea_surface_temperature', 'sea_water_temperature', 'sst', 'temp'],
        'currents': ['sea_water_x_velocity', 'sea_water_y_velocity', 'u', 'v'],
        'wind': ['wind_speed', 'x_wind', 'y_wind'],
        'salinity': ['sea_surface_salinity', 'sea_water_salinity'],
        'sea_level': ['sea_level_anomaly', 'sea_surface_height_above_geoid'],
        'ice': ['sea_ice_area_fraction', 'sea_ice_thickness'],
        'chlorophyll': ['mass_concentration_of_chlorophyll_in_sea_water'],
    }
    
    targets = category_vars.get(category, [])
    
    # Check standard names first
    for var_name in ds.data_vars:
        std_name = ds[var_name].attrs.get('standard_name')
        if std_name in targets:
            return var_name
    
    # Check variable names
    for target in targets:
        if target in ds.data_vars:
            return target
    
    return None


def is_scientific_variable(var_name: str, ds: xr.Dataset) -> bool:
    """
    Check if a variable is a scientific variable (not a coordinate or flag).
    
    Args:
        var_name: Variable name
        ds: xarray Dataset
        
    Returns:
        True if it's a scientific variable
    """
    if var_name not in ds.data_vars:
        return False
    
    var = ds[var_name]
    
    # Skip coordinates
    if var_name in ds.coords:
        return False
    
    # Skip flag variables
    if 'flag' in var_name.lower():
        return False
    
    # Check if it has scientific attributes
    if var.attrs.get('standard_name') or var.attrs.get('long_name'):
        return True
    
    # Check if it has units (often indicates scientific data)
    if var.attrs.get('units'):
        return True
    
    # Check dimensionality (scientific vars typically have spatial dims)
    spatial_dims = {'lat', 'latitude', 'lon', 'longitude', 'x', 'y', 'depth', 'level'}
    for dim in var.dims:
        if dim.lower() in spatial_dims or dim.lower() in ds.dims:
            return True
    
    return False
