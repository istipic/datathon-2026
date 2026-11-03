"""Geofabrik/osmium route for OSM features (fallback when Overpass is unavailable)."""

from __future__ import annotations

from pathlib import Path

import pytest
from shapely.geometry import box

from blizu_api.ingest import osm_pbf
from blizu_api.ingest.facilities import OSM_TAGS, osm_features_to_frame

REAL_EXTRACT = Path(__file__).parents[2] / "data" / "raw" / "2026-11-03_croatia-latest.osm.pbf"
ZAGREB_BOX = box(15.77, 45.61, 16.24, 45.97)


@pytest.mark.parametrize(
    ("tags", "category"),
    [
        ({"amenity": "doctors"}, "lijecnik"),
        ({"amenity": "clinic"}, "lijecnik"),
        ({"amenity": "pharmacy"}, "ljekarna"),
        ({"amenity": "library"}, "knjiznica"),
        ({"amenity": "post_office"}, "posta"),
        ({"leisure": "park"}, "park"),
        ({"shop": "supermarket"}, "namirnice"),
        ({"shop": "convenience"}, "namirnice"),
        ({"amenity": "school"}, osm_pbf.SCHOOL_NAMES),
        ({"amenity": "bench"}, None),
        ({"shop": "bakery"}, None),
        ({"leisure": "pitch"}, None),
        ({}, None),
    ],
)
def test_category_of_matches_the_task_tag_filters(
    tags: dict[str, str], category: str | None
) -> None:
    assert osm_pbf.category_of(tags) == category


def test_tag_mapping_covers_exactly_the_overpass_filters() -> None:
    """The extract route must select the same features as the osmnx tag filters."""
    for category, filters in OSM_TAGS.items():
        for key, values in filters.items():
            for value in [values] if isinstance(values, str) else values:
                assert osm_pbf.category_of({key: value}) == category, (key, value)


@pytest.mark.skipif(not REAL_EXTRACT.exists(), reason="real Geofabrik extract not downloaded")
def test_real_extract_gives_plausible_zagreb_features() -> None:
    found = osm_pbf.extract_features(REAL_EXTRACT, ZAGREB_BOX)
    counts = {c: len(g) for c, g in found.items()}
    assert counts["ljekarna"] > 150  # Zagreb has > 150 pharmacies in OSM
    assert counts["park"] > 300
    assert counts["namirnice"] > 500
    assert counts["lijecnik"] > 100
    assert counts["posta"] > 50
    assert counts["knjiznica"] > 30
    assert counts[osm_pbf.SCHOOL_NAMES] > 100
    for gdf in found.values():
        assert gdf.crs.to_epsg() == 4326
        assert list(gdf.index.names) == ["element", "id"]
        assert set(gdf.index.get_level_values("element")) <= {"node", "way", "relation"}
        reps = gdf.geometry.representative_point()
        assert reps.x.between(15.77, 16.24).all()
        assert reps.y.between(45.61, 45.97).all()
    parks = found["park"]
    assert (parks.geometry.geom_type.isin(["Polygon", "MultiPolygon"])).all()  # assembled areas
    frame = osm_features_to_frame(parks, "park")
    assert frame["attrs"].map(lambda a: len(a.get("access_points", []))).min() == 5
    assert (frame["tier"] == "community").all()
