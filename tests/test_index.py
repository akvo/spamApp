"""Tests for src.index — parquet index building."""

import pandas as pd

from src.index import build_index


class TestBuildIndex:
    def test_creates_parquet_file(self, test_data_dir, tmp_path, monkeypatch):
        """Build index with mocked boundaries, verify parquet is created."""
        import geopandas as gpd
        from shapely.geometry import box

        def mock_get_all_boundaries(admin_level, country_code=None, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": ["Testland"],
                    "admin_code": ["TST_0"],
                    "admin_level": [0],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [box(70.0, 20.0, 80.0, 30.0)],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.index.get_all_boundaries", mock_get_all_boundaries)

        output_dir = tmp_path / "index"
        output_dir.mkdir()

        result_path = build_index(
            data_dir=test_data_dir,
            admin_level=0,
            output_dir=output_dir,
            year=2020,
        )

        assert result_path.exists()
        df = pd.read_parquet(result_path)
        assert len(df) > 0
        assert "crop_code" in df.columns
        assert "production_mt" in df.columns
        assert "admin_name" in df.columns

    def test_single_crop_filter(self, test_data_dir, tmp_path, monkeypatch):
        """Build index for single crop only."""
        import geopandas as gpd
        from shapely.geometry import box

        def mock_get_all_boundaries(admin_level, country_code=None, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": ["Testland"],
                    "admin_code": ["TST_0"],
                    "admin_level": [0],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [box(70.0, 20.0, 80.0, 30.0)],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.index.get_all_boundaries", mock_get_all_boundaries)

        output_dir = tmp_path / "index"
        output_dir.mkdir()

        build_index(
            data_dir=test_data_dir,
            admin_level=0,
            output_dir=output_dir,
            year=2020,
            crops=["WHEA"],
        )

        df = pd.read_parquet(output_dir / "level_0.parquet")
        assert set(df["crop_code"]) == {"WHEA"}

    def test_incremental_appends(self, test_data_dir, tmp_path, monkeypatch):
        """Running build_index twice with different crops appends results."""
        import geopandas as gpd
        from shapely.geometry import box

        def mock_get_all_boundaries(admin_level, country_code=None, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": ["Testland"],
                    "admin_code": ["TST_0"],
                    "admin_level": [0],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [box(70.0, 20.0, 80.0, 30.0)],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.index.get_all_boundaries", mock_get_all_boundaries)

        output_dir = tmp_path / "index"
        output_dir.mkdir()

        # First run: WHEA only
        build_index(
            data_dir=test_data_dir, admin_level=0,
            output_dir=output_dir, year=2020, crops=["WHEA"],
        )
        df1 = pd.read_parquet(output_dir / "level_0.parquet")
        assert set(df1["crop_code"]) == {"WHEA"}

        # Second run: RICE only (should append)
        build_index(
            data_dir=test_data_dir, admin_level=0,
            output_dir=output_dir, year=2020, crops=["RICE"],
        )
        df2 = pd.read_parquet(output_dir / "level_0.parquet")
        assert set(df2["crop_code"]) == {"WHEA", "RICE"}
