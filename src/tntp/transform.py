import geopandas as gpd
import pandas as pd


def split_zone_nodes(
    node_df: gpd.GeoDataFrame,
    net_df: gpd.GeoDataFrame,
    demand_df: pd.DataFrame,
    u_col: str = "init_node",
    v_col: str = "term_node",
) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]:
    """Duplicate every node ``n < first_thru_node`` into source/sink copies.

    TNTP networks declare a ``<FIRST THRU NODE>`` value: nodes with id less
    than this value (centroids) may originate or terminate trips but cannot
    be routed *through*. This function enforces that constraint structurally
    by splitting each centroid ``n`` into two fresh integer ids allocated
    above ``max(node_df.index)``:

    - ``source_id[n]`` carries ``n``'s outgoing edges and demand row.
    - ``sink_id[n]`` carries ``n``'s incoming edges and demand column.

    Because the source has no incoming edges and the sink has no outgoing
    edges, no path can traverse the centroid. Original centroid ids are
    removed from every output; ``node_df`` is the source of truth for the
    id space. The returned ``node_df`` carries a ``parent_node`` column:
    the original id for non-centroid rows, and the centroid id for both
    source and sink copies of a split centroid.

    Parameters
    ----------
    node_df:
        Node GeoDataFrame from ``read_node_file``. Used as the source of
        truth for both the centroid set (``index < first_thru_node``) and
        the id ceiling above which new ids are allocated.
    net_df:
        Edge GeoDataFrame from ``read_net_file``.
    demand_df:
        OD demand from ``read_demand_file``, indexed origin x destination.
    u_col, v_col:
        Column names in ``net_df`` holding the from/to ids for each edge.

    Returns
    -------
    tuple[gpd.GeoDataFrame, gpd.GeoDataFrame, pd.DataFrame]
        The split node, edge, and demand tables. The input ``node_df``,
        ``net_df`` and ``demand_df`` are left unchanged; all results are
        returned in the tuple.
    """

    node_df = node_df.copy()
    net_df = net_df.copy()

    first_thru_node = int(net_df.attrs.get("FIRST THRU NODE", 1))
    zones = [n for n in node_df.index if n < first_thru_node]

    start = int(node_df.index.max()) + 1
    n_zones = len(zones)
    source_nodes = dict(zip(zones, range(start, start + n_zones)))
    sink_nodes = dict(zip(zones, range(start + n_zones, start + 2 * n_zones)))

    # remap to source/sink nodes but default to original node if it doesn't exist in source/sink mapping
    net_df[u_col] = net_df[u_col].map(lambda n: source_nodes.get(n, n))
    net_df[v_col] = net_df[v_col].map(lambda n: sink_nodes.get(n, n))

    demand_df = demand_df.rename(index=source_nodes, columns=sink_nodes)

    node_df["parent_node"] = node_df.index
    zone_rows = node_df.loc[zones]
    sources = zone_rows.rename(index=source_nodes)
    sinks = zone_rows.rename(index=sink_nodes)
    node_df = pd.concat([node_df.drop(zones), sources, sinks])

    return node_df, net_df, demand_df
