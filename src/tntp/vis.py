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
