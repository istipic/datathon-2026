from __future__ import annotations

import geopandas as gpd
import numpy as np
import pytest
from shapely.geometry import Point

from opendata_core import geo


def test_constants() -> None:
    assert geo.WGS84 == 4326
    assert geo.HTRS96_TM == 3765


def test_to_metric_projects_zagreb_to_htrs96() -> None:
    gdf = gpd.GeoDataFrame(geometry=[Point(15.9771683, 45.8130887)], crs=geo.WGS84)
    out = geo.to_metric(gdf)
    assert out.crs.to_epsg() == 3765
    x, y = out.geometry.iloc[0].x, out.geometry.iloc[0].y
    # Zagreb centre in HTRS96/TM: easting ~ 4.6e5, northing ~ 5.07e6
    assert 450_000 < x < 470_000
    assert 5_060_000 < y < 5_080_000


def test_to_metric_requires_crs() -> None:
    with pytest.raises(ValueError, match="CRS"):
        geo.to_metric(gpd.GeoDataFrame(geometry=[Point(0, 0)]))


@pytest.mark.parametrize(
    ("lon", "lat", "expected"),
    [
        (15.98, 45.81, True),  # Zagreb
        (18.09, 42.65, True),  # Dubrovnik
        (13.0, 42.2, True),  # corner, inclusive
        (19.5, 46.6, True),
        (12.9, 45.0, False),
        (16.0, 47.0, False),
        (2.35, 48.85, False),  # Paris
        (45.81, 15.98, False),  # swapped lat/lon
    ],
)
def test_in_croatia(lon: float, lat: float, expected: bool) -> None:
    assert geo.in_croatia(lon, lat) is expected


def test_bbox_of_points() -> None:
    assert geo.bbox_of_points([(16.0, 45.0), (15.0, 46.0), (17.0, 44.5)]) == (
        15.0,
        44.5,
        17.0,
        46.0,
    )
    with pytest.raises(ValueError, match="no points"):
        geo.bbox_of_points([])


def test_bbox_around_is_about_radius() -> None:
    minx, miny, maxx, maxy = geo.bbox_around(16.0, 45.0, 1000)
    assert geo.bbox_contains((minx, miny, maxx, maxy), 16.0, 45.0)
    assert geo.haversine_m(16.0, 45.0, maxx, 45.0) == pytest.approx(1000, abs=1)
    assert geo.haversine_m(16.0, 45.0, 16.0, maxy) == pytest.approx(1000, abs=1)
    assert geo.haversine_m(16.0, 45.0, minx, 45.0) == pytest.approx(1000, abs=1)
    assert not geo.bbox_contains((minx, miny, maxx, maxy), 16.1, 45.0)
    with pytest.raises(ValueError, match="radius_m"):
        geo.bbox_around(16.0, 45.0, -1)


def test_snap_points_to_nodes() -> None:
    nodes = np.array([[0.0, 0.0], [100.0, 0.0], [0.0, 100.0]])
    points = np.array([[1.0, 1.0], [99.0, 3.0], [500.0, 500.0], [0.0, 90.0]])
    idx, dist = geo.snap_points_to_nodes(points, nodes, max_dist_m=20)
    assert idx.tolist() == [0, 1, -1, 2]
    assert dist[0] == pytest.approx(np.hypot(1, 1))
    assert dist[1] == pytest.approx(np.hypot(1, 3))
    assert np.isinf(dist[2])
    assert dist[3] == pytest.approx(10.0)


def test_snap_limit_is_inclusive_and_empty_inputs() -> None:
    idx, dist = geo.snap_points_to_nodes(np.array([[10.0, 0.0]]), np.array([[0.0, 0.0]]), 10.0)
    assert idx.tolist() == [0]
    assert dist.tolist() == [10.0]
    idx, dist = geo.snap_points_to_nodes(np.array([[1.0, 1.0]]), np.empty((0, 2)), 10.0)
    assert idx.tolist() == [-1]
    assert np.isinf(dist[0])
    idx, dist = geo.snap_points_to_nodes(np.empty((0, 2)), np.array([[0.0, 0.0]]), 10.0)
    assert len(idx) == 0
