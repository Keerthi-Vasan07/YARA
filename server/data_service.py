"""
SST Data Service - stub for backward compatibility.

ERA5 ARCO loading is now disabled. All data is served from 
pre-computed COG files in server/products/sst/. The time range
and tiles are served directly from the filesystem/database.
"""

from typing import Optional


class SSTDataService:
    """Stub service - ERA5 ARCO loading is disabled."""
    
    def __init__(self):
        self._initialized = False
        
    async def initialize(self):
        """No-op - ERA5 loading disabled."""
        self._initialized = True
        print("SST Data Service: ERA5 ARCO loading disabled. Using ECV COG products.")
        
    def get_time_range(self) -> dict:
        """Return empty - time range is now served from filesystem/database."""
        return {
            "total_months": 0,
            "start_date": None,
            "end_date": None,
            "available_dates": [],
            "years": {},
            "message": "Use /api/time-range endpoint instead"
        }
            
    async def shutdown(self):
        """Clean up resources (no-op)."""
        pass


# Singleton instance
sst_service = SSTDataService()
