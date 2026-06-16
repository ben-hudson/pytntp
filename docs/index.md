# tntp

Tiny library to read `.tntp` ([Transportation Network Test Problem][tntp-repo]) files
and convert them into [NetworkX][networkx] graphs. Networks are loaded into
[GeoDataFrames][geopandas] and converted to [osmnx][osmnx]-compatible
`MultiDiGraph`s, so the whole geospatial and graph-analysis ecosystem is available
to you out of the box.

## Installation

```
pip install git+https://github.com/ben-hudson/pytntp
```

## At a glance

```python
import tntp
from urllib.parse import urljoin

root = "https://raw.githubusercontent.com/bstabler/TransportationNetworks/refs/heads/master/SiouxFalls/"
node_df = tntp.read_node_file(
    urljoin(root, "SiouxFalls_node.tntp"), index_col="Node", x_col="X", y_col="Y", crs="EPSG:4326"
)
net_df = tntp.read_net_file(urljoin(root, "SiouxFalls_net.tntp"), crs="EPSG:4326")
network = tntp.convert_to_networkx(node_df, net_df)
```

## Where to go next

- **[Getting started](getting-started.md)** — load a network end-to-end, compute link
  congestion, and render a map.
- **[Zone splitting](zone-splitting.md)** — enforce the TNTP centroid constraint by
  splitting zone nodes into source/sink pairs.
- **[API reference](reference/index.md)** — every public function, generated from the source.

[tntp-repo]: https://github.com/bstabler/TransportationNetworks
[networkx]: https://networkx.org/
[geopandas]: https://geopandas.org/
[osmnx]: https://osmnx.readthedocs.io/
