"""Build and update the global production parquet index.

Only writes to data/index/. Never modifies source data (see CONTRACTS.md).
"""

from pathlib import Path

import pandas as pd

from src.boundaries import get_all_boundaries
from src.crops import CROPS, VARIABLES
from src.raster import compute_weighted_mean, compute_zonal_sum, get_vsi_path

# Variable code → ZIP filename component
_VAR_ZIP_MAP = {
    "P": "production",
    "H": "harvested_area",
    "A": "physical_area",
    "Y": "yield",
}


def _find_zip(data_dir: Path, year: int, var_code: str) -> Path:
    """Find the ZIP file for a given year and variable code."""
    zip_component = _VAR_ZIP_MAP[var_code]
    pattern = f"spam{year}V2r0_global_{zip_component}.geotiff.zip"
    zip_path = data_dir / str(year) / pattern
    if not zip_path.exists():
        raise FileNotFoundError(f"Data file not found: {zip_path}")
    return zip_path


def build_index(
    data_dir: Path,
    admin_level: int,
    output_dir: Path = Path("data/index"),
    year: int = 2020,
    crops: list[str] | None = None,
    country_code: str | None = None,
    variables: list[str] | None = None,
    custom_boundary_dir: Path | None = None,
) -> Path:
    """Build or update the parquet index for a given admin level.

    Processes "A" (all systems) tech level for specified variables.
    For yield, computes weighted average using harvested area.
    Supports incremental builds — skips already-indexed combos.

    Args:
        variables: Variable codes to index (e.g., ["P", "H", "Y"]).
            Default: all 4 (P, H, A, Y).

    Returns path to the output parquet file.
    """
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"level_{admin_level}.parquet"

    # Load existing index if present (for incremental builds)
    existing_df = None
    existing_keys = set()
    if output_path.exists():
        existing_df = pd.read_parquet(output_path)
        key_cols = ["admin_code", "crop_code"]
        if "variable" in existing_df.columns:
            key_cols.append("variable")
        existing_keys = set(existing_df[key_cols].itertuples(index=False))

    # Determine what to process
    crop_codes = crops if crops else list(CROPS.keys())
    var_codes = variables if variables else list(VARIABLES.keys())

    # Load boundaries
    boundaries_gdf = get_all_boundaries(
        admin_level, country_code=country_code, custom_dir=custom_boundary_dir
    )

    # Pre-locate ZIPs
    zip_paths = {}
    for vc in var_codes:
        try:
            zip_paths[vc] = _find_zip(data_dir, year, vc)
        except FileNotFoundError:
            continue

    # Need harvested area ZIP for yield weighting
    ha_zip = None
    if "Y" in var_codes:
        try:
            ha_zip = _find_zip(data_dir, year, "H")
        except FileNotFoundError:
            pass

    new_rows = []
    for crop_code in crop_codes:
        if crop_code not in CROPS:
            continue
        crop_info = CROPS[crop_code]

        for var_code in var_codes:
            if var_code not in zip_paths:
                continue

            var_info = VARIABLES[var_code]
            zip_path = zip_paths[var_code]

            try:
                vsi_path = get_vsi_path(zip_path, var_code, crop_code, "A")
            except FileNotFoundError:
                continue

            # For yield, also need harvested area path
            ha_vsi = None
            if var_code == "Y" and ha_zip:
                try:
                    ha_vsi = get_vsi_path(ha_zip, "H", crop_code, "A")
                except FileNotFoundError:
                    continue

            for _, boundary in boundaries_gdf.iterrows():
                admin_code = boundary["admin_code"]

                # Skip if already indexed
                key = (admin_code, crop_code, var_code)
                old_key = (admin_code, crop_code)
                if key in existing_keys or old_key in existing_keys:
                    continue

                # Compute value
                if var_code == "Y" and ha_vsi:
                    value = compute_weighted_mean(
                        vsi_path, ha_vsi, boundary.geometry
                    )
                else:
                    value = compute_zonal_sum(vsi_path, boundary.geometry)

                new_rows.append(
                    {
                        "admin_name": boundary["admin_name"],
                        "admin_code": admin_code,
                        "admin_level": admin_level,
                        "country_code": boundary["country_code"],
                        "country_name": boundary["country_name"],
                        "crop_code": crop_code,
                        "crop_name": crop_info["name"],
                        "category": crop_info["category"],
                        "variable": var_code,
                        "variable_name": var_info["name"],
                        "unit": var_info["unit"],
                        "value": value,
                        # Keep backward compat column
                        "production_mt": value if var_code == "P" else 0,
                    }
                )

    # Combine with existing data
    new_df = pd.DataFrame(new_rows)
    if existing_df is not None and not new_df.empty:
        # Add missing columns to old data for backward compat
        if "variable" not in existing_df.columns:
            existing_df["variable"] = "P"
            existing_df["variable_name"] = "Production"
            existing_df["unit"] = "metric tonnes"
            existing_df["value"] = existing_df["production_mt"]
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    elif existing_df is not None:
        combined = existing_df
    else:
        combined = new_df

    combined.to_parquet(output_path, index=False)
    return output_path
