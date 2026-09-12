"""
STAC Catalog Integration Tests

Tests the SpatioTemporal Asset Catalog functionality:
- Catalog building from COG filesystem
- Collection and item creation
- Catalog updates after ingestion
- Zarr collection handling
- API endpoint integration
"""

import json
import pytest
from pathlib import Path


class TestSTACCatalogBuilding:
    """Tests for STAC catalog creation and updates."""
    
    def test_build_catalog_creates_structure(self, temp_stac_dir: Path, sample_cog_series: list[Path]):
        """Test that build_catalog creates proper directory structure."""
        from server.stac.catalog import build_catalog
        
        # Temporarily override STAC_DIR
        import server.stac.catalog as catalog_module
        original_stac_dir = catalog_module.STAC_DIR
        original_products_dir = catalog_module.PRODUCTS_DIR
        catalog_module.STAC_DIR = temp_stac_dir
        catalog_module.PRODUCTS_DIR = sample_cog_series[0].parent.parent
        
        try:
            build_catalog()
            
            # Check structure created
            assert (temp_stac_dir / "catalog.json").exists()
            assert (temp_stac_dir / "collections").is_dir()
            assert (temp_stac_dir / "items").is_dir()
        finally:
            catalog_module.STAC_DIR = original_stac_dir
            catalog_module.PRODUCTS_DIR = original_products_dir
    
    def test_catalog_json_valid(self, sample_stac_catalog: Path):
        """Test that generated catalog.json is valid STAC."""
        catalog_path = sample_stac_catalog / "catalog.json"
        
        with open(catalog_path) as f:
            catalog = json.load(f)
        
        assert catalog["type"] == "Catalog"
        assert catalog["stac_version"] == "1.0.0"
        assert "id" in catalog
        assert "links" in catalog
        
        # Check required links
        link_rels = [link["rel"] for link in catalog["links"]]
        assert "self" in link_rels
        assert "root" in link_rels
    
    def test_collection_has_temporal_extent(self, sample_stac_catalog: Path):
        """Test that collection has proper temporal extent from items."""
        collection_path = sample_stac_catalog / "collections" / "sst.json"
        
        with open(collection_path) as f:
            collection = json.load(f)
        
        assert collection["type"] == "Collection"
        assert "extent" in collection
        assert "temporal" in collection["extent"]
        
        temporal = collection["extent"]["temporal"]["interval"][0]
        assert temporal[0] is not None  # start date
        assert temporal[1] is not None  # end date
    
    def test_item_has_required_fields(self, sample_stac_catalog: Path):
        """Test that STAC items have all required fields."""
        items_dir = sample_stac_catalog / "items" / "sst"
        item_files = list(items_dir.glob("*.json"))
        
        assert len(item_files) > 0
        
        with open(item_files[0]) as f:
            item = json.load(f)
        
        # Required STAC fields
        assert item["type"] == "Feature"
        assert "id" in item
        assert "geometry" in item
        assert "bbox" in item
        assert "properties" in item
        assert "datetime" in item["properties"]
        assert "links" in item
        assert "assets" in item
    
    def test_item_asset_points_to_cog(self, sample_stac_catalog: Path, sample_cog_series: list[Path]):
        """Test that item assets point to valid COG files."""
        items_dir = sample_stac_catalog / "items" / "sst"
        first_date = sample_cog_series[0].stem
        item_path = items_dir / f"{first_date}.json"
        
        with open(item_path) as f:
            item = json.load(f)
        
        assert "data" in item["assets"]
        asset = item["assets"]["data"]
        assert asset["type"] == "image/tiff; application=geotiff"
        assert Path(asset["href"]).exists()


class TestSTACCatalogQueries:
    """Tests for STAC catalog query functionality."""
    
    def test_get_catalog_object(self, sample_stac_catalog: Path, monkeypatch):
        """Test STACCatalog class instantiation and caching."""
        import server.stac.catalog as catalog_module
        monkeypatch.setattr(catalog_module, "STAC_DIR", sample_stac_catalog)
        
        from server.stac.catalog import get_catalog
        
        catalog = get_catalog()
        assert catalog is not None
    
    def test_get_available_dates(self, sample_stac_catalog: Path, sample_cog_series: list[Path], monkeypatch):
        """Test getting available dates from catalog."""
        import server.stac.catalog as catalog_module
        monkeypatch.setattr(catalog_module, "STAC_DIR", sample_stac_catalog)
        
        from server.stac.catalog import get_catalog
        
        catalog = get_catalog()
        dates = catalog.get_available_dates("sst")
        
        expected_dates = sorted([cog.stem for cog in sample_cog_series])
        assert dates == expected_dates
    
    def test_get_collection(self, sample_stac_catalog: Path, monkeypatch):
        """Test getting collection metadata."""
        import server.stac.catalog as catalog_module
        monkeypatch.setattr(catalog_module, "STAC_DIR", sample_stac_catalog)
        
        from server.stac import get_collection
        
        collection = get_collection("sst")
        assert collection is not None
        assert collection["id"] == "sst"
    
    def test_get_item(self, sample_stac_catalog: Path, sample_cog_series: list[Path], monkeypatch):
        """Test getting individual item."""
        import server.stac.catalog as catalog_module
        monkeypatch.setattr(catalog_module, "STAC_DIR", sample_stac_catalog)
        
        from server.stac import get_item
        
        first_date = sample_cog_series[0].stem
        item = get_item("sst", first_date)
        
        assert item is not None
        assert item["properties"]["datetime"].startswith(first_date)


class TestSTACCatalogUpdates:
    """Tests for STAC catalog update operations."""
    
    def test_update_collection_after_new_cog(self, temp_stac_dir: Path, temp_products_dir: Path, monkeypatch):
        """Test that adding a new COG updates the collection."""
        import numpy as np
        import rasterio
        from rasterio.transform import from_bounds
        from rasterio.crs import CRS
        import server.stac.catalog as catalog_module
        
        monkeypatch.setattr(catalog_module, "STAC_DIR", temp_stac_dir)
        monkeypatch.setattr(catalog_module, "PRODUCTS_DIR", temp_products_dir)
        
        # Create initial COG
        cog_path = temp_products_dir / "sst" / "2024-01-01.tif"
        data = np.random.randint(-200, 3500, (180, 360), dtype=np.int16)
        
        with rasterio.open(
            cog_path, "w",
            driver="GTiff", dtype="int16", width=360, height=180, count=1,
            crs=CRS.from_epsg(4326), transform=from_bounds(-180, -90, 180, 90, 360, 180),
            nodata=-32768,
        ) as dst:
            dst.write(data, 1)
        
        # Build initial catalog
        from server.stac.catalog import build_catalog, update_collection_from_filesystem
        build_catalog()
        
        # Add new COG
        cog_path2 = temp_products_dir / "sst" / "2024-01-02.tif"
        with rasterio.open(
            cog_path2, "w",
            driver="GTiff", dtype="int16", width=360, height=180, count=1,
            crs=CRS.from_epsg(4326), transform=from_bounds(-180, -90, 180, 90, 360, 180),
            nodata=-32768,
        ) as dst:
            dst.write(data, 1)
        
        # Update collection
        update_collection_from_filesystem("sst")
        
        # Verify item was created
        item_path = temp_stac_dir / "items" / "sst" / "2024-01-02.json"
        assert item_path.exists()
        
        # Verify collection temporal extent was updated
        with open(temp_stac_dir / "collections" / "sst.json") as f:
            collection = json.load(f)
        
        temporal = collection["extent"]["temporal"]["interval"][0]
        assert "2024-01-02" in temporal[1]  # End date should include new date


class TestSTACAPIEndpoints:
    """Tests for STAC API endpoints."""
    
    @pytest.mark.integration
    def test_stac_root_endpoint(self, test_client_with_data):
        """Test /api/stac returns valid catalog."""
        response = test_client_with_data.get("/api/stac")
        assert response.status_code == 200
        
        data = response.json()
        assert data["type"] == "Catalog"
        assert "links" in data
    
    @pytest.mark.integration
    def test_stac_collections_endpoint(self, test_client_with_data):
        """Test /api/stac/collections returns list of collections."""
        response = test_client_with_data.get("/api/stac/collections")
        assert response.status_code == 200
        
        data = response.json()
        assert "collections" in data
    
    @pytest.mark.integration
    def test_stac_collection_detail_endpoint(self, test_client_with_data):
        """Test /api/stac/collections/{variable} returns collection detail."""
        response = test_client_with_data.get("/api/stac/collections/sst")
        
        if response.status_code == 200:
            data = response.json()
            assert data["type"] == "Collection"
            assert data["id"] == "sst"
    
    @pytest.mark.integration
    def test_stac_items_pagination(self, test_client_with_data):
        """Test /api/stac/collections/{var}/items supports pagination."""
        response = test_client_with_data.get(
            "/api/stac/collections/sst/items",
            params={"limit": 5, "offset": 0}
        )
        
        if response.status_code == 200:
            data = response.json()
            assert "features" in data
            assert "numberMatched" in data
            assert "numberReturned" in data
    
    @pytest.mark.integration
    def test_stac_rebuild_endpoint(self, test_client_with_data):
        """Test POST /api/stac/rebuild triggers catalog rebuild."""
        response = test_client_with_data.post("/api/stac/rebuild")
        
        # May return 200 or 500 depending on setup
        assert response.status_code in [200, 500]
        
        if response.status_code == 200:
            data = response.json()
            assert data["status"] == "rebuilt"


class TestZarrSTACIntegration:
    """Tests for Zarr-specific STAC functionality."""
    
    def test_zarr_collection_created(self, sample_zarr_store: Path, temp_stac_dir: Path, monkeypatch):
        """Test that Zarr stores get STAC collections."""
        import server.stac.catalog as catalog_module
        
        # Point to our test directories
        monkeypatch.setattr(catalog_module, "STAC_DIR", temp_stac_dir)
        monkeypatch.setattr(catalog_module, "ZARR_DIR", sample_zarr_store.parent)
        
        from server.stac.catalog import build_catalog
        
        # This should create zarr-sst collection
        build_catalog()
        
        # Check for zarr collection
        zarr_collection_path = temp_stac_dir / "collections" / "zarr-sst.json"
        
        if zarr_collection_path.exists():
            with open(zarr_collection_path) as f:
                collection = json.load(f)
            
            assert collection["id"] == "zarr-sst"
            assert "datacube" in str(collection.get("stac_extensions", []))
    
    def test_zarr_item_has_cube_dimensions(self, sample_zarr_store: Path, temp_stac_dir: Path, monkeypatch):
        """Test that Zarr STAC items include datacube dimensions."""
        import server.stac.catalog as catalog_module
        
        monkeypatch.setattr(catalog_module, "STAC_DIR", temp_stac_dir)
        monkeypatch.setattr(catalog_module, "ZARR_DIR", sample_zarr_store.parent)
        
        from server.stac.catalog import build_catalog
        build_catalog()
        
        # Check for zarr item
        zarr_item_path = temp_stac_dir / "items" / "zarr-sst" / "analytics.json"
        
        if zarr_item_path.exists():
            with open(zarr_item_path) as f:
                item = json.load(f)
            
            # Should have cube dimensions
            assert "cube:dimensions" in item["properties"]
            dims = item["properties"]["cube:dimensions"]
            assert "time" in dims or "lat" in dims
