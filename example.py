import matplotlib.pyplot as plt
import osmnx as ox
import tntp

from urllib.parse import urljoin

name = "ChicagoSketch"
root = f"https://raw.githubusercontent.com/bstabler/TransportationNetworks/refs/heads/master/Chicago-Sketch/"
flow_df = tntp.read_flow_file(urljoin(root, f"{name}_flow.tntp")).rename(
    columns={"From": "init_node", "To": "term_node"}
)
network = tntp.convert_to_networkx(
    tntp.read_net_file(urljoin(root, f"{name}_net.tntp"), crs="EPSG:26771"),
    tntp.read_node_file(urljoin(root, f"{name}_node.tntp"), index_col="node", x_col="X", y_col="Y", crs="EPSG:26771"),
    flow_df=flow_df,
)

for u, v, k, data in network.edges(keys=True, data=True):
    data["vc_ratio"] = data["Volume"] / data["capacity"]

tntp.offset_parallel_edges(network)

# Plot only the road links — drop link_type==3 (centroid connectors) so they
# don't clutter the map or compress the quantile colormap.
road_edges = [(u, v, k) for u, v, k, d in network.edges(keys=True, data=True) if d.get("link_type") != 3]
roads = network.edge_subgraph(road_edges)

fig, (ax_vc, ax_flow) = plt.subplots(1, 2, figsize=(16, 8), facecolor="#111111")
for ax in (ax_vc, ax_flow):
    ax.set_facecolor("#111111")
ox.plot.plot_graph(
    roads,
    ax=ax_vc,
    edge_color=tntp.quantile_edge_colors(roads, "vc_ratio", "RdYlGn_r"),
    show=False,
)
ax_vc.set_title("Link congestion", color="white")
ox.plot.plot_graph(
    roads,
    ax=ax_flow,
    edge_color=tntp.quantile_edge_colors(roads, "Volume", "viridis"),
    show=False,
)
ax_flow.set_title("Traffic flow", color="white")

fig.savefig("example.png", dpi=300, facecolor=fig.get_facecolor())
plt.show()
