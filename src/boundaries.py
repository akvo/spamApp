"""Admin boundary loading: local GeoPackage cache + GADM fallback + custom overrides.

Never imports raster.py (see CONTRACTS.md).
All returned GeoDataFrames are in EPSG:4326.
"""

from pathlib import Path

import geopandas as gpd
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
DEFAULT_CACHE_PATH = Path("data/boundaries/gadm_cache.gpkg")

_GADM_BASE_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json"


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


def _resolve_country_code(location: str) -> str:
    """Look up GADM ISO3 code for a location name using pygadm.Names."""
    try:
        name_df = pygadm.Names(name=location)
    except Exception:
        raise ValueError(f"Location '{location}' not found in GADM database.")

    if name_df.empty:
        raise ValueError(f"Location '{location}' not found in GADM database.")

    # pygadm returns different GID columns depending on match level
    # e.g., GID_0 for countries, GID_1 for states ("IND.36_1")
    # Extract the ISO3 country code from whichever GID column exists
    row = name_df.iloc[0]
    for col in ["GID_0", "GID_1", "GID_2"]:
        if col in row.index:
            # GID format: "IND" or "IND.36_1" or "IND.36.5_2" — first 3 chars are ISO3
            return str(row[col])[:3]

    raise ValueError(f"Could not determine country code for '{location}'")


def _fetch_gadm(country_code: str, admin_level: int) -> gpd.GeoDataFrame:
    """Download GADM boundaries directly from geodata.ucdavis.edu.

    Returns a GeoDataFrame with GADM columns (GID_0, NAME_0, GID_1, NAME_1, etc.)
    """
    url = f"{_GADM_BASE_URL}/gadm41_{country_code}_{admin_level}.json"
    try:
        gdf = gpd.read_file(url)
    except Exception:
        raise ValueError(
            f"Could not download GADM data for {country_code} level {admin_level}. "
            f"URL: {url}"
        )

    if gdf.empty:
        raise ValueError(f"No GADM data for {country_code} level {admin_level}")

    return gdf


def _cache_layer_name(country_code: str, admin_level: int) -> str:
    """GeoPackage layer name for a country/level combo."""
    return f"{country_code}_{admin_level}"


def _read_cache(
    country_code: str, admin_level: int, cache_path: Path = DEFAULT_CACHE_PATH
) -> gpd.GeoDataFrame | None:
    """Read boundaries from local GeoPackage cache. Returns None if not cached."""
    if not cache_path.exists():
        return None
    layer = _cache_layer_name(country_code, admin_level)
    try:
        import fiona

        layers = fiona.listlayers(cache_path)
        if layer not in layers:
            return None
        return gpd.read_file(cache_path, layer=layer)
    except Exception:
        return None


def _write_cache(
    gdf: gpd.GeoDataFrame,
    country_code: str,
    admin_level: int,
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> None:
    """Write boundaries to local GeoPackage cache."""
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    layer = _cache_layer_name(country_code, admin_level)
    gdf.to_file(cache_path, layer=layer, driver="GPKG")


def fetch_and_cache(
    country_code: str,
    admin_level: int,
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> gpd.GeoDataFrame:
    """Fetch GADM data, cache locally, return the GeoDataFrame.

    Reads from cache if available, downloads from GADM if not.
    """
    cached = _read_cache(country_code, admin_level, cache_path)
    if cached is not None:
        return cached

    gdf = _fetch_gadm(country_code, admin_level)
    _write_cache(gdf, country_code, admin_level, cache_path)
    return gdf


def list_cached_countries(cache_path: Path = DEFAULT_CACHE_PATH) -> list[dict]:
    """List all countries/levels in the cache. Returns list of {code, level} dicts."""
    if not cache_path.exists():
        return []
    try:
        import fiona

        layers = fiona.listlayers(cache_path)
        results = []
        for layer in layers:
            parts = layer.rsplit("_", 1)
            if len(parts) == 2:
                results.append({"code": parts[0], "level": int(parts[1])})
        return results
    except Exception:
        return []


def _fix_gadm_name(name: str) -> str:
    """Insert spaces in CamelCase GADM names.

    'DemocraticRepublicoftheCongo' -> 'Democratic Republic of the Congo'
    'SouthAfrica' -> 'South Africa'
    """
    import re

    # Split before uppercase letters: "SouthAfrica" -> "South Africa"
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", name)
    # Split before lowercase words like "of", "the", "and":
    # "Republicofthe" -> "Republic of the"
    spaced = re.sub(r"(?<=[a-zA-Z])(of|the|and|del|das|dos)(?=[a-zA-Z])", r" \1 ", spaced)
    # Clean up double spaces
    spaced = re.sub(r"  +", " ", spaced).strip()
    return spaced


def get_cached_country_names(
    cache_path: Path = DEFAULT_CACHE_PATH,
) -> dict[str, str]:
    """Return {display_name: gadm_name} for all level-0 cached countries.

    Keys are cleaned display names, values are the original GADM names
    (needed for boundary lookups).
    """
    if not cache_path.exists():
        return {}
    entries = list_cached_countries(cache_path)
    level0_codes = [e["code"] for e in entries if e["level"] == 0]

    result = {}
    for code in level0_codes:
        gdf = _read_cache(code, 0, cache_path)
        if gdf is not None:
            name_col = "COUNTRY" if "COUNTRY" in gdf.columns else "NAME_0"
            gadm_name = gdf[name_col].iloc[0]
            display = _fix_gadm_name(gadm_name)
            result[display] = code
    return dict(sorted(result.items()))


def get_cached_states(
    country_code: str, cache_path: Path = DEFAULT_CACHE_PATH
) -> list[str]:
    """Return sorted state names for a cached country."""
    gdf = _read_cache(country_code, 1, cache_path)
    if gdf is None:
        return []
    return sorted(gdf["NAME_1"].unique())


def get_cached_districts(
    country_code: str, state_name: str, cache_path: Path = DEFAULT_CACHE_PATH
) -> list[str]:
    """Return sorted district names for a cached state."""
    gdf = _read_cache(country_code, 2, cache_path)
    if gdf is None:
        return []
    filtered = gdf[gdf["NAME_1"] == state_name]
    return sorted(filtered["NAME_2"].unique())


def _gadm_to_standard(gdf: gpd.GeoDataFrame, admin_level: int) -> gpd.GeoDataFrame:
    """Convert a GADM GeoDataFrame to the standard boundary schema.

    At level 0, dissolves all polygons for the same country into one
    (GADM splits disputed territories into separate rows).
    """
    # GADM level 0 uses COUNTRY column, higher levels use NAME_N
    if admin_level == 0:
        name_col = "COUNTRY" if "COUNTRY" in gdf.columns else "NAME_0"
    else:
        name_col = f"NAME_{admin_level}"

    code_col = f"GID_{admin_level}" if f"GID_{admin_level}" in gdf.columns else "GID_0"

    # Country info
    country_name_col = "COUNTRY" if "COUNTRY" in gdf.columns else "NAME_0"

    # At level 0, dissolve all polygons per country into one
    if admin_level == 0:
        # Group by country name and dissolve geometries
        dissolved = gdf.dissolve(by=country_name_col).reset_index()
        # Use the primary GID (shortest, e.g. "IND" not "Z01")
        primary_codes = gdf.groupby(country_name_col)["GID_0"].first().reset_index()
        dissolved = dissolved.merge(
            primary_codes, on=country_name_col, how="left", suffixes=("_drop", "")
        )
        if "GID_0_drop" in dissolved.columns:
            dissolved = dissolved.drop(columns=["GID_0_drop"])

        result = gpd.GeoDataFrame(
            {
                "admin_name": dissolved[country_name_col].values,
                "admin_code": dissolved["GID_0"].str[:3].values,
                "admin_level": admin_level,
                "country_code": dissolved["GID_0"].str[:3].values,
                "country_name": dissolved[country_name_col].values,
                "parent_name": None,
                "geometry": dissolved.geometry.values,
            },
            crs="EPSG:4326",
        )
        return result

    # Determine parent name for levels > 0
    parent_col = f"NAME_{admin_level - 1}"
    if parent_col not in gdf.columns:
        parent_col = "COUNTRY" if "COUNTRY" in gdf.columns else None

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

    # Fall back to cached GADM, then remote GADM
    # Step 1: Resolve location name to country code
    country_code = _resolve_country_code(location)

    # Step 2: Get GADM data (cache first, download if needed)
    gdf = fetch_and_cache(country_code, admin_level)

    # Step 3: If admin_level > 0, filter to matching name
    if admin_level > 0:
        name_col = f"NAME_{admin_level}"
        if name_col in gdf.columns:
            matches = gdf[gdf[name_col].str.lower() == location.lower()]
            if not matches.empty:
                return _gadm_to_standard(matches, admin_level)

        raise ValueError(
            f"Location '{location}' not found at admin level {admin_level} "
            f"in country {country_code}."
        )

    # Level 0: return the full country (may have multiple polygons for disputed areas)
    return _gadm_to_standard(gdf, admin_level)


def get_all_boundaries(
    admin_level: int,
    country_code: str | None = None,
    custom_dir: Path | None = None,
) -> gpd.GeoDataFrame:
    """Load ALL boundaries at a given admin level for a country.

    Merges custom overrides with GADM (custom takes precedence per country).
    country_code is required (global all-country loading not supported via direct download).
    """
    if not country_code:
        raise ValueError(
            "country_code is required for get_all_boundaries. "
            "Direct download does not support loading all countries at once."
        )

    # Check custom boundaries first
    if custom_dir:
        custom_dir = Path(custom_dir)
        if custom_dir.exists():
            for ext in [".gpkg", ".shp"]:
                for path in custom_dir.glob(f"{country_code}_{admin_level}{ext}"):
                    try:
                        return load_custom_boundaries(path)
                    except (ValueError, Exception):
                        continue

    # Fall back to cached GADM, then remote GADM
    gdf = fetch_and_cache(country_code, admin_level)
    return _gadm_to_standard(gdf, admin_level)
