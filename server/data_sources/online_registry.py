"""Declarative registry for YARA's public online datasets.

Endpoints live only here, never in React. Adding a scalar dataset is a registry
entry plus a provider implementation; Cesium and the local pipeline stay put.
"""

from __future__ import annotations

from .providers.base import DatasetDefinition, VariableDefinition

DEFAULT_CAPABILITIES = {
    "scalar": True, "vector": False, "time": True, "depth": False,
    "profile": False, "point_query": True, "spatial_subset": True,
    "playback": True,
}

ONLINE_DATASETS: dict[str, DatasetDefinition] = {
    "noaa_oisst_v21_2025": DatasetDefinition(
        id="noaa_oisst_v21_2025", name="NOAA OISST v2.1 Sea Surface Temperature (2025)",
        provider="opendap", endpoint="https://psl.noaa.gov/thredds/dodsC/Datasets/noaa.oisst.v2.highres/sst.day.mean.2025.nc",
        source="NOAA Physical Sciences Laboratory", description="Daily 0.25° NOAA Optimum Interpolation SST analysis.",
        variables=(VariableDefinition("sst", "sst", "Sea Surface Temperature", "degC", category="temperature", colormap="thermal", vmin=-2, vmax=35),),
        temporal_resolution="P1D", spatial_resolution="0.25°", coverage={"west": 0, "east": 359.875, "south": -89.875, "north": 89.875}, capabilities=DEFAULT_CAPABILITIES,
    ),
    "noaa_smap_sss_nrt": DatasetDefinition(
        id="noaa_smap_sss_nrt", name="NOAA CoastWatch SMAP Sea Surface Salinity",
        provider="opendap", endpoint="https://coastwatch.noaa.gov/erddap/griddap/noaacwSMAPsssDaily",
        source="NOAA NESDIS CoastWatch / NASA JPL", description="Daily global Level-3 SMAP sea-surface salinity at 0.25°.",
        variables=(VariableDefinition("sss", "sss", "Sea Surface Salinity", "PSU", category="salinity", colormap="viridis", vmin=30, vmax=40),),
        temporal_resolution="P1D", spatial_resolution="0.25°", coverage={"west": -179.875, "east": 179.875, "south": -89.875, "north": 89.875}, capabilities=DEFAULT_CAPABILITIES,
    ),
    "noaa_modis_chlorophyll_nrt": DatasetDefinition(
        id="noaa_modis_chlorophyll_nrt", name="NASA MODIS Aqua Chlorophyll-a (NOAA ERDDAP)",
        provider="opendap", endpoint="https://coastwatch.pfeg.noaa.gov/erddap/griddap/erdMH1chla1day_R2022NRT",
        source="NASA GSFC OBPG / NOAA ERD ERDDAP", description="Daily global MODIS-Aqua Level-3 chlorophyll-a composite at 4 km.",
        variables=(VariableDefinition("chlorophyll", "chlorophyll", "Chlorophyll-a", "mg m-3", category="biogeochemistry", colormap="viridis", vmin=0.03, vmax=30, log_scale=True),),
        temporal_resolution="P1D", spatial_resolution="0.0416667°", coverage={"west": -179.9792, "east": 179.9792, "south": -89.97917, "north": 89.97916}, capabilities=DEFAULT_CAPABILITIES,
    ),
}


def get_dataset(dataset_id: str) -> DatasetDefinition:
    try:
        return ONLINE_DATASETS[dataset_id]
    except KeyError as exc:
        raise KeyError(f"Unknown online dataset '{dataset_id}'.") from exc


def get_variable(dataset_id: str, variable_id: str) -> VariableDefinition:
    dataset = get_dataset(dataset_id)
    for variable in dataset.variables:
        if variable.id == variable_id:
            return variable
    raise KeyError(f"Dataset '{dataset_id}' does not provide variable '{variable_id}'.")
