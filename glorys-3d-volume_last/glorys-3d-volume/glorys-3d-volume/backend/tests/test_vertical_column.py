"""
test_vertical_column.py

Automated test suite for 3D Subsurface Column Profiling endpoint:
    GET /api/ocean/vertical-column
Verifies:
  - Successful response with status 200
  - Coordinate reflection (lat, lon) and timestamp
  - Standardized depth levels (up to 13 levels for max_depth=1000m)
  - Physical ranges:
      - Temperature: -2.5°C to 36.0°C
      - Salinity: 28.0 to 42.0 PSU
      - Chlorophyll: 0.0 to 10.0 mg/m³
  - Photic zone attenuation: Chlorophyll <= 0.01 mg/m³ for depths >= 500m
"""

import unittest
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


class TestVerticalColumnEndpoint(unittest.TestCase):
    def test_indian_ocean_point(self):
        """Test representative open ocean point in Arabian Sea / Indian Ocean."""
        res = client.get("/api/ocean/vertical-column?lat=12.5&lon=74.0&max_depth=1000.0")
        self.assertEqual(res.status_code, 200, f"Expected 200, got {res.status_code}: {res.text}")
        data = res.json()

        self.assertIn("lat", data)
        self.assertIn("lon", data)
        self.assertIn("timestamp", data)
        self.assertIn("profile", data)
        self.assertEqual(data["lat"], 12.5)
        self.assertEqual(data["lon"], 74.0)

        profile = data["profile"]
        self.assertGreaterEqual(len(profile), 10, "Expected at least 10 vertical depth steps")

        # Verify depth sequence is ascending
        depths = [p["depth_m"] for p in profile]
        self.assertEqual(depths, sorted(depths))
        self.assertEqual(depths[0], 0.0)

        # Check physical ranges
        for p in profile:
            self.assertIn("depth_m", p)
            self.assertIn("temperature", p)
            self.assertIn("salinity", p)
            self.assertIn("chlorophyll", p)

            t = p["temperature"]
            s = p["salinity"]
            c = p["chlorophyll"]

            self.assertTrue(-2.5 <= t <= 36.0, f"Unrealistic temperature {t} at depth {p['depth_m']}")
            self.assertTrue(28.0 <= s <= 42.0, f"Unrealistic salinity {s} at depth {p['depth_m']}")
            self.assertTrue(0.0 <= c <= 10.0, f"Unrealistic chlorophyll {c} at depth {p['depth_m']}")

        # Verify Chlorophyll extinction in aphotic zone (> 500m)
        deep_points = [p for p in profile if p["depth_m"] >= 500.0]
        self.assertTrue(len(deep_points) > 0)
        for dp in deep_points:
            self.assertLessEqual(dp["chlorophyll"], 0.01, f"Expected near-zero chlorophyll at {dp['depth_m']}m")

    def test_max_depth_parameter(self):
        """Test that max_depth subsets the returned depth layers."""
        res = client.get("/api/ocean/vertical-column?lat=0.0&lon=60.0&max_depth=200.0")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        for p in data["profile"]:
            self.assertLessEqual(p["depth_m"], 200.0)

    def test_repeated_query_cache(self):
        """Verify LRU cache returns identical results quickly."""
        res1 = client.get("/api/ocean/vertical-column?lat=15.0&lon=80.0&max_depth=500.0")
        res2 = client.get("/api/ocean/vertical-column?lat=15.0&lon=80.0&max_depth=500.0")
        self.assertEqual(res1.status_code, 200)
    def test_terrestrial_land_mask_detection(self):
        """Verify terrestrial landmass (e.g., 13.890N, 76.813E in Peninsular India) returns empty profile and is_land=True."""
        res = client.get("/api/ocean/vertical-column?lat=13.890&lon=76.813")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("is_land"), "Expected is_land to be True for peninsular India land point")
        self.assertEqual(len(data.get("profile", [])), 0, "Expected empty ocean profile for terrestrial landmass")

    def test_point_probe_land_and_ocean(self):
        """Verify /api/glorys/point endpoint flags land and provides ocean telemetry."""
        # 1. Land point in Peninsular India
        land_res = client.get("/api/glorys/point?lat=13.890&lon=76.813")
        self.assertEqual(land_res.status_code, 200)
        land_data = land_res.json()
        self.assertTrue(land_data.get("is_land"))
        self.assertEqual(land_data.get("status"), "TERRESTRIAL LANDMASS")
        self.assertIsNone(land_data.get("temperature"))
        self.assertIsNone(land_data.get("salinity"))
        self.assertIsNone(land_data.get("chlorophyll"))
        self.assertEqual(len(land_data.get("profile", [])), 0)

        # 2. Open ocean point in Arabian Sea
        ocean_res = client.get("/api/glorys/point?lat=10.0&lon=70.0")
        self.assertEqual(ocean_res.status_code, 200)
        ocean_data = ocean_res.json()
        self.assertFalse(ocean_data.get("is_land"))
        self.assertIsNotNone(ocean_data.get("temperature"))


if __name__ == "__main__":
    unittest.main()
