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
    u_col: str = "init_node",
    v_col: str = "term_node",
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

    # TNTP net files pad two blank/whitespace-only lines between
    # <END OF METADATA> and the ``~``-prefixed column-header row.
    df = pd.read_csv(io.StringIO(data), skiprows=n_metadata_lines + 2, sep="\t", dtype={u_col: int, v_col: int})
    df = df.rename(columns={name: name.strip() for name in df.columns})
    df = df.drop(["~", ";"], axis=1)
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

    df = pd.read_csv(
        path,
        sep="\t",
        index_col=index_col,
        usecols=[index_col, x_col, y_col],
        dtype={index_col: int, x_col: float, y_col: float},
    )
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)

    return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[x_col], df[y_col], crs=crs))


def read_flow_file(path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node") -> pd.DataFrame:
    """Read a flow file and return a flat DataFrame of per-edge flow attributes.

    Parameters
    ----------
    path:
        Path or URL to the input file (anything ``pandas.read_csv`` accepts).
    u_col, v_col:
        Names of the endpoint columns; cast to ``int`` on read so the frame
        can be merged against ``read_net_file`` output on ``(u_col, v_col)``.

    Returns
    -------
    pd.DataFrame
        Flat DataFrame with one row per edge and one column per flow attribute
        from the file. No index is set.
    """

    df = pd.read_csv(path, sep="\t", dtype={u_col: int, v_col: int})
    df = df.rename(columns={name: name.strip() for name in df.columns})
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

    dtypes = {"orig": int, "dest": int, "demand": float}
    df = pd.DataFrame(rows, columns=dtypes.keys()).astype(dtypes)
    return df.pivot(index="orig", columns="dest", values="demand")


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

    target_crs = getattr(net_df, "crs", None)
    if target_crs is not None:
        node_df = node_df.to_crs(target_crs)
    node_df["x"] = node_df.geometry.x
    node_df["y"] = node_df.geometry.y

    net_df = net_df.assign(key=0)
    return osmnx.convert.graph_from_gdfs(node_df, net_df.set_index([u_col, v_col, "key"]))


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
        The split node, edge, and demand tables.
    """

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
