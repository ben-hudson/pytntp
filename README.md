# pytntp
Tiny library to read .tntp (Transportation Network Test Problem) files and convert into NetworkX graphs.

## Installation
```
pip install git+https://github.com/ben-hudson/pytntp
```

## Example usage
```
root = "https://raw.githubusercontent.com/bstabler/TransportationNetworks/refs/heads/master/SiouxFalls/"
flow_df = tntp.read_flow_file(urljoin(root, "SiouxFalls_flow.tntp")).rename(
    columns={"From": "init_node", "To": "term_node"}
)
network = tntp.convert_to_networkx(
    tntp.read_net_file(urljoin(root, "SiouxFalls_net.tntp"), crs="wgs84"),
    tntp.read_node_file(urljoin(root, "SiouxFalls_node.tntp"), index_col="Node", x_col="X", y_col="Y", crs="wgs84"),
    flow_df=flow_df,
)

colors = ox.plot.get_edge_colors_by_attr(network, "Cost", cmap="RdYlGn_r")
ox.plot.plot_graph(network, edge_color=colors, show=False, save=True, dpi=300, filepath="example.png")
```
