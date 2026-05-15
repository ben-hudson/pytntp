# code to read files from https://github.com/bstabler/TransportationNetworks
import geopandas as gpd
import io
import networkx as nx
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


def _parse_net_metadata(data: str) -> dict:
    """Pull every ``<KEY> VALUE`` line out of a .net file header.

    Stops at ``<END OF METADATA>``. Values are cast to int when they parse
    cleanly as integers; otherwise kept as strings. Keys are lowercased
    with spaces replaced by underscores so they can be used as attribute names.
    No assumption is made about which keys are present.
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
        Path to the input file.
    index_col:
        Column to use as the index for the returned GeoDataFrame.
    x_col, y_col:
        Column names containing the coordinate values.
    crs:
        Coordinate reference system for the returned GeoDataFrame.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame indexed by ``index_col`` with a Point ``geometry`` column.
    """

    df = pd.read_csv(path, sep="\t", index_col=index_col)
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)
    df.drop([";"], axis=1, inplace=True)

    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[x_col], df[y_col], crs=crs))


def read_flow_file(
    path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node", k_col: str = None
) -> pd.DataFrame:
    """Read a flow file and return a DataFrame indexed by (u, v, key).

    Parameters
    ----------
    path:
        Path to the input file.
    u_col, v_col, k_col:
        Column names used for the from/to/key index. If ``k_col`` is
        ``None`` a default ``key`` column of zeros is added.

    Returns
    -------
    pd.DataFrame
        DataFrame indexed by ``(u_col, v_col, k_col)`` containing the
        flow attributes.
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

    Columns in ``net_df`` and ``flow_df`` are converted to edge attrs. If
    ``node_df`` is provided, its columns are attached as node attrs.

    Parameters
    ----------
    net_df:
        GeoDataFrame of edges from ``read_net_file``.
    node_df:
        Optional GeoDataFrame of nodes from ``read_node_file``.
    flow_df:
        Optional DataFrame from ``read_flow_file``. Must share
        ``u_col``/``v_col``/``k_col`` column names with ``net_df``.
    u_col, v_col, k_col:
        Column names in ``net_df`` (and ``flow_df``) holding the from/to/key
        ids for each edge.

    Returns
    -------
    networkx.MultiDiGraph
        Graph representing the provided edges (and nodes, if any).
    """

    if flow_df is not None:
        net_df = pd.merge(net_df, flow_df, on=[u_col, v_col, k_col])

    if node_df is not None:
        # graph_from_gdfs requires x and y node columns and a (u, v, key) edge index
        node_df = node_df.copy()
        node_df["x"] = node_df.geometry.x
        node_df["y"] = node_df.geometry.y
        return osmnx.convert.graph_from_gdfs(node_df, net_df.set_index([u_col, v_col, k_col]))

    return nx.from_pandas_edgelist(
        net_df,
        source=u_col,
        target=v_col,
        edge_key=k_col,
        edge_attr=True,
        create_using=nx.MultiDiGraph,
    )


def split_non_through_nodes(
    net_df: gpd.GeoDataFrame,
    demand_df: pd.DataFrame,
    u_col: str = "init_node",
    v_col: str = "term_node",
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Duplicate every node ``n < first_thru_node`` into source/sink copies.

    TNTP networks declare a ``<FIRST THRU NODE>`` value: nodes with id less
    than this value (centroids) may originate or terminate trips but cannot
    be routed *through*. This function enforces that constraint structurally
    by splitting each non-through node ``n`` into two ids:

    - ``"{n}_source"`` carries ``n``'s outgoing edges and demand row.
    - ``"{n}_sink"`` carries ``n``'s incoming edges and demand column.

    Because the source has no incoming edges and the sink has no outgoing
    edges, no path can traverse the centroid. New ``"{n}_sink"`` demand
    rows and ``"{n}_source"`` demand columns are zero-filled. The pre-rename
    endpoint ids are preserved in ``{u_col}_orig`` / ``{v_col}_orig`` columns.

    Parameters
    ----------
    net_df:
        Edge GeoDataFrame from ``read_net_file``.
    demand_df:
        OD demand from ``read_demand_file``, indexed origin x destination.
    first_thru_node:
        Smallest node id allowed to carry through traffic. If ``None``, taken
        from ``net_df.attrs["first_thru_node"]``.
    u_col, v_col:
        Column names in ``net_df`` holding the from/to ids for each edge.

    Returns
    -------
    tuple[gpd.GeoDataFrame, pd.DataFrame]
        The split edge and demand tables.
    """

    first_thru_node = int(net_df.attrs.get("FIRST THRU NODE", "1"))

    net_df = net_df.copy()
    net_df[f"{u_col}_orig"] = net_df[u_col]
    net_df[f"{v_col}_orig"] = net_df[v_col]
    net_df[u_col] = net_df[u_col].map(lambda n: f"{n}_source" if n < first_thru_node else n)
    net_df[v_col] = net_df[v_col].map(lambda n: f"{n}_sink" if n < first_thru_node else n)

    centroids = [n for n in demand_df.index if n < first_thru_node]
    demand_df = demand_df.rename(
        index={n: f"{n}_source" for n in centroids},
        columns={n: f"{n}_sink" for n in centroids},
    )
    new_index = list(demand_df.index) + [f"{n}_sink" for n in centroids]
    new_cols = list(demand_df.columns) + [f"{n}_source" for n in centroids]
    demand_df = demand_df.reindex(index=new_index, columns=new_cols, fill_value=0.0)

    return net_df, demand_df
