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
