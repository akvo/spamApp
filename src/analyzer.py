"""Analysis orchestrator: combines boundaries + raster processing.

This is the ONLY module that imports both boundaries and raster (see CONTRACTS.md).
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.boundaries import get_boundary
from src.raster import compute_all_crops

# Variable code → ZIP filename component mapping
_VARIABLE_ZIP_MAP = {
    "production": ("P", "production"),
    "harvested_area": ("H", "harvested_area"),
    "physical_area": ("A", "physical_area"),
    "yield": ("Y", "yield"),
}


@dataclass
class AnalysisResult:
    location_name: str
    admin_level: int
    variable: str
    total: float
    crop_data: pd.DataFrame
    top_crops: list[tuple[str, float]] = field(default_factory=list)


def _find_zip(data_dir: Path, year: int, variable: str) -> Path:
    """Find the ZIP file for a given year and variable."""
    _, zip_component = _VARIABLE_ZIP_MAP.get(variable, ("P", "production"))
    pattern = f"spam{year}V2r0_global_{zip_component}.geotiff.zip"
    zip_path = data_dir / str(year) / pattern
    if not zip_path.exists():
        raise FileNotFoundError(f"Data file not found: {zip_path}")
    return zip_path


def analyze_location(
    location: str,
    admin_level: int = 0,
    data_dir: Path = Path("data"),
    year: int = 2020,
    variable: str = "production",
    top_n: int = 10,
    crops: list[str] | None = None,
    custom_boundary_dir: Path | None = None,
) -> AnalysisResult:
    """On-the-fly analysis for a single location.

    Gets boundary geometry, then computes zonal stats for all crops using
    the "A" (all systems) tech level only.
    """
    data_dir = Path(data_dir)

    # Get boundary
    boundary_gdf = get_boundary(location, admin_level, custom_dir=custom_boundary_dir)
    geometry = boundary_gdf.union_all()

    # Find data ZIP
    zip_path = _find_zip(data_dir, year, variable)

    # Compute zonal stats for all crops, tech level "A" only (totals)
    crop_data = compute_all_crops(
        zip_path, geometry, crops=crops, tech_levels=["A"]
    )

    # Compute total and top crops
    total = float(crop_data["value"].sum())

    top_df = crop_data.nlargest(top_n, "value")
    top_crops = list(zip(top_df["crop_name"], top_df["value"]))

    return AnalysisResult(
        location_name=location,
        admin_level=admin_level,
        variable=variable,
        total=total,
        crop_data=crop_data,
        top_crops=top_crops,
    )


def rank_by_crop(
    crop_code: str,
    admin_level: int = 0,
    index_dir: Path = Path("data/index"),
    top_n: int = 10,
) -> pd.DataFrame:
    """Top N regions for a crop from pre-built parquet index.

    Returns DataFrame sorted descending by production_mt.
    """
    index_dir = Path(index_dir)
    index_path = index_dir / f"level_{admin_level}.parquet"

    if not index_path.exists():
        raise FileNotFoundError(
            f"Index not found: {index_path}. Run 'build-index --level {admin_level}' first."
        )

    df = pd.read_parquet(index_path)
    crop_df = df[df["crop_code"] == crop_code].copy()
    crop_df = crop_df.sort_values("production_mt", ascending=False)

    return crop_df.head(top_n).reset_index(drop=True)
