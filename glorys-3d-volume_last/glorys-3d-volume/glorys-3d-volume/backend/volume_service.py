"""
backend/volume_service.py

Re-exports from backend.services.volume_service.
"""

from backend.services.volume_service import (
    LOCAL_BOUNDS,
    is_within_local_dataset,
    generate_synthetic_ocean_volume,
    extract_local_volume,
    extract_remote_opendap_volume,
    extract_volume_safe,
)
