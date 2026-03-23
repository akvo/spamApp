"""GeoTIFF reading and zonal statistics.

Reads SPAM GeoTIFFs directly from ZIP using GDAL's /vsizip/ virtual filesystem.
Never imports boundaries.py (see CONTRACTS.md).
"""

import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from rasterio.mask import mask as rasterio_mask
from shapely import Geometry

from src.crops import CROPS, TECH_LEVELS, parse_filename


def get_vsi_path(zip_path: Path, variable: str, crop_code: str, tech_level: str) -> str:
    """Construct /vsizip/ path for a specific crop/tech GeoTIFF.

    Detects the internal subdirectory name from the ZIP.
    """
    zip_path = Path(zip_path)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()

    # Find matching file
    suffix = f"_{variable}_{crop_code}_{tech_level}.tif"
    for name in names:
        if name.endswith(suffix):
            return f"/vsizip/{zip_path}/{name}"

    raise FileNotFoundError(f"No file matching *{suffix} found in {zip_path.name}")


def compute_zonal_sum(raster_path: str, geometry: Geometry) -> float:
    """Sum all valid pixel values within the geometry.

    Returns 0.0 if geometry is outside raster bounds or no valid pixels exist.
    Uses crop=True to read only the bounding box of the geometry.
    """
    try:
        with rasterio.open(raster_path) as src:
            out_image, _ = rasterio_mask(
                src, [geometry], crop=True, nodata=src.nodata, all_touched=False
            )
            nodata = src.nodata

        data = out_image[0]  # single band

        # Exclude nodata and NaN pixels
        valid_mask = ~np.isnan(data)
        if nodata is not None and not np.isnan(nodata):
            valid_mask &= data != nodata
        valid = data[valid_mask]

        # Exclude negative values (common nodata sentinel in SPAM data)
        valid = valid[valid >= 0]

        return float(np.sum(valid)) if valid.size > 0 else 0.0

    except ValueError:
        # rasterio raises ValueError when geometry doesn't overlap raster
        return 0.0


def compute_weighted_mean(
    value_raster_path: str,
    weight_raster_path: str,
    geometry: Geometry,
) -> float:
    """Compute area-weighted mean: sum(value × weight) / sum(weight).

    Used for yield: avg_yield = sum(yield_pixels × ha_pixels) / sum(ha_pixels).
    Returns 0.0 if no valid pixels or total weight is 0.
    """
    try:
        with rasterio.open(value_raster_path) as val_src:
            val_image, _ = rasterio_mask(
                val_src, [geometry], crop=True, nodata=val_src.nodata, all_touched=False
            )
            val_nodata = val_src.nodata

        with rasterio.open(weight_raster_path) as wt_src:
            wt_image, _ = rasterio_mask(
                wt_src, [geometry], crop=True, nodata=wt_src.nodata, all_touched=False
            )
            wt_nodata = wt_src.nodata

        val_data = val_image[0]
        wt_data = wt_image[0]

        # Build valid mask: both value and weight must be valid
        valid_mask = ~np.isnan(val_data) & ~np.isnan(wt_data)
        if val_nodata is not None and not np.isnan(val_nodata):
            valid_mask &= val_data != val_nodata
        if wt_nodata is not None and not np.isnan(wt_nodata):
            valid_mask &= wt_data != wt_nodata
        valid_mask &= val_data >= 0
        valid_mask &= wt_data >= 0

        val_valid = val_data[valid_mask]
        wt_valid = wt_data[valid_mask]

        total_weight = float(np.sum(wt_valid))
        if total_weight == 0:
            return 0.0

        return float(np.sum(val_valid * wt_valid) / total_weight)

    except ValueError:
        return 0.0


def compute_all_crops(
    zip_path: Path,
    geometry: Geometry,
    crops: list[str] | None = None,
    tech_levels: list[str] | None = None,
) -> pd.DataFrame:
    """Process crop/tech combinations from a ZIP and return a DataFrame.

    Args:
        zip_path: Path to the SPAM GeoTIFF ZIP file.
        geometry: Shapely geometry to compute stats within.
        crops: Optional list of crop codes to process. None = all found in ZIP.
        tech_levels: Optional list of tech levels to process. None = all found in ZIP.

    Returns:
        DataFrame with columns [crop_code, crop_name, category, tech_level, value].
    """
    zip_path = Path(zip_path)

    # Discover available files in the ZIP
    with zipfile.ZipFile(zip_path) as zf:
        tif_names = [n for n in zf.namelist() if n.endswith(".tif")]

    rows = []
    for tif_name in tif_names:
        try:
            variable, crop_code, tech_level = parse_filename(tif_name)
        except ValueError:
            continue

        if crops and crop_code not in crops:
            continue
        if tech_levels and tech_level not in tech_levels:
            continue

        vsi_path = f"/vsizip/{zip_path}/{tif_name}"
        value = compute_zonal_sum(vsi_path, geometry)

        crop_info = CROPS.get(crop_code, {})
        rows.append(
            {
                "crop_code": crop_code,
                "crop_name": crop_info.get("name", crop_code),
                "category": crop_info.get("category", "Unknown"),
                "tech_level": tech_level,
                "tech_name": TECH_LEVELS.get(tech_level, tech_level),
                "value": value,
            }
        )

    return pd.DataFrame(rows)


def batch_zonal_stats(
    raster_path: str,
    geometries: list[Geometry],
) -> list[float]:
    """Compute zonal sum for one raster against many geometries.

    Returns a list of floats (one per geometry) in the same order.
    """
    return [compute_zonal_sum(raster_path, geom) for geom in geometries]


def batch_zonal_stats_gdf(
    raster_path: str,
    gdf,
) -> list[float]:
    """Compute zonal sum for one raster against ALL geometries in a GeoDataFrame.

    Uses rasterstats for efficient single-pass processing — reads the raster
    once and computes stats for all polygons. Much faster than per-geometry calls.

    Returns a list of floats (one per row in gdf) in the same order.
    """
    from rasterstats import zonal_stats

    stats = zonal_stats(gdf, raster_path, stats=["sum"], nodata=0, all_touched=False)
    return [float(s["sum"]) if s["sum"] is not None else 0.0 for s in stats]


def batch_weighted_mean_gdf(
    value_raster_path: str,
    weight_raster_path: str,
    gdf,
) -> list[float]:
    """Compute weighted mean for ALL geometries in a GeoDataFrame.

    avg = sum(value * weight) / sum(weight) for each geometry.
    Reads each raster once via rasterstats.
    """
    # rasterstats doesn't support weighted mean natively
    # rasterstats doesn't support weighted mean natively, so fall back to per-geometry
    results = []
    for geom in gdf.geometry:
        results.append(compute_weighted_mean(value_raster_path, weight_raster_path, geom))
    return results
