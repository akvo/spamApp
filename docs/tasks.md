# Task List

## Core Pipeline

| Task | Status | Description |
|------|--------|-------------|
| T1 | DONE | `crops.py`: 46 crop codes with names, categories, tech levels, variables, `parse_filename()` |
| T2 | DONE | Test fixtures: tiny GeoTIFF (10x10), test polygons, test ZIPs in `conftest.py` |
| T3 | DONE | `raster.py`: `compute_zonal_sum` via /vsizip/, `compute_all_crops`, `batch_zonal_stats_gdf` |
| T4 | DONE | `boundaries.py`: GADM download + local GeoPackage cache + custom boundary overrides |
| T5 | DONE | `analyzer.py`: `analyze_location()` on-the-fly with index-first lookup |
| T6 | DONE | `index.py`: `build_index()` with batch zonal stats, incremental, multi-variable, parallel |
| T7 | DONE | `analyzer.py`: `rank_by_crop()` from parquet index with variable/country/parent filters |
| T8 | DONE | `formatter.py`: Rich table output, CSV/JSON export, yield-aware formatting |
| T9 | DONE | `cli.py`: Typer CLI — location, ranking, crops, build-index, prep-boundary, init-boundaries |
| T10 | TODO | Integration tests: end-to-end workflows with test fixtures |

## Extended Features

| Task | Status | Description |
|------|--------|-------------|
| T11 | DONE | Multi-variable: all 4 variables (P, H, A, Y) with weighted avg yield |
| T12 | TODO | Validation: aggregate sub-regions and compare to parent total |
| T13 | DONE | Choropleth maps: folium maps in Streamlit with quantile coloring + legend |
| T14 | TODO | Raster clipping & export: clip GeoTIFF to admin boundary, save as new file |
| T15 | DONE | Crop taxonomy: category groupings, category breakdown chart in app |

## Streamlit App

| Task | Status | Description |
|------|--------|-------------|
| T16 | DONE | Streamlit dashboard: Location Analysis tab with stacked I/R bar charts |
| T17 | DONE | Crop Rankings tab with bar chart, choropleth map, data table |
| T18 | DONE | Sidebar: cascading Country → State → District dropdowns from GADM cache |
| T19 | DONE | Green theme CSS, responsive layout |
| T20 | DONE | Performance: `@st.cache_data` on analysis, `@st.cache_resource` on boundaries |

## Data Infrastructure

| Task | Status | Description |
|------|--------|-------------|
| T21 | DONE | GADM boundary cache: `init-boundaries` downloads 45 countries to GeoPackage |
| T22 | DONE | Level 0 + 1 parquet indexes: all 45 countries, 46 crops, 4 variables |
| T23 | DONE | Level 2 parquet index: all 45 countries (~30K districts), batch + parallel build |
| T24 | DONE | Extracted GeoTIFFs: prefer disk files over /vsizip/ for faster reads |

## Remaining / Future

| Task | Status | Description |
|------|--------|-------------|
| T10 | TODO | Integration tests |
| T12 | TODO | Cross-level validation (sum of children ≈ parent total) |
| T14 | TODO | Raster clip & export |
| T25 | TODO | Global Comparisons: new tab showing global distribution of a crop across all variables at L0/L1 |
| T26 | TODO | Rebuild indexes with I/R tech levels: `build-index --level 0 --parallel 8 --tech-levels A,I,R` (3x data) |
| T27 | TODO | Time-series support (add more years to data/{year}/) |
| T28 | TODO | Fix "Ug and a" display name bug in `_fix_gadm_name` |
