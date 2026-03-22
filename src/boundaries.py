"""Admin boundary loading: GADM via pygadm + custom overrides.

Never imports raster.py (see CONTRACTS.md).
All returned GeoDataFrames are in EPSG:4326.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pygadm

BOUNDARY_SCHEMA = [
    "admin_name",
    "admin_code",
    "admin_level",
    "country_code",
    "country_name",
    "parent_name",
]

DEFAULT_CUSTOM_DIR = Path("data/boundaries")


def validate_schema(gdf: gpd.GeoDataFrame) -> None:
    """Validate that a GeoDataFrame conforms to the boundary schema.

    Raises ValueError if columns are missing or CRS is not EPSG:4326.
    """
    missing = [col for col in BOUNDARY_SCHEMA if col not in gdf.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        raise ValueError(f"CRS must be EPSG:4326, got {gdf.crs}")


def standardize_boundary(
    gdf: gpd.GeoDataFrame,
    name_col: str,
    admin_level: int,
    country_code: str,
    country_name: str,
    code_col: str | None = None,
    parent_col: str | None = None,
) -> gpd.GeoDataFrame:
    """Convert an arbitrary GeoDataFrame to the standard boundary schema.

    Reprojects to EPSG:4326 if needed. Generates admin_code from index if
    code_col is not provided.
    """
    if gdf.crs is not None and gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs("EPSG:4326")

    result = gpd.GeoDataFrame(
        {
            "admin_name": gdf[name_col].values,
            "admin_code": (
                gdf[code_col].values
                if code_col and code_col in gdf.columns
                else [f"{country_code}_{admin_level}_{i}" for i in range(len(gdf))]
            ),
            "admin_level": admin_level,
            "country_code": country_code,
            "country_name": country_name,
            "parent_name": (
                gdf[parent_col].values if parent_col and parent_col in gdf.columns else None
            ),
            "geometry": gdf.geometry.values,
        },
        crs="EPSG:4326",
    )

    return result


def load_custom_boundaries(path: Path) -> gpd.GeoDataFrame:
    """Load a custom boundary file (GeoPackage, Shapefile, etc.) and validate.

    The file must already conform to the standard boundary schema.
    Raises ValueError if schema validation fails.
    """
    gdf = gpd.read_file(path)
    validate_schema(gdf)
    return gdf


def _gadm_to_standard(gdf: gpd.GeoDataFrame, admin_level: int) -> gpd.GeoDataFrame:
    """Convert a pygadm GeoDataFrame to the standard boundary schema."""
    name_col = f"NAME_{admin_level}"
    code_col = f"GID_{admin_level}"

    # Determine parent name
    parent_col = f"NAME_{admin_level - 1}" if admin_level > 0 else None

    # Country info from level 0 columns
    country_name_col = "NAME_0"
    country_code_col = "GID_0"

    result = gpd.GeoDataFrame(
        {
            "admin_name": gdf[name_col].values,
            "admin_code": gdf[code_col].values,
            "admin_level": admin_level,
            "country_code": gdf[country_code_col].str[:3].values,
            "country_name": gdf[country_name_col].values,
            "parent_name": (
                gdf[parent_col].values if parent_col and parent_col in gdf.columns else None
            ),
            "geometry": gdf.geometry.values,
        },
        crs="EPSG:4326",
    )

    return result


def get_boundary(
    location: str,
    admin_level: int = 0,
    custom_dir: Path | None = None,
) -> gpd.GeoDataFrame:
    """Resolve a location name to a boundary GeoDataFrame.

    Checks custom overrides first (if custom_dir provided), then falls back to GADM.
    Raises ValueError if location not found.
    """
    # Check custom boundaries first
    if custom_dir:
        custom_dir = Path(custom_dir)
        if custom_dir.exists():
            for ext in [".gpkg", ".shp"]:
                for path in custom_dir.glob(f"*_{admin_level}{ext}"):
                    try:
                        gdf = load_custom_boundaries(path)
                        matches = gdf[gdf["admin_name"].str.lower() == location.lower()]
                        if not matches.empty:
                            return matches
                    except (ValueError, Exception):
                        continue

    # Fall back to pygadm
    try:
        gdf = pygadm.Items(name=location, admin=str(admin_level))
    except Exception:
        raise ValueError(
            f"Location '{location}' not found at admin level {admin_level}. "
            f"Try pygadm.Names(name='{location}') to search for similar names."
        )

    if gdf.empty:
        raise ValueError(f"Location '{location}' not found at admin level {admin_level}")

    return _gadm_to_standard(gdf, admin_level)


def get_all_boundaries(
    admin_level: int,
    country_code: str | None = None,
    custom_dir: Path | None = None,
) -> gpd.GeoDataFrame:
    """Load ALL boundaries at a given admin level.

    Merges custom overrides with GADM (custom takes precedence per country).
    If country_code is provided, loads only that country's boundaries.
    """
    # Start with GADM
    if country_code:
        gdf = pygadm.Items(admin=str(country_code), content_level=admin_level)
    else:
        gdf = pygadm.Items(admin="*", content_level=admin_level)

    result = _gadm_to_standard(gdf, admin_level)

    # Merge custom overrides
    if custom_dir:
        custom_dir = Path(custom_dir)
        if custom_dir.exists():
            for ext in [".gpkg", ".shp"]:
                for path in custom_dir.glob(f"*_{admin_level}{ext}"):
                    try:
                        custom_gdf = load_custom_boundaries(path)
                        # Remove GADM entries for countries present in custom data
                        custom_countries = set(custom_gdf["country_code"])
                        result = result[~result["country_code"].isin(custom_countries)]
                        result = gpd.GeoDataFrame(
                            pd.concat([result, custom_gdf], ignore_index=True),
                            crs="EPSG:4326",
                        )
                    except (ValueError, Exception):
                        continue

    return result
