import xarray as xr
from pathlib import Path

src = Path("local_dataset/oisst-avhrr-v02r01.20250219.nc")
out = Path("local_dataset/oisst-avhrr-v02r01.20250219.zarr")

print("Opening:", src)

ds = xr.open_dataset(src)

print("\nVariables:")
print(list(ds.data_vars))

print("\nCoordinates:")
print(list(ds.coords))

print("\nDimensions:")
print(ds.dims)

if out.exists():
    import shutil
    shutil.rmtree(out)

print("\nCreating Zarr...")
ds.to_zarr(out, mode="w")

ds.close()

print("\nDONE")
print("Zarr:", out)
