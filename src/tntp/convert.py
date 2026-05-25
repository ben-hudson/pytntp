# code to read files from https://github.com/bstabler/TransportationNetworks
import geopandas as gpd
import io
import networkx as nx
import numpy as np
import osmnx
import pandas as pd
import pathlib
import re

from urllib.request import urlopen
from urllib.parse import urlparse

try:
    from itertools import batched
except ImportError:
    from itertools import islice

    def batched(iterable, n):
        iterator = iter(iterable)
        while True:
            batch = tuple(islice(iterator, n))
            if not batch:
                return
            yield batch


def _read_text(path: pathlib.Path, mode: str = "r", enc: str = "utf-8") -> str:
    """Read text from a local path or URL, decoding bytes if necessary."""
    path = str(path)
    if urlparse(path).scheme == "":
        with open(path, mode) as f:
            data = f.read()
    else:
        with urlopen(path) as f:
            data = f.read()
    if isinstance(data, bytes):
        data = data.decode(enc)
    return data


def _parse_net_metadata(data: str) -> tuple[dict, int]:
    """Pull every ``<KEY> VALUE`` line out of a .net file header.

    Stops at ``<END OF METADATA>``. Keys and values are kept as raw stripped
    strings (callers cast them as needed). No assumption is made about which
    keys are present. Returns ``(metadata, n_metadata_lines)`` so the caller
    can skip past the header when reading the body.
    """
    metadata_pattern = re.compile(r"<([^>]+)>\s*(.*)")
    metadata = {}

    for line_num, line in enumerate(data.splitlines()):
        match = metadata_pattern.match(line)

        # skip lines that are not <KEY> OPTIONAL VALUE
        if not match:
            continue

        key, val = match.group(1).strip(), match.group(2).strip()
        if key == "END OF METADATA":
            break

        metadata[key] = val

    n_metadata_lines = line_num + 1
    return metadata, n_metadata_lines


def read_net_file(
    path: pathlib.Path,
    crs: str = None,
    mode: str = "r",
    enc: str = "utf-8",
) -> gpd.GeoDataFrame:
    """Read a network (edge) file and return a GeoDataFrame.

    Parameters
    ----------
    path:
        Path or URL to the input file.
    crs:
        Coordinate reference system for the returned GeoDataFrame.
    mode:
        File open mode for local paths (default: "r"). Use "rb" for binary mode.
    enc:
        Encoding to decode bytes when read in binary mode or from a URL.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame with one row per edge, a ``key`` column of zeros, and
        a ``geometry`` column of ``None`` values (with the optional CRS
        applied). The ``<KEY> VALUE`` metadata header (e.g.
        ``FIRST THRU NODE``) is parsed and attached as ``gdf.attrs``.
    """

    data = _read_text(path, mode, enc)

    metadata, n_metadata_lines = _parse_net_metadata(data)

    df = pd.read_csv(io.StringIO(data), skiprows=n_metadata_lines, sep="\t")
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)
    df.drop(["~", ";"], axis=1, inplace=True)

    df["key"] = 0
    df["geometry"] = None
    gdf = gpd.GeoDataFrame(df, crs=crs)
    gdf.attrs = metadata
    return gdf


def read_node_file(
    path: pathlib.Path, index_col: str = "node", x_col: str = "x", y_col: str = "y", crs: str = None
) -> gpd.GeoDataFrame:
    """Read a node file and return a GeoDataFrame with Point geometries.

    Parameters
    ----------
    path:
        Path or URL to the input file (anything ``pandas.read_csv`` accepts).
    index_col:
        Column to use as the index for the returned GeoDataFrame.
    x_col, y_col:
        Column names containing the coordinate values.
    crs:
        Coordinate reference system for the returned GeoDataFrame.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame indexed by ``index_col`` with a Point ``geometry`` column
        built from ``x_col`` / ``y_col``.
    """

    df = pd.read_csv(path, sep="\t", index_col=index_col)
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)
    df.drop([";"], axis=1, inplace=True)

    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[x_col], df[y_col], crs=crs))


def read_flow_file(
    path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node", k_col: str = None
) -> pd.DataFrame:
    """Read a flow file and return a flat DataFrame of per-edge flow attributes.

    Parameters
    ----------
    path:
        Path or URL to the input file (anything ``pandas.read_csv`` accepts).
    u_col, v_col:
        Currently unused. Kept for symmetry with ``read_net_file`` so callers
        can pre-declare endpoint column names.
    k_col:
        Name of an existing key column to keep. If ``None``, a new ``key``
        column of zeros is added so the resulting frame can be merged
        against ``read_net_file`` output on ``(init_node, term_node, key)``.

    Returns
    -------
    pd.DataFrame
        Flat DataFrame with one row per edge and one column per flow attribute
        from the file (plus the synthesized ``key`` column if ``k_col`` was
        ``None``). No index is set.
    """

    df = pd.read_csv(path, sep="\t")
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)

    if k_col is None:
        k_col = "key"
        df[k_col] = 0
    return df


def read_demand_file(path: pathlib.Path, mode: str = "r", enc: str = "utf-8") -> pd.DataFrame:
    """Parse a TransportationNetworks demand file into an origin-destination matrix.

    Parameters
    ----------
    path:
        Path to the demand file.
    mode:
        File open mode (default: "r"). Use "rb" if you want binary mode.
    enc:
        Encoding to decode bytes when opened in binary mode (default: "utf-8").

    Returns
    -------
    pd.DataFrame
        Table of demands (index: origin, columns: destination).
    """

    data = _read_text(path, mode, enc)

    header_pattern = r"Origin\s+(\d+)"
    demand_pattern = r"(\d+)\s*:\s*(\d+(?:\.\d+));"
    # the resulting list contains the input string split according to the header pattern
    # since the header pattern includes a capturing group, it also contains the captured groups
    # the first block is the data preceding the first split, which is the metadata (and we want to discard it)
    blocks = re.split(header_pattern, data)[1:]

    rows = []
    # after discarding the first block containing the metadata, we can iterate over pairs of origin and the demands
    for orig, block in batched(blocks, 2):
        for dest, demand in re.findall(demand_pattern, block):
            rows.append((orig, dest, demand))

    df = pd.DataFrame(rows, columns=["orig", "dest", "demand"])
    df["orig"] = df["orig"].astype(int)
    df["dest"] = df["dest"].astype(int)
    df["demand"] = df["demand"].astype(float)
    return df.pivot(index="orig", columns="dest", values="demand")


def convert_to_networkx(
    net_df: gpd.GeoDataFrame,
    node_df: gpd.GeoDataFrame = None,
    flow_df: pd.DataFrame = None,
    u_col: str = "init_node",
    v_col: str = "term_node",
    k_col: str = "key",
) -> nx.MultiDiGraph:
    """Convert edge (and optional node) GeoDataFrames to a NetworkX graph.

    Routes through ``osmnx.convert.graph_from_gdfs`` so the returned graph is
    osmnx-compatible: it carries ``net_df.crs`` on ``G.graph["crs"]``, every
    node has ``x`` / ``y`` attributes, and edges are keyed by ``(u, v, key)``.

    Columns in ``net_df`` and ``flow_df`` become edge attributes (merged on
    ``(u_col, v_col, k_col)``). If ``node_df`` is provided its columns
    (including ``geometry``-derived ``x`` / ``y``) become node attributes;
    otherwise a NaN-coord node table is synthesized from the unique edge
    endpoints so the graph still round-trips through ``graph_to_gdfs``.

    Parameters
    ----------
    net_df:
        GeoDataFrame of edges from ``read_net_file``.
    node_df:
        Optional GeoDataFrame of nodes from ``read_node_file``. If its CRS
        differs from ``net_df.crs`` it is reprojected to match.
    flow_df:
        Optional DataFrame from ``read_flow_file``. Must share
        ``u_col``/``v_col``/``k_col`` column names with ``net_df``.
    u_col, v_col, k_col:
        Column names in ``net_df`` (and ``flow_df``) holding the from/to/key
        ids for each edge.

    Returns
    -------
    networkx.MultiDiGraph
        Graph whose nodes are the union of ``node_df.index`` (if given) and
        every endpoint of ``net_df``, and whose edges are ``net_df`` (merged
        with ``flow_df`` if supplied).
    """

    if flow_df is not None:
        net_df = pd.merge(net_df, flow_df, on=[u_col, v_col, k_col])

    endpoints = pd.unique(np.concatenate([net_df[u_col].values, net_df[v_col].values]))

    # graph_from_gdfs requires x/y columns on the node table; when the user has
    # no node file, synthesize a NaN-coord table so the graph still round-trips.
    if node_df is None:
        node_df = pd.DataFrame({"x": np.nan, "y": np.nan}, index=pd.Index(endpoints))
    else:
        target_crs = getattr(net_df, "crs", None)
        if target_crs is not None:
            node_df = node_df.to_crs(target_crs)
        node_df["x"] = node_df.geometry.x
        node_df["y"] = node_df.geometry.y
        node_df = node_df.reindex(node_df.index.union(endpoints))

    return osmnx.convert.graph_from_gdfs(node_df, net_df.set_index([u_col, v_col, k_col]))


def split_non_through_nodes(
    net_df: gpd.GeoDataFrame,
    demand_df: pd.DataFrame,
    node_df: gpd.GeoDataFrame = None,
    u_col: str = "init_node",
    v_col: str = "term_node",
) -> tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame | None]:
    """Duplicate every node ``n < first_thru_node`` into source/sink copies.

    TNTP networks declare a ``<FIRST THRU NODE>`` value: nodes with id less
    than this value (centroids) may originate or terminate trips but cannot
    be routed *through*. This function enforces that constraint structurally
    by splitting each non-through node ``n`` into two ids:

    - ``(n, "source")`` carries ``n``'s outgoing edges and demand row.
    - ``(n, "sink")`` carries ``n``'s incoming edges and demand column.

    Because the source has no incoming edges and the sink has no outgoing
    edges, no path can traverse the centroid. New ``(n, "sink")`` demand
    rows and ``(n, "source")`` demand columns are zero-filled. The pre-rename
    endpoint ids are preserved in ``{u_col}_orig`` / ``{v_col}_orig`` columns.

    Parameters
    ----------
    net_df:
        Edge GeoDataFrame from ``read_net_file``.
    demand_df:
        OD demand from ``read_demand_file``, indexed origin x destination.
    node_df:
        Optional node GeoDataFrame from ``read_node_file``. If given, each
        centroid row is duplicated into ``(n, "source")`` and ``(n, "sink")``
        copies sharing the original coordinates, so plotting still works.
    u_col, v_col:
        Column names in ``net_df`` holding the from/to ids for each edge.

    Returns
    -------
    tuple[gpd.GeoDataFrame, pd.DataFrame, gpd.GeoDataFrame | None]
        The split edge, demand, and node tables. The node table is ``None``
        when no ``node_df`` was provided.
    """

    first_thru_node = int(net_df.attrs.get("FIRST THRU NODE", "1"))

    net_df = net_df.join(net_df[[u_col, v_col]].add_suffix("_orig"))
    net_df[u_col] = net_df[u_col].map(lambda n: (n, "source") if n < first_thru_node else n)
    net_df[v_col] = net_df[v_col].map(lambda n: (n, "sink") if n < first_thru_node else n)

    centroids = [n for n in demand_df.index if n < first_thru_node]
    demand_df = demand_df.rename(
        index={n: (n, "source") for n in centroids},
        columns={n: (n, "sink") for n in centroids},
    )
    new_index = pd.Index(list(demand_df.index) + [(n, "sink") for n in centroids], dtype=object)
    new_cols = pd.Index(list(demand_df.columns) + [(n, "source") for n in centroids], dtype=object)
    demand_df = demand_df.reindex(index=new_index, columns=new_cols, fill_value=0.0)

    split_node_df = None
    if node_df is not None:
        centroid_rows = node_df.loc[node_df.index.isin(centroids)]
        sources = centroid_rows.rename(index={n: (n, "source") for n in centroid_rows.index})
        sinks = centroid_rows.rename(index={n: (n, "sink") for n in centroid_rows.index})
        non_centroids = node_df.loc[~node_df.index.isin(centroids)]
        split_node_df = pd.concat([non_centroids, sources, sinks])

    return net_df, demand_df, split_node_df
