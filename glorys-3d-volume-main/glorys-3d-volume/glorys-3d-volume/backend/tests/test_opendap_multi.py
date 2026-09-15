import os
import sys
import json
import struct
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

for var in ['temperature', 'salinity', 'sound_speed', 'density', 'current_speed']:
    print(f"Testing variable: {var}...")
    res = client.get(
        f"/api/v1/subsurface/volume?variable={var}&lon_min=65&lon_max=70&lat_min=10&lat_max=14&depth_min=0&depth_max=200&downsample_stride=1"
    )
    if res.status_code != 200:
        print(f"FAIL {var}: {res.status_code} - {res.text}")
        continue
    raw = res.content
    meta_len = struct.unpack(">I", raw[:4])[0]
    meta = json.loads(raw[4 : 4 + meta_len].decode("utf-8"))
    data = np.frombuffer(raw[4 + meta_len :], dtype=np.float32)
    valid = data[~np.isnan(data)]
    print(
        f"OK {var}: shape={meta['shape']} voxels={len(data)} valid={len(valid)} "
        f"range=[{meta['value_min']:.2f}, {meta['value_max']:.2f}] unit={meta['units']}"
    )
