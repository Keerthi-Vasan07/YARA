# Online dataset providers

YARA keeps local files and remote datasets on separate paths. Local `.nc`,
`.h5`, `.hdf5`, and `.zarr` files continue through `server/data_sources/local`
and `/api/local-dataset`. Remote data is declared in
`server/data_sources/online_registry.py` and served through `/api/online`.

`DatasetProvider` is the boundary between a transport and the visualization
layer. It supplies inspection, exact time discovery, a spatial frame, point
query, and a query description. `OPeNDAPProvider` discovers coordinate names
from CF `standard_name`/axis attributes and common aliases, masks fill values,
normalizes longitude, transposes grids to `[latitude, longitude]`, and returns
`NormalizedGrid`. The generic API renderer converts that normalized grid to the
same transparent PNG imagery layer that the existing Cesium viewer uses.

## Adding a dataset

Add a `DatasetDefinition` to `ONLINE_DATASETS`. The only variable-specific
configuration is scientific metadata (source variable name, units, display
range, palette, and whether logarithmic display is needed). Do not change
Cesium, `OnlineControls`, or the local reader pipeline.

```python
"example": DatasetDefinition(
    id="example", name="Example daily oxygen", provider="opendap",
    endpoint="https://authoritative.example/thredds/dodsC/product.nc",
    source="Provider", description="...", temporal_resolution="P1D",
    spatial_resolution="0.1°",
    variables=(VariableDefinition(
        "oxygen", "o2", "Dissolved oxygen", "mmol m-3",
        category="biogeochemistry", vmin=0, vmax=400,
    ),),
)
```

Verify the endpoint's DDS/DAS first. The registry must use a real public
endpoint and source variable name. YARA does not synthesize fallback values.

## API and rendering flow

The UI discovers only backend metadata:

`/datasets` → dataset selector → `/datasets/{id}/metadata` and `/times` →
variable/date/time controls → `/data?dataset_id=…&variable=…&time=…` → PNG
with exact geographic bounds → existing Cesium imagery layer.

`/point` uses the same provider and exact selected timestamp. Frame caching
keys include provider, dataset, variable, timestamp, bounds, pixel limit, and
colour parameters, preventing cross-variable or cross-time reuse.

## Vectors and future providers

Variables can be declared as `vector_component` with `vector_group` and
`paired_component`. The current renderer explicitly accepts scalar fields;
future arrows/streamlines should consume paired normalized U/V grids without
changing the provider contract or Cesium setup. A new ERDDAP, COG, Argo, ADCP,
or Copernicus provider implements `DatasetProvider`; it need not modify core
rendering or local dataset code.
