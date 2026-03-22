"""Shared test fixtures: tiny GeoTIFF, test polygon, test ZIP."""

import zipfile
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import box


@pytest.fixture
def tmp_data_dir(tmp_path):
    """Base temp directory for test data."""
    return tmp_path


@pytest.fixture
def tiny_geotiff(tmp_data_dir):
    """Create a 10x10 GeoTIFF with known values in EPSG:4326.

    Covers lon [70, 80], lat [20, 30] (roughly western India).
    Pixel values: row * 10 + col (0..99), so total sum = 4950.
    Nodata value: -1 (no nodata pixels in this fixture).
    """
    path = tmp_data_dir / "test_raster.tif"
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    transform = from_bounds(70.0, 20.0, 80.0, 30.0, 10, 10)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-1,
    ) as dst:
        dst.write(data, 1)

    return path


@pytest.fixture
def tiny_geotiff_with_nodata(tmp_data_dir):
    """10x10 GeoTIFF with some nodata pixels.

    Same extent as tiny_geotiff. Pixels at positions (0,0), (0,1), (0,2)
    are set to nodata (-1). Valid sum = 4950 - 0 - 1 - 2 = 4947.
    """
    path = tmp_data_dir / "test_raster_nodata.tif"
    data = np.arange(100, dtype=np.float32).reshape(10, 10)
    data[0, 0] = -1
    data[0, 1] = -1
    data[0, 2] = -1
    transform = from_bounds(70.0, 20.0, 80.0, 30.0, 10, 10)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-1,
    ) as dst:
        dst.write(data, 1)

    return path


@pytest.fixture
def covering_polygon():
    """Polygon covering the full extent of the tiny GeoTIFF (lon 70-80, lat 20-30)."""
    return box(70.0, 20.0, 80.0, 30.0)


@pytest.fixture
def partial_polygon():
    """Polygon covering the left half of the raster (lon 70-75, lat 20-30).

    Covers columns 0-4 (5 columns, all 10 rows).
    Expected sum of column indices 0-4 across all rows:
    sum of (row*10 + col) for row in 0..9, col in 0..4
    = sum(row*10 for row in 0..9) * 5 + sum(col for col in 0..4) * 10
    Actually: sum = sum over row 0..9, col 0..4 of (row*10 + col)
    = 5 * sum(row*10 for row 0..9) + 10 * sum(col for col 0..4)
    = 5 * 10 * 45 + 10 * 10 = 2250 + 100 = 2350
    Wait, let me compute properly:
    sum = sum_{r=0}^{9} sum_{c=0}^{4} (10r + c)
        = sum_{r=0}^{9} (5*10r + 0+1+2+3+4)
        = sum_{r=0}^{9} (50r + 10)
        = 50*45 + 10*10
        = 2250 + 100
        = 2350
    """
    return box(70.0, 20.0, 75.0, 30.0)


@pytest.fixture
def outside_polygon():
    """Polygon completely outside the raster extent."""
    return box(0.0, 0.0, 10.0, 10.0)


@pytest.fixture
def test_zip(tmp_data_dir, tiny_geotiff):
    """Create a ZIP mimicking SPAM structure with two crop GeoTIFFs.

    Contains:
      spam2020V2r0_global_production/spam2020_V2r0_global_P_WHEA_A.tif
      spam2020V2r0_global_production/spam2020_V2r0_global_P_RICE_A.tif
    Both files are copies of tiny_geotiff.
    """
    zip_path = tmp_data_dir / "spam2020V2r0_global_production.geotiff.zip"
    subdir = "spam2020V2r0_global_production"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(
            tiny_geotiff,
            f"{subdir}/spam2020_V2r0_global_P_WHEA_A.tif",
        )
        zf.write(
            tiny_geotiff,
            f"{subdir}/spam2020_V2r0_global_P_RICE_A.tif",
        )

    return zip_path


@pytest.fixture
def test_data_dir(tmp_data_dir, test_zip):
    """Create a data directory structure mimicking the real layout.

    data/2020/spam2020V2r0_global_production.geotiff.zip
    """
    year_dir = tmp_data_dir / "data" / "2020"
    year_dir.mkdir(parents=True)

    import shutil

    shutil.copy(test_zip, year_dir / test_zip.name)

    return tmp_data_dir / "data"


@pytest.fixture
def tiny_geotiff_weights(tmp_data_dir):
    """10x10 GeoTIFF with weight values (all 2.0).

    Same extent as tiny_geotiff. Used as harvested area weights for yield tests.
    Weighted mean of tiny_geotiff values = sum(values * 2) / sum(2s)
      = sum(values) / count = 4950 / 100 = 49.5
    """
    path = tmp_data_dir / "test_weights.tif"
    data = np.full((10, 10), 2.0, dtype=np.float32)
    transform = from_bounds(70.0, 20.0, 80.0, 30.0, 10, 10)

    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=10,
        width=10,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
        nodata=-1,
    ) as dst:
        dst.write(data, 1)

    return path


@pytest.fixture
def test_zip_yield(tmp_data_dir, tiny_geotiff):
    """ZIP mimicking yield data structure."""
    zip_path = tmp_data_dir / "spam2020V2r0_global_yield.geotiff.zip"
    subdir = "spam2020V2r0_global_yield"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(tiny_geotiff, f"{subdir}/spam2020_V2r0_global_Y_WHEA_A.tif")
        zf.write(tiny_geotiff, f"{subdir}/spam2020_V2r0_global_Y_RICE_A.tif")

    return zip_path


@pytest.fixture
def test_zip_harvested_area(tmp_data_dir, tiny_geotiff_weights):
    """ZIP mimicking harvested area data structure (uniform weights)."""
    zip_path = tmp_data_dir / "spam2020V2r0_global_harvested_area.geotiff.zip"
    subdir = "spam2020V2r0_global_harvested_area"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.write(tiny_geotiff_weights, f"{subdir}/spam2020_V2r0_global_H_WHEA_A.tif")
        zf.write(tiny_geotiff_weights, f"{subdir}/spam2020_V2r0_global_H_RICE_A.tif")

    return zip_path


@pytest.fixture
def test_data_dir_multi(tmp_data_dir, test_zip, test_zip_yield, test_zip_harvested_area):
    """Data directory with production, yield, and harvested area ZIPs."""
    year_dir = tmp_data_dir / "data" / "2020"
    year_dir.mkdir(parents=True, exist_ok=True)

    import shutil

    for zp in [test_zip, test_zip_yield, test_zip_harvested_area]:
        shutil.copy(zp, year_dir / zp.name)

    return tmp_data_dir / "data"


def test_fixtures_sanity(tiny_geotiff, covering_polygon, test_zip):
    """Sanity check that fixtures are created correctly."""
    assert Path(tiny_geotiff).exists()
    assert covering_polygon.is_valid
    assert Path(test_zip).exists()

    with rasterio.open(tiny_geotiff) as src:
        assert src.crs.to_epsg() == 4326
        assert src.width == 10
        assert src.height == 10
        data = src.read(1)
        assert data.shape == (10, 10)
        assert np.sum(data) == 4950.0
