import urllib.request
import time
import struct
import json

base_url = "http://127.0.0.1:8000"

# Test 1: Atlantic ocean coordinates outside local bounds (0°..10°E, -10°..0°N)
print("=== TEST 1: Atlantic Ocean Coordinates Outside Local Bounds ===")
t0 = time.time()
url_atlantic = f"{base_url}/api/glorys/volume?date=2026-06-23&lonMin=0&lonMax=10&latMin=-10&latMax=0&depthMin=0&depthMax=500&lod=1&variable=thetao"
print(f"Requesting: {url_atlantic}")
req = urllib.request.urlopen(url_atlantic, timeout=15)
data = req.read()
elapsed = time.time() - t0

meta_len = struct.unpack(">I", data[:4])[0]
meta = json.loads(data[4:4+meta_len].decode("utf-8"))
raw_bytes_len = len(data[4+meta_len:])

print(f"Atlantic query succeeded in {elapsed:.2f}s!")
print(f"Status: HTTP {req.status}")
print(f"Mode: {meta.get('mode')}")
print(f"Variable: {meta.get('variable')}")
print(f"Dataset: {meta.get('dataset')}")
print(f"Shape: {meta.get('shape')}")
print(f"Voxel Bytes: {raw_bytes_len} bytes")
print(f"Value Range: {meta.get('value_min'):.2f} .. {meta.get('value_max'):.2f}")
assert elapsed < 7.0, f"Query took too long: {elapsed:.2f}s > 7.0s"
assert raw_bytes_len > 0, "No voxel bytes returned"

# Test 2: Local Indian Ocean coordinates (70°..75°E, 10°..15°N)
print("\n=== TEST 2: Local Indian Ocean Coordinates (Fast Path) ===")
t1 = time.time()
url_local = f"{base_url}/api/glorys/volume?date=2004-12-26&lonMin=70&lonMax=75&latMin=10&latMax=15&depthMin=0&depthMax=500&lod=1&variable=thetao"
print(f"Requesting: {url_local}")
req2 = urllib.request.urlopen(url_local, timeout=15)
data2 = req2.read()
elapsed2 = time.time() - t1

meta_len2 = struct.unpack(">I", data2[:4])[0]
meta2 = json.loads(data2[4:4+meta_len2].decode("utf-8"))
raw_bytes_len2 = len(data2[4+meta_len2:])

print(f"Local query succeeded in {elapsed2:.2f}s!")
print(f"Mode: {meta2.get('mode')}")
print(f"Shape: {meta2.get('shape')}")
print(f"Voxel Bytes: {raw_bytes_len2} bytes")

print("\nALL BACKEND VOLUME TESTS PASSED CLEANLY!")
