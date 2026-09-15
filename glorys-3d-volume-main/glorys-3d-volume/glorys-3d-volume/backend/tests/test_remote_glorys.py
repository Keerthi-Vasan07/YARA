"""
Automated tests for remote GLORYS backend services and FastAPI endpoints.
"""

import json
import struct
import unittest
from fastapi.testclient import TestClient

from backend.main import app
from backend.glorys_service import get_service, normalize_longitude

client = TestClient(app)


class TestRemoteGlorysAPI(unittest.TestCase):

    def test_health_endpoints(self):
        res = client.get("/api/health")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json(), {"status": "ok"})

        res_g = client.get("/api/glorys/health")
        self.assertEqual(res_g.status_code, 200)
        data = res_g.json()
        self.assertIn("status", data)
        self.assertIn("mode", data)
        self.assertIn("dataset_id", data)
        self.assertEqual(data["variable"], "thetao")

    def test_time_range(self):
        res = client.get("/api/glorys/time-range")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["dataset"], "cmems_mod_glo_phy_my_0.083deg_P1D-m")
        self.assertEqual(data["variable"], "thetao")
        self.assertIn("start", data)
        self.assertIn("end", data)

    def test_metadata_for_date(self):
        res = client.get("/api/glorys/metadata?date=2026-06-23")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["date"], "2026-06-23")
        self.assertEqual(data["variable"], "thetao")
        self.assertIn("longitude", data)
        self.assertIn("latitude", data)
        self.assertIn("depth", data)
        self.assertGreater(data["depth"]["count"], 0)
        self.assertGreater(len(data["depth"]["values"]), 0)

    def test_metadata_invalid_date(self):
        res = client.get("/api/glorys/metadata?date=invalid-date")
        self.assertEqual(res.status_code, 400)

    def test_volume_binary_stream(self):
        # Query balanced volume subset
        res = client.get("/api/glorys/volume?date=2026-06-23&lonMin=42&lonMax=107&latMin=-2.8&latMax=22.8&depthMin=0&depthMax=1062&lod=1")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers["content-type"], "application/octet-stream")

        content = res.content
        self.assertGreater(len(content), 4)

        # Decode header length
        header_len = struct.unpack(">I", content[:4])[0]
        self.assertGreater(header_len, 0)
        self.assertLess(header_len, len(content))

        # Decode JSON metadata
        meta_json_str = content[4 : 4 + header_len].decode("utf-8")
        meta = json.loads(meta_json_str)

        self.assertEqual(meta["variable"], "thetao")
        self.assertIn("shape", meta)
        shape = meta["shape"]
        self.assertIn("depth", shape)
        self.assertIn("lat", shape)
        self.assertIn("lon", shape)

        # Raw float payload
        raw_float_bytes = content[4 + header_len :]
        expected_bytes = shape["depth"] * shape["lat"] * shape["lon"] * 4
        self.assertEqual(len(raw_float_bytes), expected_bytes)
        self.assertEqual(meta["byte_length"], expected_bytes)

    def test_volume_lod_variants(self):
        # Test coarse LOD (lod=0)
        res0 = client.get("/api/glorys/volume?date=2026-06-23&lonMin=42&lonMax=60&latMin=0&latMax=10&lod=0")
        self.assertEqual(res0.status_code, 200)

        # Test fine LOD (lod=2)
        res2 = client.get("/api/glorys/volume?date=2026-06-23&lonMin=42&lonMax=60&latMin=0&latMax=10&lod=2")
        self.assertEqual(res2.status_code, 200)

        # Fine LOD should have more bytes than Coarse LOD
        self.assertGreater(len(res2.content), len(res0.content))

    def test_profile_query(self):
        res = client.get("/api/glorys/profile?lat=10.0&lon=80.0&date=2026-06-23")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["date"], "2026-06-23")
        self.assertIn("matched_latitude", data)
        self.assertIn("matched_longitude", data)
        self.assertIn("depth", data)
        self.assertIn("temperature", data)
        self.assertEqual(len(data["depth"]), len(data["temperature"]))

    def test_longitude_normalization(self):
        self.assertAlmostEqual(normalize_longitude(0.0), 0.0)
        self.assertAlmostEqual(normalize_longitude(180.0), -180.0)
        self.assertAlmostEqual(normalize_longitude(-180.0), -180.0)
        self.assertAlmostEqual(normalize_longitude(200.0), -160.0)
        self.assertAlmostEqual(normalize_longitude(-200.0), 160.0)


if __name__ == "__main__":
    unittest.main()
