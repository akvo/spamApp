"""Build and update the global production parquet index.

Only writes to data/index/. Never modifies source data (see CONTRACTS.md).
"""

from pathlib import Path

import pandas as pd

from src.boundaries import get_all_boundaries
from src.crops import CROPS
from src.raster import compute_zonal_sum, get_vsi_path


def build_index(
    data_dir: Path,
    admin_level: int,
    output_dir: Path = Path("data/index"),
    year: int = 2020,
    crops: list[str] | None = None,
    country_code: str | None = None,
    custom_boundary_dir: Path | None = None,
) -> Path:
    """Build or update the parquet index for a given admin level.

    Processes "A" (all systems) tech level only for production totals.
    Supports incremental builds — skips already-indexed crop/boundary combos.

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
        existing_keys = set(zip(existing_df["admin_code"], existing_df["crop_code"]))

    # Determine which crops to process
    crop_codes = crops if crops else list(CROPS.keys())

    # Load boundaries
    boundaries_gdf = get_all_boundaries(
        admin_level, country_code=country_code, custom_dir=custom_boundary_dir
    )

    # Find the production ZIP
    zip_pattern = f"spam{year}V2r0_global_production.geotiff.zip"
    zip_path = data_dir / str(year) / zip_pattern
    if not zip_path.exists():
        raise FileNotFoundError(f"Data file not found: {zip_path}")

    new_rows = []
    for crop_code in crop_codes:
        if crop_code not in CROPS:
            continue

        crop_info = CROPS[crop_code]

        # Get VSI path for this crop
        try:
            vsi_path = get_vsi_path(zip_path, "P", crop_code, "A")
        except FileNotFoundError:
            continue

        for _, boundary in boundaries_gdf.iterrows():
            admin_code = boundary["admin_code"]

            # Skip if already indexed
            if (admin_code, crop_code) in existing_keys:
                continue

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
                    "production_mt": value,
                }
            )

    # Combine with existing data
    new_df = pd.DataFrame(new_rows)
    if existing_df is not None and not new_df.empty:
        combined = pd.concat([existing_df, new_df], ignore_index=True)
    elif existing_df is not None:
        combined = existing_df
    else:
        combined = new_df

    combined.to_parquet(output_path, index=False)
    return output_path
