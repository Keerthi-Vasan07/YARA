# GLORYS 3D Remote Ocean Visualization

Production-style remote 3D ocean temperature visualization system for Copernicus Marine GLORYS12V1 (`GLOBAL_MULTIYEAR_PHY_001_030` / `cmems_mod_glo_phy_my_0.083deg_P1D-m`, variable `thetao`).

The system performs remote lazy subsetting on the backend using the official Copernicus Marine Toolbox (`copernicusmarine`) and ARCO/Zarr, streams compact binary IEEE 754 Float32 data to the client, and renders a 100% data-driven GPU ray-marched 3D volume using Three.js `Data3DTexture` and GLSL3 shaders.

---

## 1. System Architecture

```text
Copernicus GLORYS (GLOBAL_MULTIYEAR_PHY_001_030)
      ↓
Remote ARCO/Zarr / Toolbox (copernicusmarine)
      ↓
FastAPI Backend (backend/glorys_service.py)
      ↓
xarray lazy spatial & temporal subsetting
      ↓
LOD / downsampling
      ↓
Compact Binary Packet ([4-byte uint32 header len] + [JSON metadata] + [Float32 raw bytes])
      ↓
Three.js Data3DTexture (FloatType, RedFormat)
      ↓
GLSL3 ray-marching shader (sampler3D)
      ↓
Interactive 3D Ocean Volume (Data-driven aspect ratio & depth profile picking)
```

- **Zero Global Archive Downloads**: The browser never downloads multi-gigabyte NetCDF files or the 40+ year GLORYS archive. The backend fetches and downsamples only the exact requested temporal and spatial slice.
- **Zero Credentials on Frontend**: Copernicus Marine credentials reside solely on the backend (`.env`), completely isolated from the browser client and network traffic.
- **100% Data-Driven Geometry**: Geometry aspect ratio, depth proportions, camera auto-framing, and coordinate picking are derived directly from the loaded dataset coordinates.

---

## 2. Copernicus Marine Account Requirement

Remote mode accesses Copernicus Marine datasets directly:
1. Register for a free account at [marine.copernicus.eu](https://marine.copernicus.eu/).
2. Your account credentials (`username` and `password`) are used by the backend service.

---

## 3. Environment Variables

Create a `.env` file in the project root based on `.env.example`:

```bash
# Copy example configuration
cp .env.example .env
```

Set your credentials in `.env`:

```env
# Copernicus Marine Credentials (Backend Only)
COPERNICUSMARINE_USERNAME=your_username_here
COPERNICUSMARINE_PASSWORD=your_password_here

# Data Mode: 'remote' (default) uses Copernicus Marine Toolbox / ARCO
# 'local' uses the local NetCDF fixture in data/ for offline development
GLORYS_DATA_MODE=remote
```

> **Security Guarantee**: `.env` is listed in `.gitignore` and is never exposed or committed.

---

## 4. Installation

### Prerequisites
- Python 3.10+ (with `pip`)
- Node.js 18+ (with `npm`)

### Backend Setup

```bash
cd glorys-3d-volume
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

pip install -r backend/requirements.txt
```

### Frontend Setup

```bash
cd glorys-3d-volume/frontend
npm install
```

---

## 5. Startup

### Start Backend

```bash
cd glorys-3d-volume
# Ensure virtual environment is active
uvicorn backend.main:app --reload --port 8000
```

Verify backend health:
```bash
curl http://localhost:8000/api/health
curl http://localhost:8000/api/glorys/health
```

### Start Frontend

```bash
cd glorys-3d-volume/frontend
npm run dev
```

Open the printed Vite development URL (typically `http://localhost:5174/` or `http://localhost:5173/`).

---

## 6. Remote GLORYS Configuration & Modes

The backend supports dual data modes controlled by `GLORYS_DATA_MODE`:
- `remote` (default): Queries remote Copernicus Marine ARCO/Zarr services using `copernicusmarine.open_dataset` and the remote product catalogue.
  - *Graceful fallback*: If credentials are not yet set or remote network access is unavailable, it automatically falls back to the local NetCDF fixture, ensuring immediate functionality for testing and development.
- `local`: Forces the backend to use the regional NetCDF fixture located in `data/cmems_mod_glo_phy_my_0.083deg_P1D-m_1788622407563.nc`.

---

## 7. API Endpoints

### `GET /api/health`
Basic liveness check.
```json
{ "status": "ok" }
```

### `GET /api/glorys/health`
Checks GLORYS service readiness, active mode (`remote` vs `local`), credential status, and cache size.
```json
{
  "status": "ok",
  "mode": "remote",
  "dataset_id": "cmems_mod_glo_phy_my_0.083deg_P1D-m",
  "product_id": "GLOBAL_MULTIYEAR_PHY_001_030",
  "variable": "thetao",
  "copernicus_credentials_configured": true,
  "local_fixture_available": true,
  "cache_entries": 2
}
```

### `GET /api/glorys/time-range`
Returns real dataset start and end dates from the product catalogue.
```json
{
  "dataset": "cmems_mod_glo_phy_my_0.083deg_P1D-m",
  "product": "GLOBAL_MULTIYEAR_PHY_001_030",
  "variable": "thetao",
  "start": "1993-01-01",
  "end": "2026-06-23",
  "resolution": "daily",
  "mode": "remote"
}
```

### `GET /api/glorys/metadata?date=YYYY-MM-DD`
Returns actual spatial coordinate ranges, depth levels, variable, and units for the given date.

### `GET /api/glorys/volume`
Extracts the requested GLORYS volume subset and returns a compact binary stream:
- **Parameters**:
  - `date`: Date string `YYYY-MM-DD` (e.g. `2026-06-23`).
  - `lonMin`, `lonMax`: Longitude bounds (e.g. `42.0` to `107.4`).
  - `latMin`, `latMax`: Latitude bounds (e.g. `-2.8` to `22.8`).
  - `depthMin`, `depthMax`: Depth bounds in meters (e.g. `0` to `1062`).
  - `lod`: Level of detail (`0` = Coarse, `1` = Balanced, `2` = High-Res).
  - `stride_lat`, `stride_lon`, `stride_depth`: Optional stride overrides.
- **Response**: `application/octet-stream` binary packet.

### `GET /api/glorys/profile?lat=...&lon=...&date=...`
Returns the real, unsmoothed vertical temperature-depth profile for the grid point nearest to `(lat, lon)`.

---

## 8. Compact Binary Response Protocol

Rather than sending millions of floating-point numbers in large JSON strings (which causes high memory usage and parsing overhead), the backend transmits a binary packet:

```
[ 4-byte uint32 (big-endian) metadata length L ]
[ L bytes UTF-8 JSON metadata ]
[ N bytes raw IEEE 754 Float32Array ]
```

### Client-Side Decoding (`frontend/src/api.ts`)
```typescript
const buffer = await response.arrayBuffer();
const view = new DataView(buffer);
const metaLen = view.getUint32(0, false); // big-endian
const metaBytes = new Uint8Array(buffer, 4, metaLen);
const meta: VolumeMeta = JSON.parse(new TextDecoder().decode(metaBytes));

// Byte-aligned slice for direct WebGL consumption
const float32 = new Float32Array(buffer.slice(4 + metaLen));
```

---

## 9. Date Selection, Region & Depth Subsetting

- **Date Picker**: Validated dynamically against the available product range (`timeRange.start` to `timeRange.end`).
- **Geographic Bounds**: Users can select custom longitude (`lonMin` / `lonMax`) and latitude (`latMin` / `latMax`) bounding boxes. Longitude wrapping is handled seamlessly.
- **Depth Bounds**: Users can restrict depth from surface (`0 m`) down to the maximum available depth in the dataset (`depthMax`).
- **LOD / Downsampling**:
  - `LOD 0 (Coarse)`: Fast query with higher stride, ideal for broad regional exploration.
  - `LOD 1 (Balanced)`: Standard balanced resolution (~1 million voxels).
  - `LOD 2 (High-Res)`: Fine sampling resolution.

---

## 10. Data-Driven 3D Geometry & Three.js Pipeline

1. **Volume Memory Layout**:
   Numpy array with shape `(depth, lat, lon)` in C-contiguous order maps directly to:
   ```typescript
   new THREE.Data3DTexture(float32, meta.shape.lon, meta.shape.lat, meta.shape.depth)
   ```
2. **Physical Aspect Ratio**:
   Extents in kilometers are derived dynamically:
   $$\text{meanLat} = \frac{\text{latMin} + \text{latMax}}{2}$$
   $$\text{widthKm} = (\text{lonMax} - \text{lonMin}) \times 111.32 \cos(\text{meanLat})$$
   $$\text{heightKm} = (\text{latMax} - \text{latMin}) \times 111.32$$
   $$\text{depthKm} = \frac{\text{depthMax} - \text{depthMin}}{1000}$$
   $$\text{scaleX} = 1.0, \quad \text{scaleZ} = \frac{\text{heightKm}}{\text{widthKm}}, \quad \text{scaleY} = \left(\frac{\text{depthKm}}{\text{widthKm}}\right) \times \text{verticalExaggeration}$$
3. **Camera Framing**:
   Auto-frames on dataset arrival using `THREE.Box3` and bounding sphere calculations, setting camera distance, near/far planes, and orbit distance limits.
4. **Interactive Profile Picking**:
   Clicking the volume calculates the world-to-local intersection, interpolates actual coordinate arrays, and queries `/api/glorys/profile` to render an unsmoothed depth profile chart.

---

## 11. Automated Tests

Run backend test suite:
```bash
python -m unittest backend/tests/test_remote_glorys.py
```

Run frontend type check & production build:
```bash
cd frontend
npx tsc --noEmit
npm run build
```

---

## 12. Troubleshooting

- **Copernicus Authentication Error**: Ensure `COPERNICUSMARINE_USERNAME` and `COPERNICUSMARINE_PASSWORD` in `.env` are valid. If not set, the backend operates in local fallback mode.
- **Slow Query on Large Region**: When requesting a large geographic region, select `Coarse (LOD 0)` or `Balanced (LOD 1)` to avoid fetching overly dense grids.
- **Port Conflicts**: Backend runs on `8000` (`uvicorn backend.main:app --port 8000`). Frontend runs on `5173` or `5174` with automatic `/api` proxying configured in `vite.config.ts`.
