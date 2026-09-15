from dataclasses import asdict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .argo_reader import get_float_trajectories
from .glider_reader import get_glider_trajectories
from .config import ALLOWED_ORIGINS

app = FastAPI(title="Real In-Situ Observation API", version="2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "datasets_configured": 2,
        "sources": ["INCOIS Argo API", "IFREMER Glider FTP (dynamically discovered)"],
    }


@app.get("/api/floats")
def floats():
    try:
        return [asdict(x) for x in get_float_trajectories()]
    except Exception as e:
        raise HTTPException(502, detail=f"INCOIS ERDDAP error: {e}")


@app.get("/api/stats")
def stats():
    try:
        t = get_float_trajectories()
        times = [p.time for x in t for p in x.points]
        return {
            "platform_count": len(t),
            "observation_count": sum(len(x.points) for x in t),
            "earliest_observation": min(times) if times else None,
            "latest_observation": max(times) if times else None,
            "source": "INCOIS ERDDAP - Indian_ARGO_Floats",
        }
    except Exception as e:
        raise HTTPException(502, detail=f"INCOIS ERDDAP error: {e}")


@app.get("/api/gliders")
def gliders(refresh: bool = False):
    try:
        data, sources, discovery = get_glider_trajectories(force_refresh=refresh)
        return {
            "platforms": [asdict(x) for x in data],
            "source_status": sources,
            "discovery": {
                "method": "IFREMER FTP recursive NetCDF discovery",
                "hardcoded_dataset_ids": False,
                "search": discovery,
            },
        }
    except Exception as e:
        raise HTTPException(502, detail=f"IFREMER Glider FTP discovery error: {e}")


@app.get("/api/sources")
def sources():
    try:
        _, glider_status, discovery = get_glider_trajectories()
        return {
            "argo": {
                "name": "INCOIS Argo",
                "type": "ERDDAP tabledap API",
                "dataset": "Indian_ARGO_Floats",
                "status": "available",
            },
            "glider": {
                "name": "IFREMER Glider",
                "type": "IFREMER FTP dynamic discovery",
                "status": "available" if any(x.get("status") == "ok" for x in glider_status) else "no_usable_dataset",
                "datasets_checked": len(glider_status),
                "dataset_status": glider_status,
                "discovery": discovery,
            },
        }
    except Exception as e:
        return {
            "argo": {"name": "INCOIS Argo", "status": "available"},
            "glider": {"name": "IFREMER Glider", "status": "error", "error": str(e)},
        }
