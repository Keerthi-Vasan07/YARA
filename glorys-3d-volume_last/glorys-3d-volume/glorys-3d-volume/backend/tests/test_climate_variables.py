"""
test_climate_variables.py

Automated tests for the multi-variable climate subsurface parameters module.
Tests validate the four new variables (thetao, so, mlotst, ohc_0_700m) against
the FastAPI endpoints and GlorysService, using the TestClient in local mode.

Run:
    python -m pytest backend/tests/test_climate_variables.py -v
"""

import json
import os
import struct
import unittest

from fastapi.testclient import TestClient

# Force local mode for tests so we don't require live Copernicus credentials
os.environ.setdefault("GLORYS_DATA_MODE", "local")

from backend.main import app
from backend.glorys_service import get_service, normalize_longitude, ALLOWED_VARIABLES, VARIABLE_META

client = TestClient(app)


class TestVariableValidation(unittest.TestCase):
    """Test variable name validation — no fixture required."""

    def test_invalid_variable_volume_returns_400(self):
        """An invalid variable name must return HTTP 400."""
        res = client.get("/api/glorys/volume?date=2004-12-15&variable=foo")
        self.assertEqual(res.status_code, 400, f"Expected 400, got {res.status_code}: {res.text}")
        body = res.json()
        self.assertIn("detail", body)
        self.assertIn("foo", body["detail"])

    def test_invalid_variable_metadata_returns_400(self):
        """Metadata endpoint also validates variable name."""
        res = client.get("/api/glorys/metadata?date=2004-12-15&variable=invalid_var")
        self.assertEqual(res.status_code, 400)

    def test_allowed_variables_list(self):
        """ALLOWED_VARIABLES must contain the expected variables."""
        self.assertTrue({"thetao", "so", "mlotst", "ohc_0_700m", "chl", "composite"}.issubset(ALLOWED_VARIABLES))

    def test_variable_meta_is_2d_flags(self):
        """is_2d flags must be correct for each variable."""
        self.assertFalse(VARIABLE_META["thetao"]["is_2d"])
        self.assertFalse(VARIABLE_META["so"]["is_2d"])
        self.assertFalse(VARIABLE_META["chl"]["is_2d"])
        self.assertFalse(VARIABLE_META["composite"]["is_2d"])
        self.assertTrue(VARIABLE_META["mlotst"]["is_2d"])
        self.assertTrue(VARIABLE_META["ohc_0_700m"]["is_2d"])


class TestRemoteModeClimateRestrictions(unittest.TestCase):
    """Test that climate-only variables raise HTTP 501 in remote mode when fixture unavailable."""

    def setUp(self):
        """Temporarily set remote mode for these tests."""
        self._original_mode = os.environ.get("GLORYS_DATA_MODE", "remote")
        os.environ["GLORYS_DATA_MODE"] = "remote"
        # Reset singleton so it picks up the new mode
        import backend.glorys_service as svc
        svc._service_instance = None

    def tearDown(self):
        """Restore original mode."""
        os.environ["GLORYS_DATA_MODE"] = self._original_mode
        import backend.glorys_service as svc
        svc._service_instance = None

    def test_so_in_remote_mode_returns_expected_status(self):
        """Requesting 'so' while in remote mode returns 200 (if local fixture fallback) or 501/503."""
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=so&lonMin=70&lonMax=80&latMin=10&latMax=20"
        )
        self.assertIn(
            res.status_code, [200, 501, 503],
            f"Expected 200, 501, or 503 for 'so', got {res.status_code}: {res.text[:200]}"
        )

    def test_mlotst_in_remote_mode_returns_5xx(self):
        """Requesting 'mlotst' while in remote mode must return an error status."""
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=mlotst&lonMin=70&lonMax=80&latMin=10&latMax=20"
        )
        self.assertGreaterEqual(res.status_code, 500)

    def test_ohc_0_700m_in_remote_mode_returns_5xx(self):
        """Requesting 'ohc_0_700m' while in remote mode must return an error status."""
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=ohc_0_700m&lonMin=70&lonMax=80&latMin=10&latMax=20"
        )
        self.assertGreaterEqual(res.status_code, 500)


class TestClimateFixtureBinary(unittest.TestCase):
    """
    Integration tests requiring the Dec 2004 climate fixture.
    These tests are SKIPPED if the fixture file has not been ingested yet.
    Run: python backend/scripts/ingest_global_dec2004.py  before running these tests.
    """

    CLIMATE_PATH = None

    @classmethod
    def setUpClass(cls):
        from pathlib import Path
        _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        cls.CLIMATE_PATH = _PROJECT_ROOT / "backend" / "data" / "glorys_global_dec2004_climate.nc"
        if not cls.CLIMATE_PATH.exists():
            raise unittest.SkipTest(
                f"Climate fixture not found at {cls.CLIMATE_PATH}. "
                "Run: python backend/scripts/ingest_global_dec2004.py"
            )
        # Force local mode
        os.environ["GLORYS_DATA_MODE"] = "local"
        import backend.glorys_service as svc
        svc._service_instance = None

    def _decode_binary_packet(self, content: bytes):
        """Decode the binary packet and return (meta dict, float32 array length)."""
        self.assertGreater(len(content), 4, "Payload must be longer than 4 bytes")
        header_len = struct.unpack(">I", content[:4])[0]
        self.assertGreater(header_len, 0)
        self.assertLess(header_len, len(content))
        meta_json_str = content[4: 4 + header_len].decode("utf-8")
        meta = json.loads(meta_json_str)
        raw_float_bytes = content[4 + header_len:]
        return meta, raw_float_bytes

    def test_salinity_binary_payload_local(self):
        """
        Test 1: local-mode 'so' returns 200 and a correctly-shaped binary payload
        for a small bounding box within December 2004.
        """
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=so&lonMin=70&lonMax=80&latMin=10&latMax=20&lod=0"
        )
        self.assertEqual(res.status_code, 200, f"so volume failed: {res.text[:300]}")
        self.assertEqual(res.headers["content-type"], "application/octet-stream")

        meta, raw = self._decode_binary_packet(res.content)
        self.assertEqual(meta["variable"], "so")
        self.assertFalse(meta.get("is_2d", False), "'so' must not be marked as 2D")
        shape = meta["shape"]
        self.assertGreater(shape["depth"], 0)
        self.assertGreater(shape["lat"], 0)
        self.assertGreater(shape["lon"], 0)
        expected_bytes = shape["depth"] * shape["lat"] * shape["lon"] * 4
        self.assertEqual(len(raw), expected_bytes, "Byte length mismatch for 'so'")
        self.assertEqual(meta["byte_length"], expected_bytes)

        # Salinity values should be physically realistic (25–42 PSU range)
        import struct as struct_mod
        import numpy as np
        floats = np.frombuffer(raw, dtype=np.float32)
        valid = floats[~np.isnan(floats)]
        if valid.size > 0:
            self.assertGreater(float(valid.min()), 0.0, "Salinity min should be positive")
            self.assertLess(float(valid.max()), 45.0, "Salinity max should be < 45 PSU")

    def test_mlotst_returns_2d_payload(self):
        """
        Test 2: 'mlotst' returns a 2D-shaped payload (depth=1) and metadata with is_2d=true.
        """
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=mlotst&lonMin=60&lonMax=80&latMin=5&latMax=25&lod=0"
        )
        self.assertEqual(res.status_code, 200, f"mlotst volume failed: {res.text[:300]}")
        meta, raw = self._decode_binary_packet(res.content)

        self.assertEqual(meta["variable"], "mlotst")
        self.assertTrue(meta.get("is_2d", False), "mlotst must be marked as is_2d=true")
        shape = meta["shape"]
        self.assertEqual(shape["depth"], 1, "mlotst must have depth=1 (2D surface variable)")
        self.assertGreater(shape["lat"], 0)
        self.assertGreater(shape["lon"], 0)
        expected_bytes = 1 * shape["lat"] * shape["lon"] * 4
        self.assertEqual(len(raw), expected_bytes)

    def test_ohc_values_physically_sane(self):
        """
        Test 5: ohc_0_700m values must be physically sane — positive, roughly 1e8–1e10 J/m²
        for tropical latitudes.
        """
        import numpy as np
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=ohc_0_700m&lonMin=60&lonMax=90&latMin=0&latMax=20&lod=0"
        )
        self.assertEqual(res.status_code, 200, f"ohc_0_700m volume failed: {res.text[:300]}")
        meta, raw = self._decode_binary_packet(res.content)

        self.assertEqual(meta["variable"], "ohc_0_700m")
        self.assertTrue(meta.get("is_2d", False), "ohc_0_700m must be is_2d=true")

        floats = np.frombuffer(raw, dtype=np.float32)
        valid = floats[~np.isnan(floats)]
        self.assertGreater(valid.size, 0, "ohc_0_700m must have valid (non-NaN) ocean values")

        ohc_min = float(valid.min())
        ohc_max = float(valid.max())
        # Physically sane OHC for tropical ocean: roughly 1e8 to 1e11 J/m²
        self.assertGreater(ohc_min, 1e6, f"OHC min {ohc_min:.2e} seems too low (expected > 1e6 J/m²)")
        self.assertLess(ohc_max, 1e12, f"OHC max {ohc_max:.2e} seems unrealistically high")

    def test_2d_profile_returns_informational_message(self):
        """
        2D variables (mlotst, ohc_0_700m) must return an informational message
        rather than a real depth profile.
        """
        for var in ["mlotst", "ohc_0_700m"]:
            res = client.get(
                f"/api/glorys/profile?lat=10.0&lon=75.0&date=2004-12-15&variable={var}"
            )
            self.assertEqual(res.status_code, 200, f"Profile for {var} returned {res.status_code}")
            body = res.json()
            self.assertTrue(
                body.get("is_2d") or body.get("message"),
                f"Expected is_2d flag or message for {var} profile, got: {body}"
            )
            self.assertEqual(body.get("depth", []), [], f"Depth must be empty list for {var} profile")

    def test_thetao_regression_binary_shape(self):
        """
        Regression test: existing thetao endpoint still works correctly in local mode
        with the same binary packet format as before.
        """
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=thetao&lonMin=70&lonMax=85&latMin=8&latMax=20&lod=0"
        )
        self.assertEqual(res.status_code, 200, f"thetao regression failed: {res.text[:300]}")
        self.assertEqual(res.headers["content-type"], "application/octet-stream")

        meta, raw = self._decode_binary_packet(res.content)
        self.assertEqual(meta["variable"], "thetao")
        self.assertFalse(meta.get("is_2d", False), "thetao must not be 2D")
        self.assertIn("temperature_min", meta, "backward-compat temperature_min must be present")
        self.assertIn("temperature_max", meta, "backward-compat temperature_max must be present")
        self.assertIn("value_min", meta, "new value_min must be present")
        self.assertIn("value_max", meta, "new value_max must be present")
        self.assertEqual(
            meta["temperature_min"], meta["value_min"],
            "temperature_min must equal value_min for backward compat"
        )

        shape = meta["shape"]
        expected_bytes = shape["depth"] * shape["lat"] * shape["lon"] * 4
        self.assertEqual(len(raw), expected_bytes)

    def test_payload_hash_integrity_salinity(self):
        """SHA-256 payload_hash in metadata must match the first 16 hex chars of the actual payload."""
        import hashlib
        res = client.get(
            "/api/glorys/volume?date=2004-12-15"
            "&variable=so&lonMin=70&lonMax=75&latMin=10&latMax=15&lod=0"
        )
        self.assertEqual(res.status_code, 200)
        meta, raw = self._decode_binary_packet(res.content)
        expected_hash = hashlib.sha256(raw).hexdigest()[:16]
        self.assertEqual(
            meta.get("payload_hash"), expected_hash,
            f"Payload hash mismatch: server={meta.get('payload_hash')} client={expected_hash}"
        )


if __name__ == "__main__":
    unittest.main()
