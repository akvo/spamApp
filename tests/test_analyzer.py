"""Tests for src.analyzer — analysis orchestration."""

import pandas as pd
import pytest

from src.analyzer import AnalysisResult, analyze_location, rank_by_crop


class TestAnalyzeLocation:
    def test_returns_analysis_result(self, test_data_dir, covering_polygon, monkeypatch):
        """Mock boundary lookup to return our test polygon, then analyze."""
        import geopandas as gpd

        # Mock get_boundary to return a known geometry
        def mock_get_boundary(location, admin_level=0, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": [location],
                    "admin_code": ["TEST_0"],
                    "admin_level": [admin_level],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [covering_polygon],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.analyzer.get_boundary", mock_get_boundary)

        result = analyze_location(
            location="Testland",
            admin_level=0,
            data_dir=test_data_dir,
            year=2020,
        )

        assert isinstance(result, AnalysisResult)
        assert result.location_name == "Testland"
        assert result.admin_level == 0
        assert result.total > 0

    def test_crop_data_has_correct_columns(self, test_data_dir, covering_polygon, monkeypatch):
        import geopandas as gpd

        def mock_get_boundary(location, admin_level=0, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": [location],
                    "admin_code": ["TEST_0"],
                    "admin_level": [admin_level],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [covering_polygon],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.analyzer.get_boundary", mock_get_boundary)

        result = analyze_location(
            location="Testland",
            data_dir=test_data_dir,
            year=2020,
        )

        assert "crop_code" in result.crop_data.columns
        assert "crop_name" in result.crop_data.columns
        assert "value" in result.crop_data.columns

    def test_top_crops_sorted_descending(self, test_data_dir, covering_polygon, monkeypatch):
        import geopandas as gpd

        def mock_get_boundary(location, admin_level=0, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": [location],
                    "admin_code": ["TEST_0"],
                    "admin_level": [admin_level],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [covering_polygon],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.analyzer.get_boundary", mock_get_boundary)

        result = analyze_location(
            location="Testland",
            data_dir=test_data_dir,
            year=2020,
            top_n=5,
        )

        values = [v for _, v in result.top_crops]
        assert values == sorted(values, reverse=True)


class TestAnalyzeYield:
    def test_yield_uses_weighted_mean(self, test_data_dir_multi, covering_polygon, monkeypatch):
        """Yield should use weighted avg, not sum.

        Yield raster has values 0..99, weight raster has all 2.0.
        Weighted mean = sum(values * 2) / sum(2s) = 4950*2 / (100*2) = 49.5 per crop.
        """
        import geopandas as gpd

        def mock_get_boundary(location, admin_level=0, custom_dir=None):
            return gpd.GeoDataFrame(
                {
                    "admin_name": [location],
                    "admin_code": ["TEST_0"],
                    "admin_level": [admin_level],
                    "country_code": ["TST"],
                    "country_name": ["Testland"],
                    "parent_name": [None],
                    "geometry": [covering_polygon],
                },
                crs="EPSG:4326",
            )

        monkeypatch.setattr("src.analyzer.get_boundary", mock_get_boundary)

        result = analyze_location(
            location="Testland",
            data_dir=test_data_dir_multi,
            year=2020,
            variable="yield",
        )

        assert result.variable == "yield"
        # Each crop should have weighted avg = 49.5
        for _, row in result.crop_data.iterrows():
            assert abs(row["value"] - 49.5) < 0.1, f"{row['crop_code']}: {row['value']}"
        # Total should not be a sum — it's a weighted average
        assert result.total < 100  # should be ~49.5, not 99


class TestRankByCrop:
    def test_returns_sorted_dataframe(self, tmp_path):
        """Create a test parquet index and verify ranking."""
        index_df = pd.DataFrame(
            {
                "admin_name": ["Country A", "Country B", "Country C"],
                "admin_code": ["A", "B", "C"],
                "admin_level": [0, 0, 0],
                "country_code": ["AAA", "BBB", "CCC"],
                "country_name": ["Country A", "Country B", "Country C"],
                "crop_code": ["MAIZ", "MAIZ", "MAIZ"],
                "crop_name": ["Maize", "Maize", "Maize"],
                "category": ["Cereals", "Cereals", "Cereals"],
                "production_mt": [500.0, 1000.0, 200.0],
            }
        )

        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        result = rank_by_crop("MAIZ", admin_level=0, index_dir=index_dir, top_n=3)

        assert len(result) == 3
        assert result.iloc[0]["admin_name"] == "Country B"
        assert result.iloc[0]["production_mt"] == 1000.0
        assert result.iloc[1]["admin_name"] == "Country A"
        assert result.iloc[2]["admin_name"] == "Country C"

    def test_top_n_limits_results(self, tmp_path):
        index_df = pd.DataFrame(
            {
                "admin_name": [f"Country {i}" for i in range(10)],
                "admin_code": [str(i) for i in range(10)],
                "admin_level": [0] * 10,
                "country_code": [f"C{i:02d}" for i in range(10)],
                "country_name": [f"Country {i}" for i in range(10)],
                "crop_code": ["WHEA"] * 10,
                "crop_name": ["Wheat"] * 10,
                "category": ["Cereals"] * 10,
                "production_mt": [float(i * 100) for i in range(10)],
            }
        )

        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        result = rank_by_crop("WHEA", admin_level=0, index_dir=index_dir, top_n=3)
        assert len(result) == 3

    def test_missing_index_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            rank_by_crop("MAIZ", admin_level=0, index_dir=tmp_path / "nonexistent")

    def test_rank_filters_by_tech_level(self, tmp_path):
        """Each tech_level value returns only matching rows."""
        index_df = pd.DataFrame(
            {
                "admin_name": ["X", "X", "X", "Y", "Y", "Y"],
                "admin_code": ["X0", "X0", "X0", "Y0", "Y0", "Y0"],
                "admin_level": [0] * 6,
                "country_code": ["XX"] * 6,
                "country_name": ["X Land", "X Land", "X Land", "Y Land", "Y Land", "Y Land"],
                "crop_code": ["MAIZ"] * 6,
                "crop_name": ["Maize"] * 6,
                "category": ["Cereals"] * 6,
                "production_mt": [1000.0, 600.0, 400.0, 500.0, 300.0, 200.0],
                "variable": ["P"] * 6,
                "value": [1000.0, 600.0, 400.0, 500.0, 300.0, 200.0],
                "tech_level": ["A", "I", "R", "A", "I", "R"],
            }
        )
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        result_a = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="A")
        assert len(result_a) == 2
        assert result_a.iloc[0]["rank_value"] == 1000.0

        result_i = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="I")
        assert len(result_i) == 2
        assert result_i.iloc[0]["rank_value"] == 600.0

        result_r = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="R")
        assert len(result_r) == 2
        assert result_r.iloc[0]["rank_value"] == 400.0

    def test_rank_nan_tech_treated_as_a(self, tmp_path):
        """When all rows have NaN tech_level, they are treated as 'A'."""
        index_df = pd.DataFrame(
            {
                "admin_name": ["X", "Y"],
                "admin_code": ["X0", "Y0"],
                "admin_level": [0, 0],
                "country_code": ["XX", "YY"],
                "country_name": ["X Land", "Y Land"],
                "crop_code": ["MAIZ", "MAIZ"],
                "crop_name": ["Maize", "Maize"],
                "category": ["Cereals", "Cereals"],
                "production_mt": [1000.0, 500.0],
                "variable": ["P", "P"],
                "value": [1000.0, 500.0],
                "tech_level": [None, None],
            }
        )
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        result = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="A")
        assert len(result) == 2

        result_i = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="I")
        assert len(result_i) == 0

    def test_rank_drops_null_when_real_tech_exists(self, tmp_path):
        """Legacy null rows are dropped when real A/I/R rows exist."""
        index_df = pd.DataFrame(
            {
                "admin_name": ["X", "X", "X"],
                "admin_code": ["X0", "X0", "X0"],
                "admin_level": [0, 0, 0],
                "country_code": ["XX", "XX", "XX"],
                "country_name": ["X Land", "X Land", "X Land"],
                "crop_code": ["MAIZ", "MAIZ", "MAIZ"],
                "crop_name": ["Maize", "Maize", "Maize"],
                "category": ["Cereals", "Cereals", "Cereals"],
                "production_mt": [1000.0, 1000.0, 600.0],
                "variable": ["P", "P", "P"],
                "value": [1000.0, 1000.0, 600.0],
                "tech_level": [None, "A", "I"],
            }
        )
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        # Should get 1 row for A (null dropped, not doubled)
        result_a = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="A")
        assert len(result_a) == 1
        assert result_a.iloc[0]["rank_value"] == 1000.0

        result_i = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="I")
        assert len(result_i) == 1
        assert result_i.iloc[0]["rank_value"] == 600.0

    def test_rank_default_tech_is_a(self, tmp_path):
        """Calling without tech_level returns same as tech_level='A'."""
        index_df = pd.DataFrame(
            {
                "admin_name": ["X", "X"],
                "admin_code": ["X0", "X0"],
                "admin_level": [0, 0],
                "country_code": ["XX", "XX"],
                "country_name": ["X Land", "X Land"],
                "crop_code": ["MAIZ", "MAIZ"],
                "crop_name": ["Maize", "Maize"],
                "category": ["Cereals", "Cereals"],
                "production_mt": [1000.0, 600.0],
                "variable": ["P", "P"],
                "value": [1000.0, 600.0],
                "tech_level": ["A", "I"],
            }
        )
        index_dir = tmp_path / "index"
        index_dir.mkdir()
        index_df.to_parquet(index_dir / "level_0.parquet")

        default = rank_by_crop("MAIZ", index_dir=index_dir)
        explicit = rank_by_crop("MAIZ", index_dir=index_dir, tech_level="A")

        assert len(default) == len(explicit)
        assert default.iloc[0]["rank_value"] == explicit.iloc[0]["rank_value"]
