"""
=============================================================
  Project 20 – Path Tracing Tool (SDN-based)
  Mininet Topology Script
=============================================================
  Topology (Linear – 3 switches, 3 hosts):

      h1 ── s1 ── s2 ── s3 ── h3
                  |
                  h2

  Run (requires root):
      sudo python3 mininet_topo.py

  Controller must already be running:
      ryu-manager path_tracer.py --observe-links
=============================================================
"""

from mininet.net    import Mininet
from mininet.topo   import Topo
from mininet.node   import RemoteController, OVSKernelSwitch
from mininet.link   import TCLink
from mininet.cli    import CLI
from mininet.log    import setLogLevel, info


# ─────────────────────────────────────────────────────────── #
#  Topology Definitions                                        #
# ─────────────────────────────────────────────────────────── #

class LinearSDNTopo(Topo):
    """
    Linear topology:
        h1 -- s1 -- s2 -- s3 -- h3
                    |
                    h2
    """
    def build(self):
        # Switches
        s1 = self.addSwitch('s1', dpid='0000000000000001')
        s2 = self.addSwitch('s2', dpid='0000000000000002')
        s3 = self.addSwitch('s3', dpid='0000000000000003')

        # Hosts (fixed MACs for easy testing)
        h1 = self.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/24')
        h2 = self.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2/24')
        h3 = self.addHost('h3', mac='00:00:00:00:00:03', ip='10.0.0.3/24')

        # Host-to-switch links
        self.addLink(h1, s1)
        self.addLink(h2, s2)
        self.addLink(h3, s3)

        # Switch-to-switch links
        self.addLink(s1, s2)
        self.addLink(s2, s3)


class StarSDNTopo(Topo):
    """
    Star topology (4 switches, one central):
        h1 -- s1
        h2 -- s2 -- s0 (core)
        h3 -- s3
        h4 -- s4
    """
    def build(self):
        s0 = self.addSwitch('s0', dpid='0000000000000010')
        s1 = self.addSwitch('s1', dpid='0000000000000001')
        s2 = self.addSwitch('s2', dpid='0000000000000002')
        s3 = self.addSwitch('s3', dpid='0000000000000003')
        s4 = self.addSwitch('s4', dpid='0000000000000004')

        h1 = self.addHost('h1', mac='00:00:00:00:00:01', ip='10.0.0.1/24')
        h2 = self.addHost('h2', mac='00:00:00:00:00:02', ip='10.0.0.2/24')
        h3 = self.addHost('h3', mac='00:00:00:00:00:03', ip='10.0.0.3/24')
        h4 = self.addHost('h4', mac='00:00:00:00:00:04', ip='10.0.0.4/24')

        self.addLink(h1, s1)
        self.addLink(h2, s2)
        self.addLink(h3, s3)
        self.addLink(h4, s4)

        self.addLink(s1, s0)
        self.addLink(s2, s0)
        self.addLink(s3, s0)
        self.addLink(s4, s0)


# ─────────────────────────────────────────────────────────── #
#  Runner                                                      #
# ─────────────────────────────────────────────────────────── #

def run(topo_type='linear'):
    if topo_type == 'star':
        topo = StarSDNTopo()
        info("*** Using Star topology\n")
    else:
        topo = LinearSDNTopo()
        info("*** Using Linear topology\n")

    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6633),
        switch=OVSKernelSwitch,
        link=TCLink,
        autoSetMacs=False
    )

    net.start()
    info("\n")
    info("=" * 55 + "\n")
    info("  Path Tracing Tool – Network Running\n")
    info("=" * 55 + "\n")
    info("  Hosts:\n")
    for h in net.hosts:
        info(f"    {h.name}  MAC={h.MAC()}  IP={h.IP()}\n")
    info("\n")
    info("  Suggested tests:\n")
    info("    h1 ping h3           # trace multi-hop path\n")
    info("    h1 ping h2\n")
    info("    h2 ping h3\n")
    info("\n")
    info("  REST API:\n")
    info("    curl http://localhost:8080/topology\n")
    info("    curl http://localhost:8080/paths\n")
    info("    curl http://localhost:8080/path/00:00:00:00:00:01/00:00:00:00:00:03\n")
    info("=" * 55 + "\n\n")

    CLI(net)
    net.stop()


if __name__ == '__main__':
    import sys
    setLogLevel('info')
    topo_choice = sys.argv[1] if len(sys.argv) > 1 else 'linear'
    run(topo_choice)
