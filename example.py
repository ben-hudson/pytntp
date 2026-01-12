import tntp
import pathlib

root = pathlib.Path("./data/SiouxFalls")
network = tntp.convert_to_networkx(
    tntp.read_node_file(root / "SiouxFalls_node.tntp"),
    tntp.read_net_file(root / "SiouxFalls_net.tntp"),
    tntp.read_flow_file(root / "SiouxFalls_flow.tntp", u_col="from", v_col="to"),
    crs="wgs84",
)

node_list = list(network.nodes)
demand_table = tntp.read_demand_file(root / "SiouxFalls_trips.tntp").reindex(index=node_list, columns=node_list)
