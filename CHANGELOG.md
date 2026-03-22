# CHANGELOG

## 2026-03-22
- T1: crops.py — 46 crop codes with categories, tech levels, variables, parse_filename()
- T2: Test fixtures — tiny GeoTIFF, test polygons, test ZIP in conftest.py
- T3: raster.py — compute_zonal_sum via /vsizip/, compute_all_crops, batch_zonal_stats
- T4: boundaries.py — pluggable boundary system (GADM + custom overrides), schema validation
- T5: analyzer.py — analyze_location() for on-the-fly location→crops queries
- T6: index.py — build_index() with incremental, single-crop, single-country support
- T7: analyzer.py — rank_by_crop() from pre-built parquet index
- T8: formatter.py — Rich tables, CSV/JSON export
- T9: cli.py — Typer CLI: location, ranking, crops, build-index, prep-boundary
- Gotcha: Shapely 2.1.2 removed BaseGeometry — use `from shapely import Geometry` instead
- Gotcha: Makefile must point to conda geo env Python, not system Python
- Project scaffolding: CLAUDE.md, CONTRACTS.md, CHANGELOG.md, HLD, LLD, tasks, Makefile
