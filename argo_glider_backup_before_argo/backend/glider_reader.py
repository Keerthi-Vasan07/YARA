import ftplib
import os
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd
import truststore

truststore.inject_into_ssl()

import xarray as xr

from .config import (
    GLIDER_FTP_HOST,
    GLIDER_FTP_ROOT,
    GLIDER_MAX_FILES,
    GLIDER_MAX_POINTS_PER_FILE,
    GLIDER_MAX_TOTAL_POINTS,
    GLIDER_CACHE_SECONDS,
    GLIDER_FTP_TIMEOUT_SECONDS,
    GLIDER_REQUEST_TIMEOUT_SECONDS,
)


@dataclass
class GliderPoint:
    time: str | None
    latitude: float
    longitude: float
    depth: float | None = None
    temperature: float | None = None
    salinity: float | None = None
    pressure: float | None = None
    glider_id: str | None = None
    source: str = "IFREMER Glider FTP (dynamically discovered)"


@dataclass
class GliderTrajectory:
    glider_id: str
    points: list[GliderPoint] = field(default_factory=list)
    source: str = "IFREMER Glider FTP (dynamically discovered)"


_CACHE = {
    "timestamp": None,
    "trajectories": [],
    "statuses": [],
    "discovery": {},
}
_CACHE_LOCK = threading.Lock()


def _list_nc_files(ftp, root, deadline=None):
    """Recursively discover NetCDF files from the IFREMER Glider FTP."""
    files = []

    def walk(path):
        nonlocal files

        if len(files) >= GLIDER_MAX_FILES or (deadline and time.monotonic() >= deadline):
            return

        try:
            entries = list(ftp.mlsd(path))
        except Exception:
            if deadline and time.monotonic() >= deadline:
                return
            entries = []

            try:
                ftp.cwd(path)
                lines = []
                ftp.retrlines("LIST", lines.append)

                for line in lines:
                    parts = line.split(maxsplit=8)
                    if len(parts) < 9:
                        continue

                    name = parts[-1]
                    is_dir = line.startswith("d")
                    entries.append(
                        (name, {"type": "dir" if is_dir else "file"})
                    )

                ftp.cwd("/")
            except Exception:
                return

        for name, facts in entries:
            if len(files) >= GLIDER_MAX_FILES:
                return

            if deadline and time.monotonic() >= deadline:
                return

            if name in (".", ".."):
                continue

            full_path = path.rstrip("/") + "/" + name
            item_type = facts.get("type", "")

            if item_type == "dir":
                walk(full_path)

            elif item_type == "file":
                lower = name.lower()

                if lower.endswith((".nc", ".nc4", ".netcdf")):
                    files.append(full_path)

                    if len(files) >= GLIDER_MAX_FILES:
                        return

    walk(root)
    return files


def _pick_variable(ds, names):
    """Return the first matching variable name."""
    for name in names:
        if name in ds.variables:
            return name
    return None


def _parse_file(local_file, remote_path):
    """Read one NetCDF glider file and convert it into observation points."""

    ds = xr.open_dataset(
        local_file,
        decode_times=True,
        mask_and_scale=True,
    )

    try:
        lat_var = _pick_variable(
            ds, ["latitude", "lat", "LATITUDE"]
        )
        lon_var = _pick_variable(
            ds, ["longitude", "lon", "LONGITUDE"]
        )
        time_var = _pick_variable(
            ds, ["time", "TIME", "JULD", "datetime"]
        )
        depth_var = _pick_variable(
            ds, ["depth", "DEPTH", "depth_uv"]
        )
        temp_var = _pick_variable(
            ds,
            [
                "temperature",
                "TEMP",
                "TEMP_ADJUSTED",
                "sea_water_temperature",
            ],
        )
        sal_var = _pick_variable(
            ds,
            [
                "salinity",
                "PSAL",
                "PSAL_ADJUSTED",
                "sea_water_practical_salinity",
            ],
        )
        pressure_var = _pick_variable(
            ds,
            [
                "pressure",
                "PRES",
                "PRES_ADJUSTED",
                "sea_water_pressure",
            ],
        )

        if not lat_var or not lon_var:
            return []

        columns = [lat_var, lon_var]

        for var in [
            time_var,
            depth_var,
            temp_var,
            sal_var,
            pressure_var,
        ]:
            if var and var not in columns:
                columns.append(var)

        # Optimization: subset dataset to target variables only and slice dimension early
        ds_subset = ds[columns]
        dims = list(ds_subset.dims.keys())
        if dims:
            primary_dim = dims[0]
            if ds_subset.dims[primary_dim] > GLIDER_MAX_POINTS_PER_FILE:
                ds_subset = ds_subset.isel({primary_dim: slice(0, GLIDER_MAX_POINTS_PER_FILE)})

        df = ds_subset.to_dataframe().reset_index()

        # Remove duplicate columns that can appear after reset_index()
        df = df.loc[:, ~df.columns.duplicated()]

        if lat_var not in df.columns or lon_var not in df.columns:
            return []

        df = df.dropna(subset=[lat_var, lon_var])

        # Basic coordinate validation
        df = df[
            (df[lat_var] >= -90)
            & (df[lat_var] <= 90)
            & (df[lon_var] >= -180)
            & (df[lon_var] <= 180)
        ]

        if df.empty:
            return []

        # Keep response reasonably small
        df = df.head(GLIDER_MAX_POINTS_PER_FILE)

        # Use parent folder / filename as dynamically discovered identifier
        filename = os.path.basename(remote_path)
        parent = os.path.basename(
            os.path.dirname(remote_path.rstrip("/"))
        )

        glider_id = parent or filename

        points = []

        for _, row in df.iterrows():

            def value(var):
                if not var or var not in row.index:
                    return None

                v = row[var]

                if pd.isna(v):
                    return None

                try:
                    return float(v)
                except Exception:
                    return None

            timestamp = None

            if time_var and time_var in row.index:
                t = row[time_var]

                if not pd.isna(t):
                    try:
                        timestamp = pd.Timestamp(t).isoformat()
                    except Exception:
                        timestamp = str(t)

            points.append(
                GliderPoint(
                    time=timestamp,
                    latitude=float(row[lat_var]),
                    longitude=float(row[lon_var]),
                    depth=value(depth_var),
                    temperature=value(temp_var),
                    salinity=value(sal_var),
                    pressure=value(pressure_var),
                    glider_id=glider_id,
                )
            )

        return points

    finally:
        ds.close()


def get_glider_trajectories(force_refresh=False):
    now = datetime.now(timezone.utc)

    with _CACHE_LOCK:
        if (
            not force_refresh
            and _CACHE["timestamp"] is not None
            and (now - _CACHE["timestamp"]).total_seconds()
            < GLIDER_CACHE_SECONDS
        ):
            return (
                _CACHE["trajectories"],
                _CACHE["statuses"],
                _CACHE["discovery"],
            )

        return _load_glider_trajectories(now)


def _load_glider_trajectories(now):

    trajectories = []
    statuses = []

    try:
        ftp = ftplib.FTP(
            GLIDER_FTP_HOST,
            timeout=GLIDER_FTP_TIMEOUT_SECONDS,
        )

        ftp.login()
        ftp.voidcmd("TYPE I")

        deadline = time.monotonic() + GLIDER_REQUEST_TIMEOUT_SECONDS
        files = _list_nc_files(
            ftp,
            GLIDER_FTP_ROOT,
            deadline,
        )

        discovery = {
            "method": "IFREMER FTP recursive NetCDF discovery",
            "hardcoded_deployment_ids": False,
            "root": GLIDER_FTP_ROOT,
            "candidate_file_count": len(files),
            "selected_file_count": min(
                len(files),
                GLIDER_MAX_FILES,
            ),
        }

        total_points = 0

        for remote_path in files[:GLIDER_MAX_FILES]:

            if total_points >= GLIDER_MAX_TOTAL_POINTS:
                break

            try:
                with tempfile.NamedTemporaryFile(
                    suffix=".nc",
                    delete=False,
                ) as tmp:

                    local_file = tmp.name

                try:
                    with open(local_file, "wb") as output:

                        ftp.retrbinary(
                            f"RETR {remote_path}",
                            output.write,
                        )

                    points = _parse_file(
                        local_file,
                        remote_path,
                    )

                    remaining = (
                        GLIDER_MAX_TOTAL_POINTS
                        - total_points
                    )

                    points = points[:remaining]

                    if points:

                        glider_id = points[0].glider_id

                        trajectories.append(
                            GliderTrajectory(
                                glider_id=glider_id,
                                points=points,
                            )
                        )

                        total_points += len(points)

                        statuses.append(
                            {
                                "file": remote_path,
                                "status": "ok",
                                "points": len(points),
                            }
                        )

                    else:
                        statuses.append(
                            {
                                "file": remote_path,
                                "status": "no valid observations",
                                "points": 0,
                            }
                        )

                finally:
                    if os.path.exists(local_file):
                        os.remove(local_file)

            except Exception as exc:

                statuses.append(
                    {
                        "file": remote_path,
                        "status": "error",
                        "error": str(exc),
                    }
                )

        ftp.quit()

    except Exception as exc:

        discovery = {
            "method": "IFREMER FTP recursive NetCDF discovery",
            "hardcoded_deployment_ids": False,
            "root": GLIDER_FTP_ROOT,
            "candidate_file_count": 0,
            "selected_file_count": 0,
        }

        statuses = [
            {
                "status": "FTP connection error",
                "error": str(exc),
            }
        ]

    _CACHE["timestamp"] = now
    _CACHE["trajectories"] = trajectories
    _CACHE["statuses"] = statuses
    _CACHE["discovery"] = discovery

    return trajectories, statuses, discovery