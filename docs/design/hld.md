# High-Level Design

## Problem Statement
Researchers and analysts need to extract crop production statistics for specific administrative regions from MapSPAM 2020 global raster data. Currently this requires GIS expertise and manual processing. This tool automates the workflow.

## Requirements

### Functional
1. **Location → Crops**: Given an admin region (country/state/district), compute production statistics for all crops
2. **Crop → Locations**: Given a crop, rank all regions globally by production
3. **Pluggable boundaries**: Support custom admin boundary files alongside GADM
4. **Multi-variable**: Support Production, Harvested Area, Physical Area, Yield
5. **Incremental indexing**: Build global index one crop/country at a time

### Non-Functional
- Handle 5GB+ raster data without full extraction
- Single-location queries complete in <2 minutes
- Global rankings are instant after index is built
- CLI-first, Streamlit UI deferred

## Architecture

### Two-Mode Design

```
Mode 1: On-the-fly (location → crops)
  User input → boundaries.py → geometry
                                  ↓
  data/2020/*.zip → raster.py → mask + sum → analyzer.py → formatter.py → output

Mode 2: Pre-indexed (crop → locations)
  [build-index] boundaries.py → all geometries
                                     ↓
  data/2020/*.zip → raster.py → batch zonal stats → index.py → data/index/*.parquet

  [query] data/index/*.parquet → analyzer.py → formatter.py → output
```

### Layer Architecture
```
Layer 0: crops.py (pure data, no deps)
Layer 1: raster.py, boundaries.py (I/O, no cross-deps)
Layer 2: analyzer.py, index.py (combines L0 + L1)
Layer 3: formatter.py, cli.py (presentation)
Layer 4: integration tests
```

## Key Decisions

| Decision | Rationale |
|----------|-----------|
| Read from ZIP via `/vsizip/` | Avoids 5GB+ disk extraction |
| `rasterio.mask.mask(crop=True)` | Reads only bounding box, not full 37MB raster |
| pygadm for boundaries | Auto-downloads/caches GADM, simple API |
| Custom boundary overrides | GADM shapes aren't always best; users can substitute |
| Parquet for global index | Compact, fast pandas queries, no DB server |
| Year-organized data dirs | Future time-series support |

## Out of Scope (for now)
- Streamlit web UI
- Time-series analysis across years
- GAMS optimization / crop allocation modeling (that's what mapspamc does)
- Database backend
