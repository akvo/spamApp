# CONTRACTS.md

## Module: crops.py
- Pure data module. No I/O, no imports from other src modules.
- `CROPS` dict must contain all 46 crop codes. Never remove an entry.
- `parse_filename()` always returns `(crop_code, tech_level)` tuple, never None. Raises ValueError for unrecognized filenames.
- Reason: downstream modules rely on crop codes being valid and complete.

## Module: raster.py
- NEVER imports boundaries.py. Reason: separation of raster processing from boundary resolution.
- `compute_production()` returns float, never None. Returns 0.0 for geometries with no data pixels.
- Must handle nodata pixels correctly (exclude from sums).
- Must use `crop=True` in rasterio.mask to avoid reading full global rasters.
- Reason: performance and correctness — full raster reads are 37MB each.

## Module: boundaries.py
- NEVER imports raster.py. Reason: separation of boundary resolution from raster processing.
- All returned GeoDataFrames MUST be in EPSG:4326. Reason: SPAM GeoTIFFs are in EPSG:4326.
- `get_boundary()` returns GeoDataFrame, never None. Raises ValueError for unknown locations.
- Custom boundaries checked before GADM. Reason: user overrides take precedence.

## Module: analyzer.py
- The ONLY module that combines boundaries + raster. Reason: single integration point prevents coupling.
- `analyze_location()` returns AnalysisResult dataclass, never None.
- `rank_by_crop()` returns DataFrame sorted descending by production.

## Module: index.py
- Only writes to `data/index/`. NEVER modifies source data in `data/{year}/`.
- Reason: source GeoTIFFs are read-only inputs.

## Module: formatter.py
- No side effects except printing to stdout or writing to explicitly specified output files.
- NEVER modifies any data structures passed to it.
- Reason: formatter is a pure presentation layer.

## Module: cli.py
- Thin wrapper over analyzer.py and formatter.py. No business logic.
- Reason: CLI should be replaceable (e.g., by Streamlit) without duplicating logic.

## General
- No module outside `src/` imports from `tests/`.
- Regression tests must never be deleted.
- All data paths use pathlib.Path, not string concatenation.
