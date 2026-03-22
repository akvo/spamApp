# Task List

## Core Pipeline

| Task | Status | Layer | Deps | Description |
|------|--------|-------|------|-------------|
| T1 | DONE | 0 | — | `crops.py`: crop registry with categories + filename parser |
| T2 | DONE | 0 | — | Test fixtures: tiny GeoTIFF + test polygon in conftest.py |
| T3 | DONE | 1 | T1,T2 | `raster.py`: read GeoTIFF from ZIP, compute zonal sum |
| T4 | DONE | 1 | T2 | `boundaries.py`: GADM lookup + custom boundary loading |
| T5 | DONE | 2 | T3,T4 | `analyzer.py`: orchestrate on-the-fly analysis |
| T6 | DONE | 2 | T3,T4 | `index.py`: build parquet index (incremental, single-crop) |
| T7 | DONE | 2 | T6 | `analyzer.py`: rank_by_crop from parquet index |
| T8 | DONE | 3 | T5,T7 | `formatter.py`: Rich table output, CSV/JSON export |
| T9 | DONE | 3 | T5,T7,T8 | `cli.py`: Typer CLI with all commands |
| T10 | TODO | 4 | T9 | Integration tests: end-to-end workflows |

## Extended Features (inspired by mapspamc)

| Task | Status | Layer | Deps | Description |
|------|--------|-------|------|-------------|
| T11 | TODO | 2 | T3,T5 | Multi-variable analysis: support all 4 variables (P, H, A, Y) |
| T12 | TODO | 3 | T5 | Validation: aggregate sub-regions and compare to parent total |
| T13 | TODO | 3 | T3,T4 | Interactive map visualization: folium/leaflet choropleth maps |
| T14 | TODO | 3 | T3 | Raster clipping & export: clip GeoTIFF to admin boundary |
| T15 | TODO | 2 | T1 | Crop taxonomy: category groupings for filtering/grouping |

## Task Details

### T1: crops.py
- **Tests**: parse_filename extracts crop/tech, CROPS has all 46 entries, unknown code raises ValueError, category groupings correct
- **Implement**: CROPS dict with name+category, TECH_LEVELS, VARIABLES, parse_filename()
- **Verify**: `make check`

### T2: Test fixtures
- **Implement**: conftest.py with tiny GeoTIFF fixture (10x10, known values, EPSG:4326), test polygon (shapely box), test ZIP containing the GeoTIFF
- **Verify**: `make check`

### T3: raster.py
- **Tests**: compute_production returns expected sum; handles nodata; handles geometry outside bounds; reads from ZIP
- **Implement**: compute_production(), compute_all_production(), batch_zonal_stats()
- **Verify**: `make check`

### T4: boundaries.py
- **Tests**: standardize_boundary produces correct schema; load_custom validates; get_boundary returns EPSG:4326
- **Implement**: schema validation, GADM lookup, custom override loading
- **Verify**: `make check`

### T5–T15: See plan file for details
