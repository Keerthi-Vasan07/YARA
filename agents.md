You are the lead software architect and implementation agent for the YARA
oceanographic visualization platform.

IMPORTANT:
Do NOT blindly rewrite the existing application.
First inspect the complete repository and understand the existing architecture,
especially the current LOCAL dataset pipeline and ONLINE/OPeNDAP pipeline.

GOAL
====

Extend YARA's ONLINE MODE into an extensible, dataset-driven OPeNDAP system.

The system must support real oceanographic surface variables such as:

1. Sea Surface Temperature (SST)
2. Sea Surface Salinity (SSS)
3. Chlorophyll-a
4. Surface Eastward Current / U Current
5. Surface Northward Current / V Current
6. Wind U
7. Wind V

The architecture must allow future addition of:

- CTD
- ADCP
- Moorings
- HF Radar
- Argo
- Ocean model variables
- Satellite products
- Machine-learning derived ocean products

Do NOT create separate hardcoded visualization logic for each variable.

The visualization engine must remain generic.


==================================================
PHASE 1 — AUDIT THE EXISTING YARA CODEBASE
==================================================

Before changing code:

Inspect:

- server/
- server/api/
- server/pipeline/
- server/data_sources/
- existing OPeNDAP implementation
- tiles.py
- opendap_sst.py
- point.py
- subset.py
- time_range.py
- zarr.py
- frontend src/
- Layout.tsx
- CesiumViewer.tsx
- existing variable selectors
- existing online/local mode switching
- playback implementation
- existing point-query implementation
- existing color scale implementation

Determine:

1. How ONLINE mode is currently activated.
2. How OPeNDAP URLs are currently represented.
3. How variables are currently detected.
4. How dates/times are currently handled.
5. How data reaches Cesium.
6. Whether the current implementation is SST-specific.
7. Which parts can be generalized.
8. Which parts must remain untouched for LOCAL datasets.

Do not modify anything until this audit is complete.


==================================================
PHASE 2 — CREATE A GENERIC ONLINE DATA MODEL
==================================================

Create a provider/dataset architecture.

Do NOT use logic such as:

if variable == "sst":
    ...
elif variable == "sss":
    ...
elif variable == "chlorophyll":
    ...

Instead create a generic DatasetProvider interface.

Conceptually:

DatasetProvider
    ├── get_datasets()
    ├── inspect_dataset()
    ├── get_variables()
    ├── get_time_range()
    ├── get_dimensions()
    ├── get_data()
    ├── get_point_value()
    └── build_query()

Create an OPeNDAP provider implementation:

OPeNDAPProvider

Future providers should be possible:

NetCDFProvider
ZarrProvider
COGProvider
ERDDAPProvider
THREDDSProvider
CopernicusProvider
ArgoProvider
ADCPProvider
etc.

The visualization engine must not care where the data came from.


==================================================
PHASE 3 — CREATE A DATASET REGISTRY
==================================================

Create a registry/configuration system for online datasets.

Example conceptual structure:

datasets/
    sst/
    sss/
    chlorophyll/
    currents/
    wind/

Or preferably a registry containing metadata.

Each dataset definition should contain fields similar to:

{
    "id": "...",
    "name": "...",
    "provider": "opendap",
    "description": "...",
    "source": "...",
    "variables": [...],
    "time_dimension": "...",
    "latitude_dimension": "...",
    "longitude_dimension": "...",
    "units": "...",
    "category": "surface",
    "temporal_resolution": "...",
    "spatial_resolution": "...",
    "coverage": {
        "north": ...,
        "south": ...,
        "east": ...,
        "west": ...
    }
}

Do NOT assume all datasets have:

lat
lon
time

with those exact names.

Dataset inspection must detect the actual coordinate names.

For example:

latitude
lat
nav_lat

longitude
lon
nav_lon

time
TIME
datetime

must be handled where practical.


==================================================
PHASE 4 — REAL DATASET DISCOVERY
==================================================

Find REAL publicly accessible OPeNDAP/THREDDS datasets.

Prioritize authoritative sources:

- NOAA
- NASA
- PO.DAAC
- Copernicus Marine
- NCEI
- HYCOM
- CoastWatch
- other established scientific data providers

Do not invent URLs.

For every candidate dataset:

1. Verify that the endpoint actually exists.
2. Verify that it exposes OPeNDAP.
3. Inspect the DDS/DAS/metadata.
4. Determine available variables.
5. Determine dimensions.
6. Determine time coverage.
7. Determine temporal resolution.
8. Determine spatial coverage.
9. Determine units.
10. Determine whether the requested variable can be queried for a specific time.

Do not assume that a dataset is hourly just because it has a time dimension.

Record the actual temporal resolution.


==================================================
PHASE 5 — SUPPORT MULTIPLE ONLINE VARIABLES
==================================================

The frontend should allow:

ONLINE MODE

Dataset:
    [ Select dataset ]

Variable:
    [ SST ▼ ]

Date:
    [ 2025-02-19 ]

Time:
    [ 12:00 UTC ]

Then:

LOAD DATA

The variable list must come dynamically from the selected dataset.

For example:

Dataset:
GOES-19 SST

Variable:
SST

Date:
2025-02-19

Time:
12:00 UTC


Another dataset:

Dataset:
Ocean Salinity Dataset

Variable:
SSS

Date:
2025-02-19

Time:
12:00 UTC


Another:

Dataset:
Ocean Color

Variable:
Chlorophyll-a

Date:
2025-02-19

Time:
12:00 UTC


Do NOT hardcode these UI values.

The UI should consume dataset metadata from the backend.


==================================================
PHASE 6 — GENERIC OPeNDAP QUERY ENGINE
==================================================

Create a generic OPeNDAP query builder.

The backend must be able to construct requests based on:

dataset
variable
time
latitude bounds
longitude bounds

For example conceptually:

dataset + variable + time slice + spatial subset

The query builder must understand the dataset's actual dimensions.

Do NOT assume dimension ordering is always:

[time][lat][lon]

Some datasets may use:

[time][latitude][longitude]

or:

[latitude][longitude][time]

or other valid arrangements.

Inspect metadata and construct the query accordingly.


==================================================
PHASE 7 — TIME HANDLING
==================================================

Implement generic time discovery.

When a dataset is selected:

GET:

- available start time
- available end time
- temporal resolution
- available timestamps

The frontend should then show a date/time selector based on REAL dataset time.

Do NOT use fake dates.

Do NOT hardcode:

2025-02-19

unless that date actually exists in the selected dataset.

If the dataset is hourly:

show hourly times.

If daily:

show daily times.

If 3-hourly:

show 3-hour intervals.

The playback system must eventually be able to use the dataset's actual temporal axis.


==================================================
PHASE 8 — GENERIC NORMALIZATION PIPELINE
==================================================

Create a generic normalization layer:

Raw OPeNDAP data
        ↓
Dataset adapter
        ↓
Coordinate normalization
        ↓
Variable normalization
        ↓
Missing-value masking
        ↓
Units
        ↓
Spatial representation
        ↓
Rendering engine

The normalized internal representation should contain:

variable
units
values
latitude
longitude
time
min
max
missing_value
metadata

The renderer should consume this representation.

This is critical because SST, SSS, chlorophyll and currents have different units
and ranges but should use the same rendering infrastructure.


==================================================
PHASE 9 — VARIABLE METADATA
==================================================

Create a variable metadata model.

Example:

SST:

{
    "id": "sst",
    "name": "Sea Surface Temperature",
    "units": "°C",
    "type": "scalar",
    "category": "temperature"
}

SSS:

{
    "id": "sss",
    "name": "Sea Surface Salinity",
    "units": "PSU",
    "type": "scalar",
    "category": "salinity"
}

Chlorophyll:

{
    "id": "chlorophyll",
    "name": "Chlorophyll-a",
    "units": "mg m-3",
    "type": "scalar",
    "category": "biogeochemistry"
}

Current U:

{
    "id": "current_u",
    "name": "Eastward Ocean Current",
    "units": "m s-1",
    "type": "vector_component",
    "vector_group": "current"
}

Current V:

{
    "id": "current_v",
    "name": "Northward Ocean Current",
    "units": "m s-1",
    "type": "vector_component",
    "vector_group": "current"
}

Wind U/V should similarly be represented as vector components.


==================================================
PHASE 10 — SCALAR VS VECTOR VARIABLES
==================================================

The architecture MUST distinguish:

SCALAR:

SST
SSS
chlorophyll
pressure
oxygen
etc.

VECTOR:

current_u + current_v
wind_u + wind_v

Do not treat U and V as unrelated variables forever.

Create a future-compatible vector model:

VectorField:

{
    "u": "...",
    "v": "...",
    "magnitude": "...",
    "direction": "..."
}

Initially implement loading/rendering of scalar fields.

Prepare the architecture for vector visualization later:

- arrows
- streamlines
- particles
- direction
- magnitude

Do not break existing scalar rendering.


==================================================
PHASE 11 — GLOBE RENDERING
==================================================

When the user selects:

ONLINE
→ Dataset
→ Variable
→ Date
→ Time
→ Load

the real OPeNDAP data must appear on the existing Cesium globe.

Do not create a second globe.

Reuse the existing CesiumViewer rendering infrastructure wherever possible.

The renderer must work generically with:

SST
SSS
chlorophyll
and future scalar variables.

Color scale should adapt to the variable metadata/data range.


==================================================
PHASE 12 — ONLINE / LOCAL MODE ISOLATION
==================================================

IMPORTANT.

LOCAL DATASET functionality must continue working.

LOCAL:

.nc
.h5
.hdf5
.zarr

must continue using the existing local pipeline.

ONLINE:

OPeNDAP

must use the new provider architecture.

Do not merge the two pipelines into one giant implementation.

Instead:

DataSource
   ├── LocalDataProvider
   └── OnlineDataProvider
          └── OPeNDAPProvider

Both should eventually return the same normalized internal data model.

This is the key extensibility boundary.


==================================================
PHASE 13 — API DESIGN
==================================================

Create generic APIs such as:

GET /api/online/datasets

GET /api/online/datasets/{dataset_id}

GET /api/online/datasets/{dataset_id}/variables

GET /api/online/datasets/{dataset_id}/times

GET /api/online/datasets/{dataset_id}/metadata

GET /api/online/data

GET /api/online/point

The exact endpoint naming can follow the existing YARA conventions.

Example:

GET /api/online/data?
dataset_id=...
&variable=sst
&time=...
&lat_min=...
&lat_max=...
&lon_min=...
&lon_max=...

Do not expose raw provider-specific implementation details to the frontend.


==================================================
PHASE 14 — ERROR HANDLING
==================================================

Handle:

- OPeNDAP unavailable
- invalid dataset
- invalid variable
- unavailable timestamp
- timeout
- malformed DDS
- missing coordinate
- unsupported dimension structure
- missing values
- network failure
- unsupported variable type

Return useful messages to the UI.

Never silently fall back to fake/synthetic data.

If a dataset cannot be loaded, tell the user why.


==================================================
PHASE 15 — NO SYNTHETIC DATA
==================================================

This is extremely important.

Do NOT create:

random SST
fake chlorophyll
fake salinity
fake currents
fake timestamps

for production visualization.

If real data cannot be obtained:

show an explicit error.

Testing fixtures may be synthetic, but they must never be presented as real
scientific data.


==================================================
PHASE 16 — CACHING
==================================================

Use caching where appropriate.

Cache key should include:

provider
dataset_id
variable
time
spatial bounds
query parameters

Do not allow:

SST at 12:00

to accidentally return:

SST at 13:00

or:

SSS at 12:00.

Cache must be variable/time/dataset aware.


==================================================
PHASE 17 — FRONTEND ARCHITECTURE
==================================================

Create reusable components rather than adding everything to Layout.tsx.

Prefer:

OnlineDatasetSelector
OnlineVariableSelector
OnlineTimeSelector
OnlineDatasetInfo
OnlineDataControls

and a reusable hook/service:

useOnlineDataset()
useOnlineVariable()
useOnlineTime()

or equivalent architecture matching the existing project.

Layout should orchestrate state rather than contain the entire online-data system.


==================================================
PHASE 18 — FUTURE PLUGIN ARCHITECTURE
==================================================

The architecture must allow future providers to be added without modifying:

CesiumViewer
ColorScaleControls
point panels
core rendering logic

For example:

providers/
    base.py
    opendap.py
    copernicus.py
    erddap.py
    argo.py
    adcp.py

A provider should implement the common interface.

Future:

class ADCPProvider(DataProvider):
    ...

should be able to provide:

velocity
depth
time
latitude
longitude
quality
temperature
heading
pitch
roll

without changing the core visualization engine.

Similarly:

class ArgoProvider(DataProvider):
    ...

can provide:

temperature profile
salinity profile
pressure
latitude
longitude
time

The system should be capable of representing these datasets even if their
visualizations are implemented later.


==================================================
PHASE 19 — DATA CAPABILITY MODEL
==================================================

Introduce a capability model.

Example:

{
    "dataset_id": "...",
    "capabilities": {
        "scalar": true,
        "vector": false,
        "time": true,
        "depth": false,
        "profile": false,
        "point_query": true,
        "spatial_subset": true,
        "playback": true
    }
}

This allows the frontend to know what controls are available.

For example:

ADCP:

depth = true
vector = true
profile = true

SST:

depth = false
vector = false
profile = false
scalar = true


==================================================
PHASE 20 — TESTING
==================================================

Build tests for:

1. Dataset discovery
2. OPeNDAP metadata parsing
3. Variable discovery
4. Time discovery
5. Dimension detection
6. Coordinate normalization
7. Missing-value handling
8. SST loading
9. SSS loading
10. Chlorophyll loading
11. Specific timestamp loading
12. Cache isolation
13. Invalid variable
14. Invalid timestamp
15. Network failure
16. Online/local switching

Use real public datasets for integration tests where practical.

Do not make tests dependent on a single fragile live endpoint if avoidable.
Separate:

unit tests
integration tests
live-data tests


==================================================
PHASE 21 — DOCUMENTATION
==================================================

Create documentation explaining:

1. How the online provider architecture works.
2. How to add a new OPeNDAP dataset.
3. How to add a new variable.
4. How to add a new provider.
5. How metadata is discovered.
6. How time selection works.
7. How data reaches Cesium.
8. How to add vector variables.
9. How to add ADCP/CTD/Argo in the future.

Include an example showing how a developer can add a new dataset WITHOUT
changing the rendering engine.


==================================================
CRITICAL RULES
==================================================

1. Inspect before modifying.
2. Preserve existing functionality.
3. Do not break LOCAL datasets.
4. Do not break existing SST OPeNDAP functionality.
5. Do not hardcode dataset URLs into React components.
6. Do not hardcode timestamps.
7. Do not create fake scientific data.
8. Do not duplicate visualization logic per variable.
9. Do not assume all datasets have identical dimensions.
10. Do not assume all datasets are hourly.
11. Do not assume lat/lon coordinate names.
12. Do not assume variable names.
13. Use real metadata to determine capabilities.
14. Keep provider-specific logic inside providers.
15. Keep rendering provider-agnostic.
16. Make the architecture plugin-style.
17. Keep LOCAL and ONLINE pipelines isolated.
18. Reuse existing YARA components where appropriate.
19. Do not rewrite working functionality unnecessarily.
20. Run tests after every major phase.


==================================================
FINAL ACCEPTANCE CRITERIA
==================================================

The implementation is considered successful only when:

A user can open YARA and select:

ONLINE MODE

then:

Dataset
→ SST dataset
→ SST
→ real available date
→ real available time
→ LOAD

and see real SST data on the globe.

Then they can switch to:

SSS

select a valid date/time

and see real SSS data.

Then:

Chlorophyll

select a valid date/time

and see real chlorophyll data.

The same rendering engine must handle all three.

The frontend must obtain dataset/variable/time metadata from the backend rather
than hardcoding them.

The OPeNDAP URL must remain backend/provider configuration.

The system must clearly show:

Dataset
Variable
Units
Date
Time
Data source
Spatial coverage
Temporal coverage

The architecture must make adding a fourth dataset possible by adding a
provider/registry definition rather than rewriting the globe renderer.

Before finishing:

- run backend tests
- run frontend tests
- run TypeScript/build
- verify existing LOCAL dataset
- verify existing ONLINE SST
- verify new SSS
- verify new chlorophyll
- verify online/local switching
- inspect browser console
- inspect backend logs

At the end provide:

1. Files changed
2. Architecture created
3. Real datasets discovered
4. OPeNDAP endpoints verified
5. Variables verified
6. Time ranges verified
7. Tests executed
8. Build result
9. Any remaining issues

Do not claim completion unless the functionality has actually been tested.