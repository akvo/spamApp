"""Build and update the global production parquet index.

Only writes to data/index/. Never modifies source data (see CONTRACTS.md).
"""

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from src.boundaries import get_all_boundaries, get_cached_country_names
from src.crops import CROPS, VARIABLES
from src.raster import (
    batch_weighted_mean_gdf,
    batch_zonal_stats_gdf,
    get_vsi_path,
)

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

    Uses batch zonal stats — reads each raster once for ALL boundaries.
    Supports incremental builds — skips already-indexed combos.

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
        if "variable" in existing_df.columns:
            existing_keys = set(
                existing_df[["admin_code", "crop_code", "variable"]].itertuples(
                    index=False
                )
            )
        else:
            existing_keys = set(
                existing_df[["admin_code", "crop_code"]].itertuples(index=False)
            )

    # Determine what to process
    crop_codes = crops if crops else list(CROPS.keys())
    var_codes = variables if variables else list(VARIABLES.keys())

    # Load boundaries
    boundaries_gdf = get_all_boundaries(
        admin_level, country_code=country_code, custom_dir=custom_boundary_dir
    )

    if boundaries_gdf.empty:
        return output_path

    n_boundaries = len(boundaries_gdf)
    label = country_code or "all"
    print(
        f"  [{label}] {n_boundaries} regions, "
        f"{len(crop_codes if crops else CROPS)} crops, "
        f"{len(var_codes)} variables",
        flush=True,
    )

    # Pre-locate ZIPs
    zip_paths = {}
    for vc in var_codes:
        try:
            zip_paths[vc] = _find_zip(data_dir, year, vc)
        except FileNotFoundError:
            continue

    ha_zip = None
    if "Y" in var_codes:
        try:
            ha_zip = _find_zip(data_dir, year, "H")
        except FileNotFoundError:
            pass

    new_rows = []
    total_combos = len(crop_codes) * len(var_codes)
    combo_done = 0
    t_start = time.time()

    for crop_code in crop_codes:
        if crop_code not in CROPS:
            continue
        crop_info = CROPS[crop_code]

        for var_code in var_codes:
            if var_code not in zip_paths:
                combo_done += 1
                continue

            combo_done += 1
            var_info = VARIABLES[var_code]
            zip_path = zip_paths[var_code]

            # Check if ALL boundaries for this crop/var are already indexed
            sample_key = (
                boundaries_gdf.iloc[0]["admin_code"],
                crop_code,
                var_code,
            )
            if sample_key in existing_keys:
                continue

            try:
                vsi_path = get_vsi_path(zip_path, var_code, crop_code, "A")
            except FileNotFoundError:
                continue

            # Progress
            elapsed = time.time() - t_start
            pct = combo_done / total_combos * 100
            crop_name = crop_info["name"]
            var_name = var_info["name"]
            print(
                f"  [{label}] {combo_done}/{total_combos} "
                f"({pct:.0f}%) {crop_name}/{var_name} "
                f"[{elapsed:.0f}s]",
                end="\r",
                flush=True,
            )

            # Batch compute: one raster read for ALL boundaries
            if var_code == "Y" and ha_zip:
                try:
                    ha_vsi = get_vsi_path(ha_zip, "H", crop_code, "A")
                except FileNotFoundError:
                    continue
                values = batch_weighted_mean_gdf(vsi_path, ha_vsi, boundaries_gdf)
            else:
                values = batch_zonal_stats_gdf(vsi_path, boundaries_gdf)

            for i, (_, boundary) in enumerate(boundaries_gdf.iterrows()):
                new_rows.append(
                    {
                        "admin_name": boundary["admin_name"],
                        "admin_code": boundary["admin_code"],
                        "admin_level": admin_level,
                        "country_code": boundary["country_code"],
                        "country_name": boundary["country_name"],
                        "crop_code": crop_code,
                        "crop_name": crop_info["name"],
                        "category": crop_info["category"],
                        "variable": var_code,
                        "variable_name": var_info["name"],
                        "unit": var_info["unit"],
                        "value": values[i],
                        "production_mt": values[i] if var_code == "P" else 0,
                    }
                )

    elapsed = time.time() - t_start
    print(
        f"  [{label}] Done: {len(new_rows):,} rows "
        f"in {elapsed:.0f}s" + " " * 40,
        flush=True,
    )

    # Combine with existing data
    new_df = pd.DataFrame(new_rows)
    if existing_df is not None and not new_df.empty:
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

    if not combined.empty:
        combined.to_parquet(output_path, index=False)
    return output_path


def _build_single_country(args):
    """Worker function for parallel index building."""
    data_dir, admin_level, output_dir, year, crops, country_code, variables = args

    # Each country gets its own subdirectory to avoid file conflicts
    country_dir = output_dir / country_code
    country_dir.mkdir(parents=True, exist_ok=True)

    result = build_index(
        data_dir=data_dir,
        admin_level=admin_level,
        output_dir=country_dir,
        year=year,
        crops=crops,
        country_code=country_code,
        variables=variables,
    )
    return country_code, result


def build_index_parallel(
    data_dir: Path,
    admin_level: int,
    output_dir: Path = Path("data/index"),
    year: int = 2020,
    crops: list[str] | None = None,
    country_codes: list[str] | None = None,
    variables: list[str] | None = None,
    max_workers: int | None = None,
) -> Path:
    """Build index for multiple countries in parallel.

    Each country is processed independently in a separate process.
    Results are merged into a single parquet file.
    """
    data_dir = Path(data_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if country_codes is None:
        # Use all cached countries
        countries = get_cached_country_names()
        country_codes = list(countries.values())

    if max_workers is None:
        max_workers = max(1, os.cpu_count() - 1)

    # Each country builds to a temp file, then we merge
    temp_dir = output_dir / "_temp"
    temp_dir.mkdir(exist_ok=True)

    args_list = [
        (data_dir, admin_level, temp_dir, year, crops, cc, variables)
        for cc in country_codes
    ]

    completed = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_build_single_country, args): args[5]
            for args in args_list
        }
        for future in as_completed(futures):
            cc = futures[future]
            try:
                country_code, result_path = future.result()
                completed.append((country_code, result_path))
                print(f"  Done: {country_code}")
            except Exception as e:
                print(f"  Failed: {cc}: {e}")

    # Merge all per-country files + existing index
    output_path = output_dir / f"level_{admin_level}.parquet"
    dfs = []

    # Keep existing data for countries NOT in this run
    if output_path.exists():
        existing = pd.read_parquet(output_path)
        processed_codes = set(country_codes)
        keep = existing[~existing["country_code"].isin(processed_codes)]
        if not keep.empty:
            dfs.append(keep)

    # Read each country's temp parquet
    for cc, _ in completed:
        temp_file = temp_dir / cc / f"level_{admin_level}.parquet"
        if temp_file.exists():
            dfs.append(pd.read_parquet(temp_file))

    if dfs:
        combined = pd.concat(dfs, ignore_index=True)
        combined.to_parquet(output_path, index=False)
        print(f"  Merged: {len(combined):,} total rows")

    # Clean up temp
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)

    return output_path
