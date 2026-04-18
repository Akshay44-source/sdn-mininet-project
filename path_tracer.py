"""
=============================================================
  Project 20 – Path Tracing Tool (SDN-based)
  Ryu OpenFlow 1.3 Controller
=============================================================
  Features:
    • Topology discovery via LLDP (EventSwitchEnter / EventLinkAdd)
    • MAC learning (host location: dpid + port)
    • Shortest-path routing with NetworkX (BFS/Dijkstra)
    • Flow rule installation along the entire path
    • Full path log (src_mac, dst_mac, switch hops)
    • REST API  →  /topology  /paths  /path/<src>/<dst>  /mac_table
=============================================================
  Run:
    ryu-manager path_tracer.py --observe-links
=============================================================
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (CONFIG_DISPATCHER,
                                     MAIN_DISPATCHER,
                                     set_ev_cls)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.topology import event as topo_event
from ryu.topology.api import get_switch, get_link
from ryu.app.wsgi import ControllerBase, WSGIApplication, route

import networkx as nx
import json
import datetime
from webob import Response

REST_NAME = 'path_tracer_api'


class PathTracerController(app_manager.RyuApp):
    """
    SDN Path Tracing Controller

    Responsibilities
    ----------------
    1. Maintain a directed graph of the switch topology.
    2. Learn MAC ↔ (dpid, port) mappings from incoming packets.
    3. Compute shortest path between source and destination switch.
    4. Install proactive flow rules along that path.
    5. Log every traced path for REST queries and CLI display.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    # ------------------------------------------------------------------ #
    #  Initialisation                                                      #
    # ------------------------------------------------------------------ #
    def __init__(self, *args, **kwargs):
        super(PathTracerController, self).__init__(*args, **kwargs)
        self.name = 'path_tracer'

        # Switch registry  { dpid: datapath }
        self.datapaths = {}

        # MAC learning tables
        self.mac_to_port = {}    # { dpid: { mac: port } }
        self.mac_to_dpid = {}    # { mac: dpid }

        # Network topology graph
        self.net = nx.DiGraph()

        # Traced paths log  [ { src_mac, dst_mac, path, timestamp } ]
        self.path_log = []

        # Register REST API
        wsgi = kwargs['wsgi']
        wsgi.register(PathTracerAPI, {REST_NAME: self})

        self.logger.info("=== Path Tracing Tool Controller Started ===")

    # ------------------------------------------------------------------ #
    #  OpenFlow: Switch connects                                           #
    # ------------------------------------------------------------------ #
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        ofp = dp.ofproto
        parser = dp.ofproto_parser

        self.datapaths[dp.id] = dp
        self.net.add_node(dp.id)

        # Table-miss rule → send to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER,
                                          ofp.OFPCML_NO_BUFFER)]
        self._add_flow(dp, priority=0, match=match, actions=actions)
        self.logger.info("[SWITCH] S%d connected", dp.id)

    # ------------------------------------------------------------------ #
    #  Topology events                                                     #
    # ------------------------------------------------------------------ #
    @set_ev_cls(topo_event.EventSwitchEnter)
    def switch_enter(self, ev):
        self._refresh_topology()

    @set_ev_cls(topo_event.EventSwitchLeave)
    def switch_leave(self, ev):
        self._refresh_topology()

    @set_ev_cls(topo_event.EventLinkAdd)
    def link_add(self, ev):
        self._refresh_topology()

    @set_ev_cls(topo_event.EventLinkDelete)
    def link_delete(self, ev):
        self._refresh_topology()

    def _refresh_topology(self):
        """Rebuild the NetworkX graph from Ryu topology API."""
        switches = get_switch(self, None)
        links    = get_link(self, None)

        self.net.clear()

        for sw in switches:
            self.net.add_node(sw.dp.id)

        for lk in links:
            self.net.add_edge(
                lk.src.dpid, lk.dst.dpid,
                src_port=lk.src.port_no,
                dst_port=lk.dst.port_no
            )

        self.logger.info(
            "[TOPOLOGY] %d switches | %d links",
            self.net.number_of_nodes(),
            self.net.number_of_edges()
        )

    # ------------------------------------------------------------------ #
    #  OpenFlow: Packet-In                                                 #
    # ------------------------------------------------------------------ #
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg      = ev.msg
        dp       = msg.datapath
        ofp      = dp.ofproto
        parser   = dp.ofproto_parser
        in_port  = msg.match['in_port']
        dpid     = dp.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        # Ignore LLDP – Ryu handles it internally
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        src = eth.src
        dst = eth.dst

        # ── Learn source MAC ──────────────────────────────────────────── #
        self.mac_to_port.setdefault(dpid, {})[src] = in_port
        self.mac_to_dpid[src] = dpid

        # ── Determine output port ─────────────────────────────────────── #
        out_port = self._resolve_output_port(dp, dpid, src, dst, in_port)

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow if we know the port
        if out_port != ofp.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            self._add_flow(dp, priority=1, match=match, actions=actions)

        # Send the buffered packet
        data = msg.data if msg.buffer_id == ofp.OFP_NO_BUFFER else None
        out  = parser.OFPPacketOut(
            datapath=dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        dp.send_msg(out)

    # ------------------------------------------------------------------ #
    #  Path resolution logic                                              #
    # ------------------------------------------------------------------ #
    def _resolve_output_port(self, dp, dpid, src, dst, in_port):
        """
        Decide where to send the packet.
        If dst is on a different switch → compute path → install rules.
        """
        ofp = dp.ofproto

        # Destination known on this switch
        if dst in self.mac_to_port.get(dpid, {}):
            return self.mac_to_port[dpid][dst]

        # Destination is on another switch
        if dst in self.mac_to_dpid:
            dst_dpid = self.mac_to_dpid[dst]
            path     = self._find_path(dpid, dst_dpid)

            if path and len(path) > 1:
                self._install_path(path, src, dst)
                # First hop port
                edge = self.net.get_edge_data(path[0], path[1])
                if edge:
                    return edge['src_port']

        # Unknown → flood
        return ofp.OFPP_FLOOD

    def _find_path(self, src_dpid, dst_dpid):
        """Return shortest path list of dpids, or None."""
        try:
            return nx.shortest_path(self.net, src_dpid, dst_dpid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    def _install_path(self, path, src_mac, dst_mac):
        """
        Install one flow rule per switch along the path.
        Last switch forwards to the host port; others forward to next switch.
        """
        for i, dpid in enumerate(path):
            dp = self.datapaths.get(dpid)
            if dp is None:
                continue

            parser = dp.ofproto_parser

            if i == len(path) - 1:
                # Last switch: forward to host
                out_port = self.mac_to_port.get(dpid, {}).get(dst_mac)
                if out_port is None:
                    continue
            else:
                # Intermediate: forward toward next switch
                edge = self.net.get_edge_data(dpid, path[i + 1])
                if edge is None:
                    continue
                out_port = edge['src_port']

            match   = parser.OFPMatch(eth_dst=dst_mac)
            actions = [parser.OFPActionOutput(out_port)]
            self._add_flow(dp, priority=2, match=match, actions=actions,
                           idle_timeout=30, hard_timeout=120)

        # Record traced path
        entry = {
            'src_mac'  : src_mac,
            'dst_mac'  : dst_mac,
            'path'     : path,
            'hops'     : len(path),
            'timestamp': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        self.path_log.append(entry)

        readable = ' -> '.join(f'S{d}' for d in path)
        self.logger.info("[PATH] %s → %s  |  %s  (%d hops)",
                         src_mac, dst_mac, readable, len(path))

    # ------------------------------------------------------------------ #
    #  Helper: install flow                                                #
    # ------------------------------------------------------------------ #
    def _add_flow(self, dp, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        ofp    = dp.ofproto
        parser = dp.ofproto_parser
        inst   = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        mod    = parser.OFPFlowMod(
            datapath=dp,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        dp.send_msg(mod)


# ======================================================================= #
#  REST API                                                                #
# ======================================================================= #
class PathTracerAPI(ControllerBase):
    """
    REST endpoints
    ──────────────
    GET /topology          →  switches, links, known hosts
    GET /paths             →  all traced paths + topology summary
    GET /path/<src>/<dst>  →  path between two MACs (if known)
    GET /mac_table         →  full MAC learning tables
    """

    def __init__(self, req, link, data, **config):
        super(PathTracerAPI, self).__init__(req, link, data, **config)
        self.pt = data[REST_NAME]

    # ── /topology ─────────────────────────────────────────────────────── #
    @route(REST_NAME, '/topology', methods=['GET'])
    def get_topology(self, req, **kw):
        pt = self.pt
        body = {
            'switches': list(pt.net.nodes()),
            'links'   : [
                {
                    'src'     : u,
                    'dst'     : v,
                    'src_port': pt.net[u][v]['src_port'],
                    'dst_port': pt.net[u][v]['dst_port']
                }
                for u, v in pt.net.edges()
            ],
            'hosts': list(pt.mac_to_dpid.keys())
        }
        return Response(content_type='application/json',
                        body=json.dumps(body, indent=2).encode('utf-8'))

    # ── /paths ────────────────────────────────────────────────────────── #
    @route(REST_NAME, '/paths', methods=['GET'])
    def get_all_paths(self, req, **kw):
        pt = self.pt
        body = {
            'total_paths_traced': len(pt.path_log),
            'traced_paths'      : pt.path_log,
            'topology_summary'  : {
                'switches': list(pt.net.nodes()),
                'links'   : [{'src': u, 'dst': v}
                             for u, v in pt.net.edges()]
            }
        }
        return Response(content_type='application/json',
                        body=json.dumps(body, indent=2).encode('utf-8'))

    # ── /path/<src_mac>/<dst_mac> ─────────────────────────────────────── #
    @route(REST_NAME, '/path/{src_mac}/{dst_mac}', methods=['GET'])
    def get_path(self, req, src_mac, dst_mac, **kw):
        pt       = self.pt
        src_dpid = pt.mac_to_dpid.get(src_mac)
        dst_dpid = pt.mac_to_dpid.get(dst_mac)

        if src_dpid is None or dst_dpid is None:
            body = {
                'error': 'One or both hosts not yet seen by the controller',
                'known_hosts': list(pt.mac_to_dpid.keys())
            }
        else:
            path = pt._find_path(src_dpid, dst_dpid)
            body = {
                'src_mac' : src_mac,
                'dst_mac' : dst_mac,
                'src_dpid': src_dpid,
                'dst_dpid': dst_dpid,
                'path'    : path,
                'hops'    : len(path) if path else 0,
                'readable': ' -> '.join(f'S{d}' for d in path) if path else 'No path'
            }

        return Response(content_type='application/json',
                        body=json.dumps(body, indent=2).encode('utf-8'))

    # ── /mac_table ────────────────────────────────────────────────────── #
    @route(REST_NAME, '/mac_table', methods=['GET'])
    def get_mac_table(self, req, **kw):
        pt = self.pt
        body = {
            'mac_to_port': {str(k): v for k, v in pt.mac_to_port.items()},
            'mac_to_dpid': pt.mac_to_dpid
        }
        return Response(content_type='application/json',
                        body=json.dumps(body, indent=2).encode('utf-8'))
