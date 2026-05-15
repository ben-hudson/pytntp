import osmnx as ox
import tntp

from urllib.parse import urljoin

network = "Anaheim"
root = f"https://raw.githubusercontent.com/bstabler/TransportationNetworks/refs/heads/master/{network}/"
flow_df = tntp.read_flow_file(urljoin(root, f"{network}_flow.tntp")).rename(
    columns={"From": "init_node", "To": "term_node"}
)
network = tntp.convert_to_networkx(
    tntp.read_net_file(urljoin(root, f"{network}_net.tntp"), crs="wgs84"),
    # tntp.read_node_file(urljoin(root, f"{network}_node.tntp"), index_col="node", x_col="X", y_col="Y", crs="wgs84"),
    flow_df=flow_df,
)
network.graph["crs"] = "EPSG:26771"

colors = ox.plot.get_edge_colors_by_attr(network, "Cost", cmap="RdYlGn_r")
ox.plot.plot_graph(network, edge_color=colors, show=False, save=True, dpi=300, filepath="example.png")
