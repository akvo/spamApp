# CLAUDE.md

## What This Is
A Python CLI tool for analyzing MapSPAM 2020 global crop production data. Given an administrative region (country/state/district), it computes crop production statistics from GeoTIFF raster data. Supports two query modes: location→crops (on-the-fly) and crop→locations (pre-indexed).

## Essential Files
1. `docs/tasks.md` — Task list. Check before starting. Update as you go.
2. `CONTRACTS.md` — Module invariants. Never violate.
3. `CHANGELOG.md` — Recent changes. Update after each task.
4. `docs/design/hld.md` — Architecture and requirements.
5. `docs/design/lld.md` — Schema, pseudo code, test plan.

## Key Decisions
- Read GeoTIFFs from ZIP via GDAL `/vsizip/`: avoids 5GB+ disk extraction
- `rasterio.mask.mask()` with `crop=True`: reads only bounding box, not full global raster
- `pygadm` for admin boundaries: auto-downloads and caches GADM data
- Pluggable boundaries: custom shapefiles in `data/boundaries/` override GADM per country
- Parquet index for global rankings: precomputed zonal stats, incremental build
- Data organized by year (`data/{year}/`) for future time-series support
- 4 variables available: Production (P), Harvested Area (H), Physical Area (A), Yield (Y)
- "A" tech level = all systems combined (total), not just rainfed

## Project Structure
```
spamApp/
  CLAUDE.md, CONTRACTS.md, CHANGELOG.md
  Makefile, pyproject.toml, .gitignore
  docs/tasks.md, docs/design/hld.md, docs/design/lld.md
  data/2020/*.geotiff.zip          # SPAM data (4 variables)
  data/boundaries/                 # Custom boundary overrides
  data/index/                      # Generated parquet indexes
  src/crops.py                     # Crop registry, filename parser
  src/boundaries.py                # Admin boundary loading
  src/raster.py                    # GeoTIFF reading + zonal stats
  src/index.py                     # Build parquet index
  src/analyzer.py                  # Orchestrator (boundaries + raster)
  src/formatter.py                 # Rich output, CSV/JSON export
  src/cli.py                       # Typer CLI
  tests/                           # pytest tests
```

## Commands
```
make test          # Run pytest
make lint          # Run ruff check
make format        # Run ruff format
make check         # lint + test (gate before commit)
```

## Process Rules
- TDD: write failing tests first, then implement
- Never commit if `make check` fails
- Update CHANGELOG.md after each completed task
- Update CONTRACTS.md when new invariants are discovered
- Check docs/tasks.md at session start for current task
- Only make changes directly requested — no scope creep

## Stable Interfaces
(will be added as modules are implemented)
