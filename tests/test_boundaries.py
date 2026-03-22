"""Tests for src.boundaries — admin boundary loading and validation."""

import geopandas as gpd
import pytest
from shapely.geometry import box

from src.boundaries import (
    BOUNDARY_SCHEMA,
    load_custom_boundaries,
    standardize_boundary,
    validate_schema,
)


class TestBoundarySchema:
    def test_schema_has_required_columns(self):
        assert "admin_name" in BOUNDARY_SCHEMA
        assert "admin_code" in BOUNDARY_SCHEMA
        assert "admin_level" in BOUNDARY_SCHEMA
        assert "country_code" in BOUNDARY_SCHEMA
        assert "country_name" in BOUNDARY_SCHEMA
        assert "parent_name" in BOUNDARY_SCHEMA


class TestStandardizeBoundary:
    def test_produces_correct_columns(self):
        gdf = gpd.GeoDataFrame(
            {"name": ["TestRegion"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:4326",
        )
        result = standardize_boundary(
            gdf,
            name_col="name",
            admin_level=1,
            country_code="IND",
            country_name="India",
        )
        for col in BOUNDARY_SCHEMA:
            assert col in result.columns, f"Missing column: {col}"
        assert result.crs.to_epsg() == 4326

    def test_reprojects_to_4326(self):
        gdf = gpd.GeoDataFrame(
            {"name": ["TestRegion"], "geometry": [box(500000, 2000000, 600000, 2100000)]},
            crs="EPSG:32643",  # UTM zone 43N
        )
        result = standardize_boundary(
            gdf,
            name_col="name",
            admin_level=1,
            country_code="IND",
            country_name="India",
        )
        assert result.crs.to_epsg() == 4326

    def test_sets_admin_fields(self):
        gdf = gpd.GeoDataFrame(
            {"name": ["Punjab"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:4326",
        )
        result = standardize_boundary(
            gdf,
            name_col="name",
            admin_level=1,
            country_code="IND",
            country_name="India",
        )
        row = result.iloc[0]
        assert row["admin_name"] == "Punjab"
        assert row["admin_level"] == 1
        assert row["country_code"] == "IND"
        assert row["country_name"] == "India"


class TestValidateSchema:
    def test_valid_gdf_passes(self):
        gdf = gpd.GeoDataFrame(
            {
                "admin_name": ["Test"],
                "admin_code": ["T1"],
                "admin_level": [0],
                "country_code": ["TST"],
                "country_name": ["Testland"],
                "parent_name": [None],
                "geometry": [box(0, 0, 1, 1)],
            },
            crs="EPSG:4326",
        )
        validate_schema(gdf)  # should not raise

    def test_missing_column_raises(self):
        gdf = gpd.GeoDataFrame(
            {"admin_name": ["Test"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:4326",
        )
        with pytest.raises(ValueError, match="Missing required columns"):
            validate_schema(gdf)

    def test_wrong_crs_raises(self):
        gdf = gpd.GeoDataFrame(
            {
                "admin_name": ["Test"],
                "admin_code": ["T1"],
                "admin_level": [0],
                "country_code": ["TST"],
                "country_name": ["Testland"],
                "parent_name": [None],
                "geometry": [box(0, 0, 1, 1)],
            },
            crs="EPSG:32643",
        )
        with pytest.raises(ValueError, match="CRS"):
            validate_schema(gdf)


class TestLoadCustomBoundaries:
    def test_loads_valid_gpkg(self, tmp_path):
        gdf = gpd.GeoDataFrame(
            {
                "admin_name": ["Region1"],
                "admin_code": ["R1"],
                "admin_level": [1],
                "country_code": ["TST"],
                "country_name": ["Testland"],
                "parent_name": ["Testland"],
                "geometry": [box(0, 0, 1, 1)],
            },
            crs="EPSG:4326",
        )
        path = tmp_path / "TST_1.gpkg"
        gdf.to_file(path, driver="GPKG")

        result = load_custom_boundaries(path)
        assert len(result) == 1
        assert result.iloc[0]["admin_name"] == "Region1"

    def test_invalid_schema_raises(self, tmp_path):
        gdf = gpd.GeoDataFrame(
            {"name": ["Region1"], "geometry": [box(0, 0, 1, 1)]},
            crs="EPSG:4326",
        )
        path = tmp_path / "bad.gpkg"
        gdf.to_file(path, driver="GPKG")

        with pytest.raises(ValueError):
            load_custom_boundaries(path)
