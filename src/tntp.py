# code to read files from https://github.com/bstabler/TransportationNetworks
import geopandas as gpd
import itertools
import osmnx
import pandas as pd
import pathlib
import re


def read_net_file(
    path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node", k_col: str = None, crs: str = None
) -> gpd.GeoDataFrame:
    """Read a network (edge) file and return a GeoDataFrame.

    Parameters
    ----------
    path:
        Path to the input file.
    u_col, v_col, k_col:
        Column names used for the from/to/key index. If ``k_col`` is
        ``None`` a default ``key`` column of zeros is added.
    crs:
        Coordinate reference system for the returned GeoDataFrame.

    Returns
    -------
    gpd.GeoDataFrame
        GeoDataFrame indexed by ``(u_col, v_col, k_col)`` with a ``geometry``
        column of ``None`` values and the optional CRS applied.
    """

    df = pd.read_csv(path, skiprows=8, sep="\t")
    df.rename(columns={name: name.strip() for name in df.columns}, inplace=True)
    df.drop(["~", ";"], axis=1, inplace=True)

    if k_col is None:
        k_col = "key"
        df[k_col] = 0
    df.set_index([u_col, v_col, k_col], inplace=True, verify_integrity=True)
    df["geometry"] = None
    return gpd.GeoDataFrame(df, crs=crs)


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
    df.set_index([u_col, v_col, k_col], inplace=True, verify_integrity=True)
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

    data = open(path, mode).read()
    if isinstance(data, bytes):
        data = data.decode(enc)

    header_pattern = r"Origin\s+(\d+)"
    demand_pattern = r"(\d+)\s*:\s*(\d+(?:\.\d+));"
    # the resulting list contains the input string split according to the header pattern
    # since the header pattern includes a capturing group, it also contains the captured groups
    # the first block is the data preceding the first split, which is the metadata (and we want to discard it)
    blocks = re.split(header_pattern, data)[1:]

    rows = []
    # after discarding the first block containing the metadata, we can iterate over pairs of origin and the demands
    for orig, block in itertools.batched(blocks, 2):
        for dest, demand in re.findall(demand_pattern, block):
            rows.append((orig, dest, demand))

    df = pd.DataFrame(rows, columns=["orig", "dest", "demand"])
    df["orig"] = df["orig"].astype(int)
    df["dest"] = df["dest"].astype(int)
    df["demand"] = df["demand"].astype(float)
    return df.pivot(index="orig", columns="dest", values="demand")


def convert_to_networkx(node_df: gpd.GeoDataFrame, net_df: gpd.GeoDataFrame, flow_df: pd.DataFrame = None):
    """Convert node and edge GeoDataFrames to a NetworkX graph.

    Columns in ``node_df`` are converted to nodes attrs, columns in ``net_df`` and ``flow_df`` to edge attrs.

    Parameters
    ----------
    node_df:
        GeoDataFrame of nodes from ``read_node_file``.
    net_df:
        GeoDataFrame of edges from ``read_net_file``.
    flow_df:
        Optional DataFrame from ``read_flow_file``.

    Returns
    -------
    networkx.MultiDiGraph
        Graph representing the provided node and edge GeoDataFrames.
    """

    # graph_from_gdfs requires x and y columns specifically
    node_df["x"] = node_df.geometry.x
    node_df["y"] = node_df.geometry.y

    if flow_df is not None:
        flow_df.index.set_names(net_df.index.names, inplace=True)
        net_df = net_df.join(flow_df)

    return osmnx.convert.graph_from_gdfs(node_df, net_df)
