import geopandas as gpd
import networkx as nx
import osmnx


def convert_to_networkx(
    node_df: gpd.GeoDataFrame,
    net_df: gpd.GeoDataFrame,
    u_col: str = "init_node",
    v_col: str = "term_node",
) -> nx.MultiDiGraph:
    """Convert edge and node GeoDataFrames to a NetworkX graph.

    Routes through ``osmnx.convert.graph_from_gdfs`` so the returned graph is
    osmnx-compatible: it carries ``net_df.crs`` on ``G.graph["crs"]``, every
    node has ``x`` / ``y`` attributes, and edges are keyed by ``(u, v, 0)``
    (TNTP networks have no parallel edges, so ``key`` is always ``0``).

    ``node_df`` and ``net_df`` are not modified in place; the
    reprojected/augmented copies live only in the returned graph.

    Columns in ``net_df`` become edge attributes; ``node_df`` columns
    (including ``geometry``-derived ``x`` / ``y``) become node attributes.
    If you have a flow DataFrame, merge it into ``net_df`` (e.g.
    ``net_df.merge(flow_df, on=[u_col, v_col])``) before calling.

    Parameters
    ----------
    node_df:
        GeoDataFrame of nodes from ``read_node_file``. If its CRS differs from
        ``net_df.crs`` it is reprojected to match.
    net_df:
        GeoDataFrame of edges from ``read_net_file``, optionally pre-merged
        with a flow DataFrame.
    u_col, v_col:
        Column names in ``net_df`` holding the from/to ids for each edge.

    Returns
    -------
    networkx.MultiDiGraph
        Graph whose nodes come from ``node_df`` and whose edges are ``net_df``.
    """

    node_df = node_df.copy()

    target_crs = getattr(net_df, "crs", None)
    if target_crs is not None:
        node_df = node_df.to_crs(target_crs)
    node_df["x"] = node_df.geometry.x
    node_df["y"] = node_df.geometry.y

    net_df = net_df.assign(key=0)
    return osmnx.convert.graph_from_gdfs(node_df, net_df.set_index([u_col, v_col, "key"]))
