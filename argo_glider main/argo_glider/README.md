# Argo API + Dynamic Glider API + 2D Leaflet Map

This version keeps the working **INCOIS Argo API** and adds a **dynamic Glider adapter**.

## Data sources

- **Argo:** INCOIS ERDDAP `Indian_ARGO_Floats`.
- **Glider:** IFREMER Glider FTP (`ftp://ftp.ifremer.fr/ifremer/glider/v2/`). The backend recursively discovers NetCDF files on the IFREMER Glider FTP repository, inspects file metadata, chooses compatible latitude/longitude/time/scientific variables, and then fetches real observations.

No individual Glider deployment ID is hardcoded.

## Project structure

```text
argo_glider/
├── backend/
│   ├── __init__.py
│   ├── main.py
│   ├── argo_reader.py
│   ├── glider_reader.py
│   ├── config.py
│   └── requirements.txt
├── frontend/
│   └── index.html
└── README.md
```

## Run

### Terminal 1 - FastAPI

```powershell
cd D:\SIH_26\argo_glider
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload --port 8000
```

Keep this terminal open.

### Terminal 2 - frontend

```powershell
cd D:\SIH_26\argo_glider
python -m http.server 5500 --directory frontend
```

Then open:

```text
http://127.0.0.1:5500
```

## API endpoints

- `/api/health`
- `/api/floats` - real INCOIS Argo trajectories
- `/api/stats` - Argo statistics
- `/api/gliders` - dynamic Glider discovery + real observations
- `/api/gliders?refresh=true` - force a fresh Glider FTP discovery
- `/api/sources` - source status and discovered Glider datasets

## Important behavior

Glider discovery is intentionally dynamic. The backend does not assume that a particular deployment ID will always exist. It:

1. Recursively discovers NetCDF files on IFREMER Glider FTP (`/ifremer/glider/v2/`).
2. Downloads selected candidate NetCDF files.
3. Reads each candidate dataset's NetCDF metadata.
4. Finds compatible coordinate/time/scientific variables.
5. Fetches near-surface observations for the 2D trajectory map.
6. Skips datasets that fail instead of breaking the whole Argo API.
7. Caches successful Glider discovery/data for 15 minutes.

The frontend also handles Glider failure gracefully: **Argo can still load if the Glider source is temporarily unavailable.**


### Glider discovery
The Glider adapter does not contain a fixed deployment ID. It queries the IFREMER Glider FTP repository, inspects discovered dataset metadata, and requests compatible observations. If discovery or a dataset fails, the failure is reported in `/api/gliders` while Argo remains usable.
