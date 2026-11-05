"""``GET /route``: shortest walking path to the nearest facility of a category (free of FastAPI)."""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse.csgraph import dijkstra

from blizu_api import service
from blizu_api.constants import CATEGORIES, DIJKSTRA_LIMIT_M
from blizu_api.scoring import minutes
from blizu_api.store import DataStore
from blizu_api.walk import (
    InvalidRequestError,
    NotReachableError,
    Origin,
    WalkIndex,
)

NO_PREDECESSOR = -9999  # scipy's marker


def path_nodes(pred: np.ndarray, origin_node: int, target: int) -> list[int]:
    """Node sequence origin -> target from a scipy predecessor row."""
    nodes = [target]
    while nodes[-1] != origin_node:
        prev = int(pred[nodes[-1]])
        if prev == NO_PREDECESSOR or len(nodes) > len(pred):
            raise NotReachableError("Put nije pronađen.")
        nodes.append(prev)
    nodes.reverse()
    return nodes


def compute_route(
    store: DataStore,
    index: WalkIndex,
    origin: Origin,
    persona: str,
    category: str | None = None,
    facility_id: int | None = None,
) -> dict[str, Any]:
    """Route to the nearest facility of ``category`` or to ``facility_id``.

    The target is chosen like ``/access`` does: smallest network distance over the facilities'
    access nodes within 4 km (ties: lowest facility id). ``minutes`` and ``distance_m`` include the
    origin's snap distance exactly as ``/access`` does, so both endpoints report the same minutes.
    Raises :class:`InvalidRequestError` (contradictory parameters) and
    :class:`NotReachableError` (unknown facility, no data, or nothing within 4 km).
    """
    if facility_id is None and category is None:
        raise InvalidRequestError("Navedite 'category' ili 'facility_id'.")
    if facility_id is not None:
        record = store.facility(facility_id)
        if record is None:
            raise NotReachableError("Objekt nije pronađen.")
        if category is not None and category != record["category"]:
            raise InvalidRequestError("'facility_id' ne pripada navedenoj kategoriji.")
        category = str(record["category"])
    assert category is not None
    if category not in CATEGORIES:
        raise InvalidRequestError("Nepoznata kategorija.")
    persona_cfg = store.cfg.personas[persona]
    fn = index.facilities(category)
    label = store.cfg.categories[category].label
    if not len(fn.ids):
        raise NotReachableError(f"{label}: nema učitanih podataka.")

    dist, pred = dijkstra(
        store.graph.variant(persona_cfg.graph),
        directed=True,  # symmetric CSR (see undirected_csr)
        indices=origin.node,
        limit=DIJKSTRA_LIMIT_M,  # the same limit as the /access arrays
        return_predecessors=True,
    )
    d_ap = dist[fn.nodes]
    if facility_id is not None:
        d_ap = np.where(fn.ids[fn.owner] == facility_id, d_ap, np.inf)
    ap_ids = fn.ids[fn.owner]
    order = np.lexsort((ap_ids, d_ap))  # nearest first, ties by facility id
    best = int(order[0])
    if not np.isfinite(d_ap[best]):
        raise NotReachableError(
            f"{label}: najbliži objekt je dalje od {round(DIJKSTRA_LIMIT_M / 1000)} km hoda."
        )
    nodes = path_nodes(pred, origin.node, int(fn.nodes[best]))
    coords = [[float(index.lon5[n]), float(index.lat5[n])] for n in nodes]
    if len(coords) == 1:  # facility on the origin's node: keep a valid (2-point) LineString
        coords = coords * 2
    total_m = origin.snapped_m + float(d_ap[best])
    fac = store.facility(int(ap_ids[best]))
    assert fac is not None
    return {
        "persona": persona,
        "category": category,
        "speed_mps": persona_cfg.speed_mps,
        "origin": origin.as_json(),
        "minutes": round(minutes(total_m, persona_cfg.speed_mps), 1),
        "distance_m": round(total_m),
        "facility": {
            "id": fac["id"],
            "category": category,
            "name": service.display_name(store, category, fac["name"]),
            "address": fac["address"],
            "lon": fac["lon"],
            "lat": fac["lat"],
            "source_id": fac["source_id"],
            "tier": fac["tier"],
        },
        "coordinates": coords,
    }
