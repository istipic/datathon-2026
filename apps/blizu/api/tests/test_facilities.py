"""Facility parsing and dedupe on REAL excerpts (recorded 2026-11-03)."""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from pyproj import Geod
from shapely.geometry import Point, Polygon

from blizu_api.ingest import facilities as fac

FIX = Path(__file__).parent / "fixtures"
GEOD = Geod(ellps="WGS84")


@pytest.fixture(scope="module")
def vrtici() -> pd.DataFrame:
    text = (FIX / "zg-vrtici" / "2026-11-03_vrtici_sample.csv").read_text(encoding="utf-8")
    return fac.parse_vrtici(text)


@pytest.fixture(scope="module")
def skole() -> pd.DataFrame:
    path = FIX / "zg-skole" / "2026-11-03_wfs_sample.geojson"
    return fac.parse_skole(json.loads(path.read_text(encoding="utf-8")))


def test_vrtici_parse_columns_and_exclusions(vrtici: pd.DataFrame) -> None:
    assert list(vrtici.columns) == fac.COLUMNS
    assert (vrtici["category"] == "vrtic").all()
    assert (vrtici["tier"] == "official").all()
    assert (vrtici["source_id"] == "zg-vrtici").all()
    types = {a["vr_vrtica"] for a in vrtici["attrs"]}
    assert not types & fac.EXCLUDED_KINDERGARTEN_TYPES  # hospital / special institutions removed
    assert len(vrtici) == 20  # 22 real rows, 2 hospital/special rows excluded
    assert vrtici["lon"].between(15.8, 16.2).all()
    assert vrtici["lat"].between(45.6, 45.95).all()
    first = vrtici.iloc[0]
    assert first["name"] == "BAJKA"
    assert first["address"] == "Zorkovačka ulica 8"
    assert first["lon"] == pytest.approx(15.9452453800001)
    assert first["lat"] == pytest.approx(45.801658172)


def test_vrtici_rejects_projected_coordinates() -> None:
    bad = "X,Y,OBJECTID,naziv,adresa,vr_vrtica\n458000,5072000,1,TEST,Ulica 1,Gradski vrtić\n"
    with pytest.raises(ValueError, match="WGS84"):
        fac.parse_vrtici(bad)


def test_skole_only_primary_education(skole: pd.DataFrame) -> None:
    assert len(skole) == 3  # 9 real features, 3 per service type: only primaryEducation kept
    assert (skole["category"] == "skola").all()
    assert skole["name"].isna().all()  # the source has no names
    assert skole["address"].isna().all()
    assert skole["source_record_id"].notna().all()
    assert skole["lon"].between(15.8, 16.2).all()
    assert all(a["service_type"] == "primaryEducation" for a in skole["attrs"])


def _offset(df: pd.DataFrame, metres: float, bearing: float = 90.0) -> pd.DataFrame:
    """Copy of ``df`` with every point moved ``metres`` along ``bearing`` (test geometry helper)."""
    out = df.copy()
    moved = [
        GEOD.fwd(lon, lat, bearing, metres)[:2]
        for lon, lat in zip(df["lon"], df["lat"], strict=True)
    ]
    out["lon"] = [m[0] for m in moved]
    out["lat"] = [m[1] for m in moved]
    return out


def test_dedupe_drops_osm_within_50m_keeps_official(vrtici: pd.DataFrame) -> None:
    near = _offset(vrtici.head(5), 30)
    far = _offset(vrtici.iloc[5:8], 120)
    for d in (near, far):
        d["tier"] = "community"
        d["source_id"] = "osm-zagreb"
    frame = pd.concat([vrtici, near, far], ignore_index=True)
    out, dropped = fac.dedupe_official_vs_osm(frame)
    assert dropped == 5  # only the 30 m copies
    assert (out["tier"] == "official").sum() == len(vrtici)  # official rows are never dropped
    assert (out["tier"] == "community").sum() == 3


def test_dedupe_is_per_category(vrtici: pd.DataFrame) -> None:
    other = _offset(vrtici.head(3), 10)
    other["category"] = "ljekarna"
    other["tier"] = "community"
    other["source_id"] = "osm-zagreb"
    out, dropped = fac.dedupe_official_vs_osm(pd.concat([vrtici, other], ignore_index=True))
    assert dropped == 0
    assert len(out) == len(vrtici) + 3  # a pharmacy next to a kindergarten stays


def test_dedupe_without_official_rows_keeps_everything(vrtici: pd.DataFrame) -> None:
    osm = vrtici.head(4).copy()
    osm["tier"] = "community"
    osm["source_id"] = "osm-zagreb"
    out, dropped = fac.dedupe_official_vs_osm(osm)
    assert dropped == 0
    assert len(out) == 4


def test_name_hints_fill_nameless_official_records(skole: pd.DataFrame) -> None:
    hints = _offset(skole, 20)
    hints["name"] = ["OŠ Prva", "OŠ Druga", "OŠ Treća"]
    hints.loc[2, "lon"] += 0.01  # one hint is ~700 m away: too far
    named, n = fac.attach_name_hints(skole, hints)
    assert n == 2
    assert list(named["name"][:2]) == ["OŠ Prva", "OŠ Druga"]
    assert pd.isna(named["name"].iloc[2])
    assert named["attrs"].iloc[0]["name_source"] == "osm"
    assert skole["name"].isna().all()  # input not mutated


def test_name_hints_do_not_overwrite_existing_names(vrtici: pd.DataFrame) -> None:
    hints = _offset(vrtici.head(2), 5)
    hints["name"] = ["X", "Y"]
    named, n = fac.attach_name_hints(vrtici.head(2), hints)
    assert n == 0
    assert list(named["name"]) == list(vrtici["name"].head(2))


def test_park_access_points_centroid_plus_boundary() -> None:
    park = Polygon([(0, 0), (400, 0), (400, 200), (0, 200)])
    pts = fac.park_access_points(park)
    assert len(pts) == 5  # representative point + 4 boundary points
    assert park.contains(Point(pts[0]))
    for x, y in pts[1:]:
        assert park.boundary.distance(Point(x, y)) < 1e-6
    assert len({(round(x), round(y)) for x, y in pts}) == 5  # all distinct


def test_osm_frame_empty_input() -> None:
    assert fac.osm_features_to_frame(gpd.GeoDataFrame(geometry=[], crs=4326), "park").empty


def test_osm_frame_conversion_points_and_park_polygons() -> None:
    # conversion mechanics only: a lon/lat polygon of roughly park size near the Zagreb centre
    poly = Polygon([(15.986, 45.8085), (15.9905, 45.8085), (15.9905, 45.8105), (15.986, 45.8105)])
    idx = pd.MultiIndex.from_tuples([("way", 1), ("node", 2)], names=["element", "id"])
    gdf = gpd.GeoDataFrame(
        {
            "name": ["Zrinjevac", None],
            "leisure": ["park", None],
            "addr:street": [None, "Ilica"],
            "addr:housenumber": [None, "5"],
        },
        geometry=[poly, Point(15.97, 45.81)],
        index=idx,
        crs=4326,
    )
    park = fac.osm_features_to_frame(gdf.iloc[[0]], "park").iloc[0]
    assert park["name"] == "Zrinjevac"
    assert park["tier"] == "community"
    assert park["source_id"] == "osm-zagreb"
    assert park["source_record_id"] == "way/1"
    assert len(park["attrs"]["access_points"]) == 5
    assert park["attrs"]["area_m2"] > 10_000
    assert 15.986 < park["lon"] < 15.9905
    post = fac.osm_features_to_frame(gdf.iloc[[1]], "posta").iloc[0]
    assert post["address"] == "Ilica 5"
    assert "access_points" not in post["attrs"]


def test_facility_records_turn_missing_text_into_null_not_the_string_nan(
    skole: pd.DataFrame,
) -> None:
    """Real unnamed schools (the INSPIRE source has no names): pandas 3 makes them NaN."""
    frame = pd.concat(
        [
            skole,
            fac.parse_vrtici(
                (FIX / "zg-vrtici" / "2026-11-03_vrtici_sample.csv").read_text(encoding="utf-8")
            ).head(2),
        ],
        ignore_index=True,
    )
    assert frame["name"].isna().sum() == 3  # the three schools have no name
    records = fac.facility_records(frame)
    assert [r["name"] for r in records[:3]] == [None, None, None]
    assert all(r["address"] is None for r in records[:3])
    assert records[3]["name"] == "BAJKA"
    assert records[3]["geom"].startswith("SRID=4326;POINT(15.94")
    assert all(r["name"] != "NaN" and r["address"] != "NaN" for r in records)
    assert all(r["source_record_id"] not in (None, "NaN") for r in records)


def test_school_hints_never_name_a_primary_school_after_a_secondary_one(
    skole: pd.DataFrame,
) -> None:
    """Real case: "IV. gimnazija Zagreb" stands next to the primary school record."""
    one = skole.head(1).reset_index(drop=True)
    gym = _offset(one, 10)
    gym["name"] = "IV. gimnazija Zagreb"
    os_ = _offset(one, 35)
    os_["name"] = "Osnovna škola Hugo Kon"
    hints = pd.concat([gym, os_], ignore_index=True)
    # plain nearest-hint matching would pick the gymnasium (10 m)
    assert fac.attach_name_hints(one, hints)[0]["name"].iloc[0] == "IV. gimnazija Zagreb"
    named, n = fac.attach_name_hints(
        one, hints, exclude=fac.SECONDARY_SCHOOL, prefer=fac.PRIMARY_SCHOOL
    )
    assert n == 1
    assert named["name"].iloc[0] == "Osnovna škola Hugo Kon"
    assert named["attrs"].iloc[0]["name_hint_distance_m"] == pytest.approx(35, abs=2)
    # only a secondary school nearby -> the record stays unnamed (honest, not wrong)
    named, n = fac.attach_name_hints(
        one, gym, exclude=fac.SECONDARY_SCHOOL, prefer=fac.PRIMARY_SCHOOL
    )
    assert n == 0
    assert pd.isna(named["name"].iloc[0])


@pytest.mark.parametrize(
    ("name", "secondary", "primary"),
    [
        ("IV. gimnazija Zagreb", True, False),
        ("Tehnička škola Ruđera Boškovića", True, False),
        ("Srednja strukovna škola", True, False),
        ("Osnovna škola Hugo Kon", False, True),
        ("OŠ Augusta Šenoe", False, True),
        ("O.Š. Petra Zrinskog", False, True),
        (
            "Osnovna glazbena škola",
            True,
            True,
        ),  # a music school: excluded because it is secondary-like
        ("Škola za medicinske sestre", True, False),
    ],
)
def test_school_name_patterns(name: str, secondary: bool, primary: bool) -> None:
    assert bool(fac.SECONDARY_SCHOOL.search(name)) is secondary
    assert bool(fac.PRIMARY_SCHOOL.search(name)) is primary
