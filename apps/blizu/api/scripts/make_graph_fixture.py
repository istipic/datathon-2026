"""Cut a 1 km box around Trg bana Jelacica out of the REAL OSM walking graph (GraphML from
`blizu ingest graph`) and save nodes/edges as CSV test fixtures.

usage: uv run python apps/blizu/api/scripts/make_graph_fixture.py <graphml> <out_dir> <YYYY-MM-DD>
"""

import sys
from pathlib import Path

import osmnx as ox

from opendata_core.geo import bbox_around

graphml, out_dir, date = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
CENTER = (15.9771683, 45.8130887)  # Trg bana Josipa Jelacica (Nominatim result, 2026-11-03)
g = ox.load_graphml(graphml)
nodes, edges = ox.graph_to_gdfs(g)
west, south, east, north = bbox_around(CENTER[0], CENTER[1], 1000)
inside = nodes[(nodes.x >= west) & (nodes.x <= east) & (nodes.y >= south) & (nodes.y <= north)]
edges = edges.reset_index()
edges = edges[edges.u.isin(inside.index) & edges.v.isin(inside.index)]
keep_cols = [c for c in ("u", "v", "length", "highway", "wheelchair", "name") if c in edges.columns]
out_dir.mkdir(parents=True, exist_ok=True)
inside[["x", "y"]].rename(columns={"x": "lon", "y": "lat"}).reset_index().rename(
    columns={"osmid": "osmid"}
).to_csv(out_dir / f"{date}_nodes_trg_bana_jelacica_1km.csv", index=False)
edges[keep_cols].to_csv(out_dir / f"{date}_edges_trg_bana_jelacica_1km.csv", index=False)
print("nodes", len(inside), "edges", len(edges))
print("highway values:", edges["highway"].astype(str).value_counts().head(8).to_dict())
if "wheelchair" in edges.columns:
    print("wheelchair values:", edges["wheelchair"].astype(str).value_counts().to_dict())
