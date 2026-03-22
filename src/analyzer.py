"""Analysis orchestrator: combines boundaries + raster processing.

This is the ONLY module that imports both boundaries and raster (see CONTRACTS.md).
"""

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from src.boundaries import get_boundary
from src.raster import compute_all_crops, compute_weighted_mean, get_vsi_path

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

    For yield: computes weighted average (weighted by harvested area) instead of sum.
    """
    data_dir = Path(data_dir)

    # Get boundary
    boundary_gdf = get_boundary(location, admin_level, custom_dir=custom_boundary_dir)
    geometry = boundary_gdf.union_all()

    if variable == "yield":
        # Yield needs weighted average: sum(Y × H) / sum(H)
        crop_data = _compute_yield(data_dir, year, geometry, crops)
    else:
        # Production, harvested area, physical area: use sum
        zip_path = _find_zip(data_dir, year, variable)
        crop_data = compute_all_crops(zip_path, geometry, crops=crops, tech_levels=["A"])

    # Compute total and top crops
    if variable == "yield":
        # Overall weighted avg yield across all crops doesn't make much sense,
        # but we compute it as the mean of per-crop yields weighted by their area
        ha_zip = _find_zip(data_dir, year, "harvested_area")
        ha_data = compute_all_crops(ha_zip, geometry, crops=crops, tech_levels=["A"])
        ha_by_crop = dict(zip(ha_data["crop_code"], ha_data["value"]))
        weighted_sum = sum(
            row["value"] * ha_by_crop.get(row["crop_code"], 0)
            for _, row in crop_data.iterrows()
        )
        total_ha = sum(ha_by_crop.get(c, 0) for c in crop_data["crop_code"])
        total = weighted_sum / total_ha if total_ha > 0 else 0.0
    else:
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


def _compute_yield(
    data_dir: Path,
    year: int,
    geometry,
    crops: list[str] | None = None,
) -> pd.DataFrame:
    """Compute weighted average yield per crop: sum(Y × H) / sum(H).

    Reads from both yield and harvested_area ZIPs simultaneously.
    """
    import zipfile

    from src.crops import CROPS, TECH_LEVELS, parse_filename

    yield_zip = _find_zip(data_dir, year, "yield")
    ha_zip = _find_zip(data_dir, year, "harvested_area")

    # Discover yield files
    with zipfile.ZipFile(yield_zip) as zf:
        yield_tifs = [n for n in zf.namelist() if n.endswith(".tif")]

    rows = []
    for tif_name in yield_tifs:
        try:
            variable, crop_code, tech_level = parse_filename(tif_name)
        except ValueError:
            continue

        if tech_level != "A":
            continue
        if crops and crop_code not in crops:
            continue

        yield_vsi = f"/vsizip/{yield_zip}/{tif_name}"

        # Find matching harvested area file
        try:
            ha_vsi = get_vsi_path(ha_zip, "H", crop_code, "A")
        except FileNotFoundError:
            continue

        avg_yield = compute_weighted_mean(yield_vsi, ha_vsi, geometry)

        crop_info = CROPS.get(crop_code, {})
        rows.append(
            {
                "crop_code": crop_code,
                "crop_name": crop_info.get("name", crop_code),
                "category": crop_info.get("category", "Unknown"),
                "tech_level": tech_level,
                "tech_name": TECH_LEVELS.get(tech_level, tech_level),
                "value": avg_yield,
            }
        )

    return pd.DataFrame(rows)


def rank_by_crop(
    crop_code: str,
    admin_level: int = 0,
    index_dir: Path = Path("data/index"),
    top_n: int = 10,
    country_code: str | None = None,
    parent_name: str | None = None,
) -> pd.DataFrame:
    """Top N regions for a crop from pre-built parquet index.

    Args:
        country_code: Filter to this country only.
        parent_name: Filter to children of this parent region
            (e.g., districts within a specific state).

    Returns DataFrame sorted descending by production_mt.
    """
    index_dir = Path(index_dir)
    index_path = index_dir / f"level_{admin_level}.parquet"

    if not index_path.exists():
        raise FileNotFoundError(
            f"Index not found: {index_path}. "
            f"Run 'build-index --level {admin_level}' first."
        )

    df = pd.read_parquet(index_path)
    crop_df = df[df["crop_code"] == crop_code].copy()

    if country_code:
        crop_df = crop_df[crop_df["country_code"] == country_code]

    if parent_name and "parent_name" in crop_df.columns:
        crop_df = crop_df[crop_df["parent_name"] == parent_name]

    crop_df = crop_df.sort_values("production_mt", ascending=False)
    return crop_df.head(top_n).reset_index(drop=True)
