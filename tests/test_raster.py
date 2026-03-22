"""Tests for src.raster — GeoTIFF reading and zonal statistics."""

import numpy as np

from src.raster import compute_all_crops, compute_zonal_sum, get_vsi_path


class TestGetVsiPath:
    def test_constructs_correct_path(self, test_zip):
        path = get_vsi_path(test_zip, "P", "WHEA", "A")
        assert "/vsizip/" in path
        assert "spam2020_V2r0_global_P_WHEA_A.tif" in path

    def test_includes_subdirectory(self, test_zip):
        path = get_vsi_path(test_zip, "P", "RICE", "A")
        assert "spam2020V2r0_global_production/" in path


class TestComputeZonalSum:
    def test_full_coverage(self, tiny_geotiff, covering_polygon):
        """Sum of all pixels 0..99 = 4950."""
        result = compute_zonal_sum(str(tiny_geotiff), covering_polygon)
        assert np.isclose(result, 4950.0)

    def test_partial_coverage(self, tiny_geotiff, partial_polygon):
        """Left half of raster: columns 0-4, all rows. Expected sum = 2350."""
        result = compute_zonal_sum(str(tiny_geotiff), partial_polygon)
        assert np.isclose(result, 2350.0)

    def test_outside_returns_zero(self, tiny_geotiff, outside_polygon):
        """Polygon completely outside raster bounds should return 0.0."""
        result = compute_zonal_sum(str(tiny_geotiff), outside_polygon)
        assert result == 0.0

    def test_nodata_excluded(self, tiny_geotiff_with_nodata, covering_polygon):
        """Nodata pixels (-1) at positions (0,0), (0,1), (0,2) excluded.
        Valid sum = 4950 - 0 - 1 - 2 = 4947.
        """
        result = compute_zonal_sum(str(tiny_geotiff_with_nodata), covering_polygon)
        assert np.isclose(result, 4947.0)

    def test_returns_float(self, tiny_geotiff, covering_polygon):
        result = compute_zonal_sum(str(tiny_geotiff), covering_polygon)
        assert isinstance(result, float)


class TestComputeAllCrops:
    def test_returns_dataframe(self, test_zip, covering_polygon):
        df = compute_all_crops(test_zip, covering_polygon)
        assert len(df) > 0
        assert "crop_code" in df.columns
        assert "crop_name" in df.columns
        assert "tech_level" in df.columns
        assert "value" in df.columns

    def test_correct_crop_codes(self, test_zip, covering_polygon):
        """Test ZIP has WHEA and RICE."""
        df = compute_all_crops(test_zip, covering_polygon)
        codes = set(df["crop_code"])
        assert "WHEA" in codes
        assert "RICE" in codes

    def test_values_are_correct(self, test_zip, covering_polygon):
        """Both crops use same raster, so both should sum to 4950."""
        df = compute_all_crops(test_zip, covering_polygon)
        for _, row in df.iterrows():
            assert np.isclose(row["value"], 4950.0)

    def test_filter_by_crop(self, test_zip, covering_polygon):
        df = compute_all_crops(test_zip, covering_polygon, crops=["WHEA"])
        assert len(df) == 1
        assert df.iloc[0]["crop_code"] == "WHEA"

    def test_filter_by_tech_level(self, test_zip, covering_polygon):
        df = compute_all_crops(test_zip, covering_polygon, tech_levels=["A"])
        assert all(df["tech_level"] == "A")
