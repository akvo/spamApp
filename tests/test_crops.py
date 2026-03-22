"""Tests for src.crops — crop registry and filename parser."""

import pytest

from src.crops import CROPS, TECH_LEVELS, VARIABLES, parse_filename


class TestCropRegistry:
    def test_has_all_46_crops(self):
        assert len(CROPS) == 46

    def test_known_crops_present(self):
        assert "WHEA" in CROPS
        assert "RICE" in CROPS
        assert "MAIZ" in CROPS
        assert "SOYB" in CROPS
        assert "COFF" in CROPS
        assert "REST" in CROPS

    def test_each_crop_has_name_and_category(self):
        for code, info in CROPS.items():
            assert "name" in info, f"{code} missing 'name'"
            assert "category" in info, f"{code} missing 'category'"
            assert isinstance(info["name"], str)
            assert isinstance(info["category"], str)
            assert len(info["name"]) > 0
            assert len(info["category"]) > 0

    def test_crop_codes_are_4_letters(self):
        for code in CROPS:
            assert len(code) == 4, f"{code} is not 4 characters"
            assert code.isalpha(), f"{code} is not all letters"
            assert code.isupper(), f"{code} is not uppercase"

    def test_categories_are_valid(self):
        valid_categories = {
            "Cereals",
            "Roots & Tubers",
            "Pulses",
            "Oil Crops",
            "Sugar Crops",
            "Fibres",
            "Stimulants",
            "Fruits",
            "Vegetables",
            "Other",
        }
        for code, info in CROPS.items():
            assert info["category"] in valid_categories, (
                f"{code} has invalid category: {info['category']}"
            )


class TestTechLevels:
    def test_has_three_levels(self):
        assert len(TECH_LEVELS) == 3

    def test_known_levels(self):
        assert "A" in TECH_LEVELS
        assert "I" in TECH_LEVELS
        assert "R" in TECH_LEVELS


class TestVariables:
    def test_has_four_variables(self):
        assert len(VARIABLES) == 4

    def test_known_variables(self):
        for code in ["P", "H", "A", "Y"]:
            assert code in VARIABLES
            assert "name" in VARIABLES[code]
            assert "unit" in VARIABLES[code]


class TestParseFilename:
    def test_production_wheat_all(self):
        result = parse_filename("spam2020_V2r0_global_P_WHEA_A.tif")
        assert result == ("P", "WHEA", "A")

    def test_harvested_area_rice_irrigated(self):
        result = parse_filename("spam2020_V2r0_global_H_RICE_I.tif")
        assert result == ("H", "RICE", "I")

    def test_yield_maize_rainfed(self):
        result = parse_filename("spam2020_V2r0_global_Y_MAIZ_R.tif")
        assert result == ("Y", "MAIZ", "R")

    def test_physical_area(self):
        result = parse_filename("spam2020_V2r0_global_A_SOYB_A.tif")
        assert result == ("A", "SOYB", "A")

    def test_handles_path_prefix(self):
        result = parse_filename(
            "spam2020V2r0_global_production/spam2020_V2r0_global_P_WHEA_A.tif"
        )
        assert result == ("P", "WHEA", "A")

    def test_invalid_filename_raises(self):
        with pytest.raises(ValueError):
            parse_filename("random_file.tif")

    def test_invalid_crop_code_raises(self):
        with pytest.raises(ValueError):
            parse_filename("spam2020_V2r0_global_P_XXXX_A.tif")

    def test_invalid_variable_raises(self):
        with pytest.raises(ValueError):
            parse_filename("spam2020_V2r0_global_Z_WHEA_A.tif")

    def test_invalid_tech_level_raises(self):
        with pytest.raises(ValueError):
            parse_filename("spam2020_V2r0_global_P_WHEA_X.tif")
