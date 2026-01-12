# code to read files from https://github.com/bstabler/TransportationNetworks
import geopandas as gpd
import itertools
import osmnx
import pandas as pd
import pathlib
import re


def read_net_file(
    path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node", k_col: str = None
) -> gpd.GeoDataFrame:
    df = pd.read_csv(path, skiprows=8, sep="\t")
    df.rename(columns={name: name.strip().lower() for name in df.columns}, inplace=True)
    df.drop(["~", ";"], axis=1, inplace=True)

    if k_col is None:
        k_col = "key"
        df[k_col] = 0
    df.set_index([u_col, v_col, k_col], inplace=True, verify_integrity=True)
    return gpd.GeoDataFrame(df)


def read_node_file(path: pathlib.Path, index_col: str = "node") -> gpd.GeoDataFrame:
    df = pd.read_csv(path, sep="\t")
    df.rename(columns={name: name.strip().lower() for name in df.columns}, inplace=True)
    df.drop([";"], axis=1, inplace=True)

    df.set_index(index_col, inplace=True, verify_integrity=True)
    return gpd.GeoDataFrame(df)


def read_flow_file(
    path: pathlib.Path, u_col: str = "init_node", v_col: str = "term_node", k_col: str = None
) -> pd.DataFrame:
    df = pd.read_csv(path, sep="\t")
    df.rename(columns={name: name.strip().lower() for name in df.columns}, inplace=True)

    if k_col is None:
        k_col = "key"
        df[k_col] = 0
    df.set_index([u_col, v_col, k_col], inplace=True, verify_integrity=True)
    return df


def read_demand_file(path: pathlib.Path, mode: str = "r", enc: str = "utf-8") -> pd.DataFrame:
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


def convert_to_networkx(
    node_df: gpd.GeoDataFrame, net_df: gpd.GeoDataFrame, flow_df: pd.DataFrame = None, crs: str = None
):
    if flow_df is not None:
        flow_df.index.set_names(net_df.index.names, inplace=True)
        net_df = net_df.join(flow_df)

    return osmnx.convert.graph_from_gdfs(node_df, net_df, graph_attrs={"crs": crs})
