import xarray as xr
import h5py
import numpy as np
from pathlib import Path

src = Path("local_dataset/oisst-avhrr-v02r01.20250219.nc")
out = Path("local_dataset/oisst-avhrr-v02r01.20250219.h5")

print("Opening real NOAA OISST:")
print(src)

ds = xr.open_dataset(src)

print("\nVariables:", list(ds.data_vars))
print("Coordinates:", list(ds.coords))
print("Dimensions:", dict(ds.sizes))

# Detect names
lat_name = "lat" if "lat" in ds else "latitude"
lon_name = "lon" if "lon" in ds else "longitude"

# SST variable
sst_name = "sst"

lat = ds[lat_name].values
lon = ds[lon_name].values
sst = ds[sst_name].values

# Remove singleton dimensions such as time=1
sst = np.squeeze(sst)

# Time
if "time" in ds.coords:
    time = ds["time"].values.astype("datetime64[ns]").astype("int64")
else:
    time = np.array([0], dtype=np.int64)

print("\nCreating HDF5:", out)

with h5py.File(out, "w") as f:

    # Main datasets
    f.create_dataset("sst", data=sst, compression="gzip")
    f.create_dataset("lat", data=lat)
    f.create_dataset("lon", data=lon)
    f.create_dataset("time", data=time)

    # Metadata
    f["sst"].attrs["standard_name"] = "sea_surface_temperature"
    f["sst"].attrs["long_name"] = "Sea Surface Temperature"
    f["sst"].attrs["units"] = str(ds[sst_name].attrs.get("units", "unknown"))

    f["lat"].attrs["standard_name"] = "latitude"
    f["lat"].attrs["units"] = "degrees_north"

    f["lon"].attrs["standard_name"] = "longitude"
    f["lon"].attrs["units"] = "degrees_east"

    f.attrs["source"] = "NOAA OISST"
    f.attrs["dataset_type"] = "Ocean Sea Surface Temperature"
    f.attrs["format"] = "HDF5"

ds.close()

print("\nSUCCESS")
print("Created:", out)
print("SST shape:", sst.shape)
print("Latitude:", lat.shape)
print("Longitude:", lon.shape)
print("Time:", time.shape)