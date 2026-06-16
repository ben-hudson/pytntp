# code to read files from https://github.com/bstabler/TransportationNetworks
import geopandas as gpd
import io
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
