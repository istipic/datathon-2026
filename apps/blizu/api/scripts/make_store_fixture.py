"""Dump REAL facilities, cells and source metadata around Trg bana Jelacica as test fixtures.

usage: uv run python apps/blizu/api/scripts/make_store_fixture.py <out_dir> <YYYY-MM-DD>
Needs DATABASE_URL (the Blizu database after `blizu ingest all`) and the API's /sources response
from the same run saved by hand: curl .../api/v1/sources > <out_dir>/<date>_sources.json
"""

import json
import sys
from pathlib import Path

import sqlalchemy as sa

from blizu_api.settings import BlizuSettings
from opendata_core.geo import bbox_around

out_dir, date = Path(sys.argv[1]), sys.argv[2]
CENTER = (15.9771683, 45.8130887)
west, south, east, north = bbox_around(
    CENTER[0], CENTER[1], 1500
)  # facilities a bit beyond the 1 km graph box
engine = sa.create_engine(BlizuSettings().database_url)
with engine.connect() as c:
    fac = (
        c.execute(
            sa.text(
                "select id, category, name, address, source_id, tier, st_x(geom) lon, st_y(geom) lat, attrs "
                "from facility where st_x(geom) between :w and :e and st_y(geom) between :s and :n order by id"
            ),
            {"w": west, "e": east, "s": south, "n": north},
        )
        .mappings()
        .all()
    )
    cells = (
        c.execute(
            sa.text(
                "select grd_id, st_asgeojson(geom, 6) geojson, pop_total, pop_u15, pop_65p from cell "
                "where st_intersects(geom, st_makeenvelope(:w, :s, :e, :n, 4326)) order by grd_id"
            ),
            {"w": west, "e": east, "s": south, "n": north},
        )
        .mappings()
        .all()
    )
out_dir.mkdir(parents=True, exist_ok=True)
(out_dir / f"{date}_facilities_trg_bana_jelacica.json").write_text(
    json.dumps([dict(r) for r in fac], ensure_ascii=False, indent=1), encoding="utf-8"
)
(out_dir / f"{date}_cells_trg_bana_jelacica.json").write_text(
    json.dumps(
        [
            {**{k: v for k, v in r.items() if k != "geojson"}, "geometry": json.loads(r["geojson"])}
            for r in cells
        ],
        indent=1,
    ),
    encoding="utf-8",
)
print("facilities", len(fac), "cells", len(cells))
