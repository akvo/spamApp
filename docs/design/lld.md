# Low-Level Design

## Data Schemas

### Boundary GeoDataFrame Schema
Any boundary source (GADM or custom) must conform to this schema:

| Column | Type | Description |
|--------|------|-------------|
| admin_name | str | Region name |
| admin_code | str | Unique identifier (e.g., GADM GID) |
| admin_level | int | 0=country, 1=state, 2=district |
| country_code | str | ISO 3166-1 alpha-3 |
| country_name | str | Country name |
| parent_name | str or None | Parent admin region name |
| geometry | Polygon/MultiPolygon | In EPSG:4326 |

### AnalysisResult Dataclass

```python
@dataclass
class AnalysisResult:
    location_name: str
    admin_level: int
    variable: str                  # "production", "harvested_area", etc.
    total: float
    crop_data: pd.DataFrame        # [crop_code, crop_name, category, tech_level, value]
    top_crops: list[tuple[str, float]]  # [(crop_name, value), ...] sorted desc
```

### Parquet Index Schema

| Column | Type | Description |
|--------|------|-------------|
| admin_name | str | Region name |
| admin_code | str | Unique ID |
| admin_level | int | 0/1/2 |
| country_code | str | ISO alpha-3 |
| country_name | str | Country name |
| crop_code | str | 4-letter code |
| crop_name | str | Full name |
| category | str | Crop category |
| production_mt | float | Production in metric tonnes |

## GeoTIFF Filename Convention

Pattern: `spam{year}_V2r0_global_{VAR}_{CROP}_{TECH}.tif`

Inside ZIP: files are under a subdirectory matching the ZIP name (without .zip).

### Variables
| Code | Name | Unit |
|------|------|------|
| P | Production | metric tonnes |
| H | Harvested Area | hectares |
| A | Physical Area | hectares |
| Y | Yield | kg/ha |

### Technology Levels
| Code | Name |
|------|------|
| A | All systems combined (total) |
| I | Irrigated |
| R | Rainfed (combined) |

## Module APIs

### crops.py
```python
CROPS: dict[str, dict]  # code → {"name": str, "category": str}
TECH_LEVELS: dict[str, str]  # code → name
VARIABLES: dict[str, dict]  # code → {"name": str, "unit": str}

def parse_filename(filename: str) -> tuple[str, str, str]:
    """Extract (variable, crop_code, tech_level) from filename. Raises ValueError."""
```

### raster.py
```python
def get_vsi_path(zip_path: Path, crop_code: str, tech_level: str) -> str:
    """Construct /vsizip/ path for a specific crop/tech GeoTIFF."""

def compute_zonal_sum(vsi_path: str, geometry: BaseGeometry) -> float:
    """Sum pixel values within geometry. Returns 0.0 if no valid pixels."""

def compute_all_crops(zip_path: Path, geometry: BaseGeometry,
                      crops: list[str] | None = None,
                      tech_levels: list[str] | None = None) -> pd.DataFrame:
    """Process all crop/tech combos. Returns DataFrame."""

def batch_zonal_stats(vsi_path: str, gdf: gpd.GeoDataFrame) -> pd.Series:
    """Zonal sum for one raster against many polygons."""
```

### boundaries.py
```python
BOUNDARY_SCHEMA: list[str]  # required columns

def get_boundary(location: str, admin_level: int = 0,
                 custom_dir: Path | None = None) -> gpd.GeoDataFrame:
    """Resolve location to boundary. Custom overrides checked first."""

def get_all_boundaries(admin_level: int, country_code: str | None = None,
                       custom_dir: Path | None = None) -> gpd.GeoDataFrame:
    """All boundaries at a level. Merges custom + GADM."""

def load_custom_boundaries(path: Path) -> gpd.GeoDataFrame:
    """Load and validate custom boundary file."""

def standardize_boundary(gdf: gpd.GeoDataFrame, admin_level: int,
                         country_code: str, country_name: str) -> gpd.GeoDataFrame:
    """Convert arbitrary GeoDataFrame to standard schema."""
```

### analyzer.py
```python
def analyze_location(location: str, admin_level: int = 0,
                     data_dir: Path = Path("data"),
                     year: int = 2020,
                     variable: str = "production",
                     top_n: int = 10) -> AnalysisResult:
    """On-the-fly analysis for a single location."""

def rank_by_crop(crop_code: str, admin_level: int = 0,
                 index_dir: Path = Path("data/index"),
                 top_n: int = 10) -> pd.DataFrame:
    """Top N regions for a crop from pre-built index."""
```

### index.py
```python
def build_index(data_dir: Path, admin_level: int,
                output_dir: Path = Path("data/index"),
                crops: list[str] | None = None,
                country_code: str | None = None) -> Path:
    """Build/update parquet index. Returns path to index file."""
```

## Edge Cases
- Geometry outside raster bounds → return 0.0
- Nodata pixels (typically -1 or very large negatives) → exclude from sum
- CRS mismatch → boundaries.py always returns EPSG:4326
- Empty/invalid geometry → raise ValueError
- ZIP internal directory structure may vary → detect dynamically
- Custom boundary missing required columns → raise ValueError with details

## Test Plan

### Unit Tests
| Test | Input | Expected |
|------|-------|----------|
| parse_filename valid | `"spam2020_V2r0_global_P_WHEA_A.tif"` | `("P", "WHEA", "A")` |
| parse_filename invalid | `"random.tif"` | ValueError |
| compute_zonal_sum | fixture GeoTIFF + covering polygon | known sum |
| compute_zonal_sum nodata | fixture with nodata pixels | sum excluding nodata |
| compute_zonal_sum outside | polygon outside raster | 0.0 |
| standardize_boundary | GeoDataFrame + metadata | correct schema columns |
| rank_by_crop | test parquet | sorted descending |

### Integration Tests
| Test | Flow |
|------|------|
| location analysis | get_boundary → compute_all_crops → AnalysisResult |
| build + query index | build_index → rank_by_crop → sorted DataFrame |
