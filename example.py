import osmnx as ox
import tntp

from urllib.parse import urljoin

root = "https://raw.githubusercontent.com/bstabler/TransportationNetworks/refs/heads/master/SiouxFalls/"
network = tntp.convert_to_networkx(
    tntp.read_node_file(urljoin(root, "SiouxFalls_node.tntp"), index_col="Node", x_col="X", y_col="Y", crs="wgs84"),
    tntp.read_net_file(urljoin(root, "SiouxFalls_net.tntp"), crs="wgs84"),
    tntp.read_flow_file(urljoin(root, "SiouxFalls_flow.tntp"), u_col="From", v_col="To"),
)

colors = ox.plot.get_edge_colors_by_attr(network, "Cost", cmap="RdYlGn_r")
ox.plot.plot_graph(network, edge_color=colors, show=False, save=True, dpi=300, filepath="example.png")
