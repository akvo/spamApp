"""Rebuild pre-built boundary and lookup files.

Called after adding new countries to keep all derived files in sync.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import MultiPolygon

from src.boundaries import (
    DEFAULT_CACHE_PATH,
    _read_cache,
    list_cached_countries,
)


def _clean_geometry(geom, tolerance=0.2, min_area=0.01):
    """Simplify geometry and remove tiny island polygons."""
    geom = geom.simplify(tolerance, preserve_topology=True)
    if geom.geom_type == "MultiPolygon":
        big = [p for p in geom.geoms if p.area > min_area]
        if not big:
            big = [max(geom.geoms, key=lambda p: p.area)]
        geom = MultiPolygon(big) if len(big) > 1 else big[0]
    return geom


def rebuild_world_l0(
    cache_path: Path = DEFAULT_CACHE_PATH,
    output_path: Path = Path("data/boundaries/world_l0.gpkg"),
):
    """Rebuild simplified world country boundaries."""
    entries = list_cached_countries(cache_path)
    level0_codes = sorted(set(e["code"] for e in entries if e["level"] == 0))

    parts = []
    for code in level0_codes:
        gdf = _read_cache(code, 0, cache_path)
        if gdf is None:
            continue
        name_col = "COUNTRY" if "COUNTRY" in gdf.columns else "NAME_0"
        g = gdf[[name_col, "geometry"]].copy()
        g = g.rename(columns={name_col: "name"})
        g["code"] = code
        g = g.dissolve(by="code").reset_index()
        g["name"] = gdf[name_col].iloc[0]
        parts.append(g[["name", "code", "geometry"]])

    if not parts:
        return

    merged = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs="EPSG:4326"
    )
    merged["geometry"] = merged.geometry.apply(
        lambda g: _clean_geometry(g, tolerance=0.2, min_area=0.01)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_file(output_path, driver="GPKG")
    print(f"  world_l0.gpkg: {len(merged)} countries")


def rebuild_world_l1(
    cache_path: Path = DEFAULT_CACHE_PATH,
    output_path: Path = Path("data/boundaries/world_l1.gpkg"),
):
    """Rebuild simplified world state boundaries."""
    entries = list_cached_countries(cache_path)
    level1_codes = sorted(set(e["code"] for e in entries if e["level"] == 1))

    parts = []
    for code in level1_codes:
        gdf = _read_cache(code, 1, cache_path)
        if gdf is None or "NAME_1" not in gdf.columns:
            continue
        g = gdf[["NAME_1", "geometry"]].copy()
        g = g.rename(columns={"NAME_1": "name"})
        g["code"] = code
        name_col = "COUNTRY" if "COUNTRY" in gdf.columns else "NAME_0"
        g["country"] = gdf[name_col].iloc[0] if name_col in gdf.columns else code
        parts.append(g[["name", "code", "country", "geometry"]])

    if not parts:
        return

    merged = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs="EPSG:4326"
    )
    merged["geometry"] = merged.geometry.apply(
        lambda g: _clean_geometry(g, tolerance=0.1, min_area=0.005)
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    merged.to_file(output_path, driver="GPKG")
    print(f"  world_l1.gpkg: {len(merged)} states")


def rebuild_districts_lookup(
    cache_path: Path = DEFAULT_CACHE_PATH,
    output_path: Path = Path("data/boundaries/districts_lookup.parquet"),
):
    """Rebuild district name lookup (no geometries)."""
    entries = list_cached_countries(cache_path)
    level2_codes = sorted(set(e["code"] for e in entries if e["level"] == 2))

    rows = []
    for code in level2_codes:
        gdf = _read_cache(code, 2, cache_path)
        if gdf is None or "NAME_1" not in gdf.columns or "NAME_2" not in gdf.columns:
            continue
        for _, r in gdf[["NAME_1", "NAME_2"]].iterrows():
            rows.append({"code": code, "state": r["NAME_1"], "district": r["NAME_2"]})

    if not rows:
        return

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(output_path, index=False)
    print(f"  districts_lookup.parquet: {len(df):,} districts")


def rebuild_all(cache_path: Path = DEFAULT_CACHE_PATH):
    """Rebuild all pre-built files from the GADM cache."""
    print("Rebuilding pre-built files...")
    rebuild_world_l0(cache_path)
    rebuild_world_l1(cache_path)
    rebuild_districts_lookup(cache_path)
    print("Done.")
