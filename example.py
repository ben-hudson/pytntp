import pathlib
import tntp

root = pathlib.Path("./data/SiouxFalls")
network = tntp.convert_to_networkx(
    tntp.read_node_file(root / "SiouxFalls_node.tntp", index_col="Node", x_col="X", y_col="Y", crs="wgs84"),
    tntp.read_net_file(root / "SiouxFalls_net.tntp", crs="wgs84"),
    tntp.read_flow_file(root / "SiouxFalls_flow.tntp", u_col="From", v_col="To"),
)

node_list = list(network.nodes)
demand_table = tntp.read_demand_file(root / "SiouxFalls_trips.tntp").reindex(index=node_list, columns=node_list)
