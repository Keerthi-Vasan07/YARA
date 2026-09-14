"""
test_server.py — YARA Copernicus backend smoke/integration test.

Run from the YARA project root:

    python test_server.py

For a running server:
    python test_server.py --base http://127.0.0.1:8000

This checks:
1. FastAPI app imports.
2. /api/online/datasets exposes exactly the 11 intended variables.
3. The registry points to the Copernicus dataset.
4. Each variable metadata route responds.
5. Optional live point/frame tests can be enabled.

No fake data is accepted.
"""

from __future__ import annotations

import argparse
import sys
import time

EXPECTED = [
    "thetao", "so", "uo", "vo", "zos",
    "mlotst", "bottomT", "siconc", "sithick", "usi", "vsi",
]
DATASET_ID = "cmems_mod_glo_phy_my_0.083deg_P1D-m"

def local_import_test():
    from server.main import app
    from server.data_sources.online_registry import ONLINE_DATASETS
    assert list(ONLINE_DATASETS) == EXPECTED, (
        f"Registry mismatch: {list(ONLINE_DATASETS)}"
    )
    print("[PASS] FastAPI import")
    print("[PASS] 11-variable registry")
    print(f"[INFO] Dataset: {DATASET_ID}")
    print("[INFO] Variables:", ", ".join(EXPECTED))
    return app

def http_test(base: str, live_points: bool = False):
    import requests

    s = requests.Session()
    base = base.rstrip("/")

    r = s.get(f"{base}/api/online/datasets", timeout=30)
    r.raise_for_status()
    data = r.json()

    keys = list(data.keys())
    assert keys == EXPECTED, f"/datasets mismatch: {keys}"
    for key in EXPECTED:
        assert data[key]["dataset_id"] == DATASET_ID
        assert data[key]["opendap_url"].endswith(DATASET_ID)
    print("[PASS] /api/online/datasets")

    for key in EXPECTED:
        r = s.get(f"{base}/api/online/{key}/metadata", timeout=120)
        if r.status_code != 200:
            print(f"[FAIL] {key}/metadata -> {r.status_code}: {r.text[:500]}")
            return 2
        payload = r.json()
        assert payload["dataset_id"] == DATASET_ID
        assert payload["variable_name"] == key
        print(f"[PASS] {key}/metadata")

    if live_points:
        # Small point query against the real remote dataset.
        key = "thetao"
        r = s.get(
            f"{base}/api/online/{key}/point",
            params={"date": "latest", "lon": -27.0, "lat": 16.1667},
            timeout=180,
        )
        if r.status_code != 200:
            print(f"[FAIL] live point -> {r.status_code}: {r.text[:1000]}")
            return 3
        p = r.json()
        print("[PASS] live thetao point query")
        print("[INFO] Point result:", p)

    print("[PASS] Server smoke test complete")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=None)
    ap.add_argument("--live", action="store_true",
                    help="also perform a real remote point query")
    args = ap.parse_args()

    try:
        local_import_test()
    except Exception as exc:
        print("[FAIL] local import/registry:", exc)
        return 1

    if args.base:
        try:
            return http_test(args.base, args.live)
        except Exception as exc:
            print("[FAIL] HTTP test:", exc)
            return 2

    print()
    print("To test a running server:")
    print("  python test_server.py --base http://127.0.0.1:8000")
    print("For a real remote point query:")
    print("  python test_server.py --base http://127.0.0.1:8000 --live")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
