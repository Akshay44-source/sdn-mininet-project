"""
=============================================================
  Project 20 – Path Tracing Tool (SDN-based)
  Test Suite
=============================================================
  Two test classes:

  1. TestPathLogic         – unit tests (no controller needed)
     • Graph path finding
     • Path length / hops
     • No-path detection
     • MAC learning table
     • Multi-hop path sequence
     • Path installation order
     • Regression: path remains after re-install

  2. TestRESTAPI           – integration tests (controller needed)
     • /topology endpoint
     • /paths endpoint
     • /mac_table endpoint
     • /path/<src>/<dst> endpoint

  Run all:
      python3 test_path_tracer.py

  Run only unit tests (no controller):
      python3 -m unittest test_path_tracer.TestPathLogic -v
=============================================================
"""

import unittest
import json
import sys

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    import networkx as nx
    NX_AVAILABLE = True
except ImportError:
    NX_AVAILABLE = False

BASE_URL = "http://localhost:8080"
CONTROLLER_TIMEOUT = 4  # seconds


# ======================================================================= #
#  Unit Tests – Path Logic (no running controller required)               #
# ======================================================================= #
class TestPathLogic(unittest.TestCase):
    """Tests for core path-tracing algorithms using NetworkX."""

    def setUp(self):
        if not NX_AVAILABLE:
            self.skipTest("networkx not installed")

    # ─── Build a standard 3-switch linear graph ─────────────────────── #
    def _linear_graph(self):
        """s1 ─ s2 ─ s3"""
        G = nx.DiGraph()
        G.add_nodes_from([1, 2, 3])
        G.add_edge(1, 2, src_port=2, dst_port=1)
        G.add_edge(2, 1, src_port=1, dst_port=2)
        G.add_edge(2, 3, src_port=2, dst_port=1)
        G.add_edge(3, 2, src_port=1, dst_port=2)
        return G

    # ─── Test 1 ─────────────────────────────────────────────────────── #
    def test_01_path_found_direct_neighbours(self):
        """Path between directly connected switches."""
        G = self._linear_graph()
        path = nx.shortest_path(G, 1, 2)
        self.assertEqual(path, [1, 2])
        print(f"  [PASS] Direct path: {path}")

    # ─── Test 2 ─────────────────────────────────────────────────────── #
    def test_02_path_found_multi_hop(self):
        """Path traverses intermediate switch (s1 → s2 → s3)."""
        G = self._linear_graph()
        path = nx.shortest_path(G, 1, 3)
        self.assertEqual(path, [1, 2, 3])
        print(f"  [PASS] Multi-hop path: {path}")

    # ─── Test 3 ─────────────────────────────────────────────────────── #
    def test_03_path_length_in_hops(self):
        """Hop count equals number of switches in path."""
        G = self._linear_graph()
        path = nx.shortest_path(G, 1, 3)
        hops = len(path)
        self.assertEqual(hops, 3)
        print(f"  [PASS] Hop count: {hops}")

    # ─── Test 4 ─────────────────────────────────────────────────────── #
    def test_04_no_path_detection(self):
        """NetworkXNoPath raised when destination is unreachable."""
        G = nx.DiGraph()
        G.add_nodes_from([1, 2])  # no edges
        with self.assertRaises((nx.NetworkXNoPath, nx.NetworkXError, nx.NodeNotFound)):
            nx.shortest_path(G, 1, 2)
        print("  [PASS] Unreachable destination correctly detected")

    # ─── Test 5 ─────────────────────────────────────────────────────── #
    def test_05_mac_learning_table(self):
        """MAC table correctly stores and retrieves host locations."""
        mac_to_port = {}
        mac_to_dpid = {}

        # Simulate PacketIn learning
        events = [
            (1, '00:00:00:00:00:01', 3),
            (2, '00:00:00:00:00:02', 1),
            (3, '00:00:00:00:00:03', 1),
        ]
        for dpid, mac, port in events:
            mac_to_port.setdefault(dpid, {})[mac] = port
            mac_to_dpid[mac] = dpid

        self.assertEqual(mac_to_port[1]['00:00:00:00:00:01'], 3)
        self.assertEqual(mac_to_dpid['00:00:00:00:00:02'], 2)
        self.assertEqual(mac_to_port[3]['00:00:00:00:00:03'], 1)
        print("  [PASS] MAC learning table correct")

    # ─── Test 6 ─────────────────────────────────────────────────────── #
    def test_06_intermediate_ports_identified(self):
        """For each hop, src_port can be retrieved from edge data."""
        G = self._linear_graph()
        path = nx.shortest_path(G, 1, 3)

        for i in range(len(path) - 1):
            edge = G.get_edge_data(path[i], path[i + 1])
            self.assertIsNotNone(edge, f"Missing edge {path[i]}→{path[i+1]}")
            self.assertIn('src_port', edge)
            self.assertIn('dst_port', edge)

        print(f"  [PASS] Port data present for every hop in {path}")

    # ─── Test 7 ─────────────────────────────────────────────────────── #
    def test_07_path_installation_order(self):
        """Path list is ordered from source to destination."""
        G = self._linear_graph()
        path = nx.shortest_path(G, 3, 1)  # reverse direction
        self.assertEqual(path[0], 3)
        self.assertEqual(path[-1], 1)
        print(f"  [PASS] Path order correct: {path}")

    # ─── Test 8 ─────────────────────────────────────────────────────── #
    def test_08_regression_path_consistent_after_reinstall(self):
        """
        Regression: re-computing path after topology rebuild
        returns the same result (path remains unchanged).
        """
        G = self._linear_graph()
        path1 = nx.shortest_path(G, 1, 3)

        # Simulate topology refresh (rebuild from same data)
        G2 = self._linear_graph()
        path2 = nx.shortest_path(G2, 1, 3)

        self.assertEqual(path1, path2)
        print(f"  [PASS] Regression: path unchanged after topology rebuild → {path1}")

    # ─── Test 9 ─────────────────────────────────────────────────────── #
    def test_09_star_topology_all_paths(self):
        """In a star topology all hosts can reach each other via the core."""
        G = nx.DiGraph()
        # Core switch = 0, edge switches 1-4
        for i in range(1, 5):
            G.add_edge(i, 0, src_port=1, dst_port=i)
            G.add_edge(0, i, src_port=i, dst_port=1)

        pairs = [(1, 2), (1, 3), (1, 4), (2, 3), (2, 4), (3, 4)]
        for src, dst in pairs:
            path = nx.shortest_path(G, src, dst)
            self.assertIsNotNone(path)
            self.assertEqual(path[0], src)
            self.assertEqual(path[-1], dst)

        print(f"  [PASS] Star topology: all {len(pairs)} paths reachable")

    # ─── Test 10 ──────────────────────────────────────────────────────── #
    def test_10_path_log_structure(self):
        """Path log entries contain required fields."""
        path_log = []

        entry = {
            'src_mac'  : '00:00:00:00:00:01',
            'dst_mac'  : '00:00:00:00:00:03',
            'path'     : [1, 2, 3],
            'hops'     : 3,
            'timestamp': '2026-04-17 10:00:00'
        }
        path_log.append(entry)

        self.assertEqual(len(path_log), 1)
        e = path_log[0]
        for field in ('src_mac', 'dst_mac', 'path', 'hops', 'timestamp'):
            self.assertIn(field, e)
        self.assertEqual(e['hops'], len(e['path']))
        print(f"  [PASS] Path log entry structure valid: {e}")


# ======================================================================= #
#  Integration Tests – REST API (requires running controller)             #
# ======================================================================= #
class TestRESTAPI(unittest.TestCase):
    """Live REST API tests. Skipped if controller is not reachable."""

    @classmethod
    def setUpClass(cls):
        if not REQUESTS_AVAILABLE:
            return
        try:
            requests.get(f"{BASE_URL}/topology", timeout=CONTROLLER_TIMEOUT)
        except requests.ConnectionError:
            cls._controller_up = False
        else:
            cls._controller_up = True

    def _skip_if_down(self):
        if not REQUESTS_AVAILABLE or not getattr(self, '_controller_up', False):
            self.skipTest("Controller not reachable at " + BASE_URL)

    # ─── Test A ─────────────────────────────────────────────────────── #
    def test_A_topology_endpoint_status(self):
        """GET /topology returns HTTP 200."""
        self._skip_if_down()
        r = requests.get(f"{BASE_URL}/topology", timeout=CONTROLLER_TIMEOUT)
        self.assertEqual(r.status_code, 200)
        print("  [PASS] /topology → 200 OK")

    # ─── Test B ─────────────────────────────────────────────────────── #
    def test_B_topology_fields(self):
        """GET /topology response contains switches, links, hosts."""
        self._skip_if_down()
        data = requests.get(f"{BASE_URL}/topology",
                            timeout=CONTROLLER_TIMEOUT).json()
        for field in ('switches', 'links', 'hosts'):
            self.assertIn(field, data)
        print(f"  [PASS] /topology fields present: "
              f"{len(data['switches'])} switches, "
              f"{len(data['links'])} links, "
              f"{len(data['hosts'])} hosts")

    # ─── Test C ─────────────────────────────────────────────────────── #
    def test_C_paths_endpoint_status(self):
        """GET /paths returns HTTP 200."""
        self._skip_if_down()
        r = requests.get(f"{BASE_URL}/paths", timeout=CONTROLLER_TIMEOUT)
        self.assertEqual(r.status_code, 200)
        print("  [PASS] /paths → 200 OK")

    # ─── Test D ─────────────────────────────────────────────────────── #
    def test_D_paths_fields(self):
        """GET /paths response has correct fields."""
        self._skip_if_down()
        data = requests.get(f"{BASE_URL}/paths",
                            timeout=CONTROLLER_TIMEOUT).json()
        self.assertIn('traced_paths', data)
        self.assertIn('total_paths_traced', data)
        self.assertIsInstance(data['traced_paths'], list)
        print(f"  [PASS] /paths: {data['total_paths_traced']} paths in log")

    # ─── Test E ─────────────────────────────────────────────────────── #
    def test_E_mac_table_endpoint(self):
        """GET /mac_table returns HTTP 200 with expected keys."""
        self._skip_if_down()
        r    = requests.get(f"{BASE_URL}/mac_table", timeout=CONTROLLER_TIMEOUT)
        data = r.json()
        self.assertEqual(r.status_code, 200)
        self.assertIn('mac_to_port', data)
        self.assertIn('mac_to_dpid', data)
        print(f"  [PASS] /mac_table: {len(data['mac_to_dpid'])} hosts known")

    # ─── Test F ─────────────────────────────────────────────────────── #
    def test_F_path_query_unknown_host(self):
        """GET /path with unknown MACs returns error field, not crash."""
        self._skip_if_down()
        src = 'ff:ff:ff:ff:ff:01'
        dst = 'ff:ff:ff:ff:ff:02'
        r   = requests.get(f"{BASE_URL}/path/{src}/{dst}",
                           timeout=CONTROLLER_TIMEOUT)
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertIn('error', data)
        print(f"  [PASS] /path unknown hosts → graceful error: {data['error']}")

    # ─── Test G ─────────────────────────────────────────────────────── #
    def test_G_path_query_known_hosts(self):
        """
        If h1 and h3 have communicated, path query returns a valid list.
        Skips if hosts are not yet known to the controller.
        """
        self._skip_if_down()
        src = '00:00:00:00:00:01'
        dst = '00:00:00:00:00:03'
        r   = requests.get(f"{BASE_URL}/path/{src}/{dst}",
                           timeout=CONTROLLER_TIMEOUT)
        data = r.json()

        if 'error' in data:
            self.skipTest("Hosts not yet known – run: h1 ping h3 in Mininet CLI")

        path = data.get('path')
        self.assertIsNotNone(path)
        self.assertIsInstance(path, list)
        self.assertGreater(len(path), 0)
        print(f"  [PASS] /path/{src}/{dst} → {data.get('readable')}")


# ======================================================================= #
#  Main                                                                    #
# ======================================================================= #
if __name__ == '__main__':
    print("\n" + "=" * 62)
    print("  Project 20 – Path Tracing Tool (SDN-based) – Test Suite")
    print("=" * 62)

    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()

    print("\n  [1/2] Unit Tests (TestPathLogic)")
    print("  " + "─" * 50)
    suite.addTests(loader.loadTestsFromTestCase(TestPathLogic))

    print("\n  [2/2] Integration Tests (TestRESTAPI)")
    print("  " + "─" * 50)
    suite.addTests(loader.loadTestsFromTestCase(TestRESTAPI))

    runner = unittest.TextTestRunner(verbosity=2, stream=sys.stdout)
    result = runner.run(suite)

    print("\n" + "=" * 62)
    if result.wasSuccessful():
        print("  ✓  ALL TESTS PASSED")
    else:
        failed = len(result.failures) + len(result.errors)
        skipped = len(result.skipped)
        print(f"  ✗  {failed} FAILED  |  {skipped} SKIPPED")
    print("=" * 62 + "\n")
