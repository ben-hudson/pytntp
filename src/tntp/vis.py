import networkx as nx
import numpy as np
import pandas as pd


def quantile_edge_colors(G: nx.MultiDiGraph, attr: str, cmap: str) -> pd.Series:
    """Color edges by the percentile rank of ``attr`` rather than the raw value.

    Returns a Series of hex colors keyed by ``(u, v, key)`` in the same order
    osmnx's plotting helpers expect.
    """
    import matplotlib.colors
    import matplotlib.pyplot as plt

    vals = pd.Series(nx.get_edge_attributes(G, attr))
    quantiles = vals.rank(pct=True)
    palette = plt.get_cmap(cmap)
    return quantiles.map(lambda q: matplotlib.colors.to_hex(palette(q)))


def offset_parallel_edges(
    G: nx.MultiDiGraph, *, offset_frac: float = 0.05, force: bool = False
) -> None:
    """Give each edge a perpendicular-offset ``geometry`` so parallel edges fan apart.

    ``(u→v)`` and ``(v→u)`` automatically receive opposite normals because their
    direction vectors flip sign. The offset distance is ``offset_frac`` of the
    network's median edge length. Mutates ``G`` in place by setting each edge's
    ``geometry`` attribute to a ``shapely.LineString``.

    Raises ``ValueError`` if any edge already has a non-null ``geometry``
    (e.g. from a prior call or a hand-set geometry); pass ``force=True`` to
    overwrite anyway.
    """
    from shapely.geometry import LineString

    if not force:
        existing = nx.get_edge_attributes(G, "geometry")
        if existing:
            raise ValueError(
                f"{len(existing)} edges already have a geometry attribute "
                f"(first: {next(iter(existing))}). Pass force=True to overwrite."
            )

    node_x = nx.get_node_attributes(G, "x")
    node_y = nx.get_node_attributes(G, "y")

    edges = list(G.edges(keys=True))
    ux = np.array([node_x[u] for u, _, _ in edges])
    uy = np.array([node_y[u] for u, _, _ in edges])
    vx = np.array([node_x[v] for _, v, _ in edges])
    vy = np.array([node_y[v] for _, v, _ in edges])

    dx, dy = vx - ux, vy - uy
    length = np.hypot(dx, dy)
    delta = np.median(length) * offset_frac
    nx_off = -dy / length * delta
    ny_off = dx / length * delta

    u_pts = list(zip(ux + nx_off, uy + ny_off))
    v_pts = list(zip(vx + nx_off, vy + ny_off))
    for (u, v, k), u_pt, v_pt in zip(edges, u_pts, v_pts):
        G[u][v][k]["geometry"] = LineString([u_pt, v_pt])
