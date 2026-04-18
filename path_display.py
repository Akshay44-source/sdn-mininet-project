"""
=============================================================
  Project 20 – Path Tracing Tool (SDN-based)
  CLI Display & Route Visualizer
=============================================================
  Run after controller + mininet are running:
      python3 path_display.py
      python3 path_display.py --watch        # auto-refresh every 3s
      python3 path_display.py --path 00:00:00:00:00:01 00:00:00:00:00:03
=============================================================
"""

import requests
import json
import time
import sys
import argparse
from datetime import datetime

BASE_URL = "http://localhost:8080"

# ─── ANSI colours ─────────────────────────────────────────── #
class C:
    HEADER  = '\033[95m'
    BLUE    = '\033[94m'
    CYAN    = '\033[96m'
    GREEN   = '\033[92m'
    YELLOW  = '\033[93m'
    RED     = '\033[91m'
    BOLD    = '\033[1m'
    RESET   = '\033[0m'
    DIM     = '\033[2m'


def hdr(text):
    w = 60
    print(f"\n{C.BOLD}{C.BLUE}{'═'*w}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {text}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'═'*w}{C.RESET}")


def fetch(endpoint):
    try:
        r = requests.get(f"{BASE_URL}{endpoint}", timeout=4)
        return r.json()
    except requests.ConnectionError:
        print(f"{C.RED}[ERROR] Cannot connect to controller at {BASE_URL}{C.RESET}")
        print(f"{C.DIM}  Make sure: ryu-manager path_tracer.py --observe-links{C.RESET}")
        return None
    except Exception as e:
        print(f"{C.RED}[ERROR] {e}{C.RESET}")
        return None


# ─── Topology display ─────────────────────────────────────── #
def display_topology():
    hdr("Network Topology")
    data = fetch("/topology")
    if data is None:
        return

    switches = data.get('switches', [])
    links    = data.get('links', [])
    hosts    = data.get('hosts', [])

    print(f"\n  {C.CYAN}Switches ({len(switches)}){C.RESET}")
    for s in sorted(switches):
        print(f"    {C.GREEN}● S{s}{C.RESET}")

    print(f"\n  {C.CYAN}Links ({len(links)}){C.RESET}")
    drawn = set()
    for lk in links:
        key = tuple(sorted([lk['src'], lk['dst']]))
        if key not in drawn:
            drawn.add(key)
            print(f"    S{lk['src']} ──[port {lk['src_port']}]── S{lk['dst']}")

    print(f"\n  {C.CYAN}Known Hosts ({len(hosts)}){C.RESET}")
    if hosts:
        for mac in hosts:
            print(f"    {C.YELLOW}◉ {mac}{C.RESET}")
    else:
        print(f"    {C.DIM}(none yet — trigger some pings){C.RESET}")


# ─── ASCII path diagram ───────────────────────────────────── #
def draw_path(path, src_mac, dst_mac):
    if not path:
        print(f"  {C.RED}No path found.{C.RESET}")
        return

    print(f"\n  {C.CYAN}Route: {src_mac}  →  {dst_mac}{C.RESET}")
    print()

    parts = [f"  {C.YELLOW}[{src_mac}]{C.RESET}"]
    for dpid in path:
        parts.append(f"{C.GREEN} ══[S{dpid}]══ {C.RESET}")
    parts.append(f"{C.YELLOW}[{dst_mac}]{C.RESET}")

    print("".join(parts))
    print(f"\n  {C.DIM}Hops: {len(path)} switch(es){C.RESET}")


# ─── All traced paths ─────────────────────────────────────── #
def display_paths():
    hdr("Traced Paths Log")
    data = fetch("/paths")
    if data is None:
        return

    total  = data.get('total_paths_traced', 0)
    traced = data.get('traced_paths', [])

    print(f"\n  Total paths traced: {C.BOLD}{C.GREEN}{total}{C.RESET}\n")

    if not traced:
        print(f"  {C.DIM}No paths traced yet. Run: h1 ping h3 in Mininet CLI.{C.RESET}")
        return

    # Deduplicate (show latest per src/dst pair)
    seen = {}
    for entry in traced:
        key = (entry['src_mac'], entry['dst_mac'])
        seen[key] = entry

    print(f"  {'SRC MAC':<20} {'DST MAC':<20} {'HOPS':>5}  {'PATH'}")
    print(f"  {'─'*20} {'─'*20} {'─'*5}  {'─'*30}")
    for entry in seen.values():
        path_str = ' → '.join(f"S{d}" for d in entry['path'])
        ts       = entry.get('timestamp', '')
        print(f"  {C.YELLOW}{entry['src_mac']:<20}{C.RESET} "
              f"{C.YELLOW}{entry['dst_mac']:<20}{C.RESET} "
              f"{C.GREEN}{entry['hops']:>5}{C.RESET}  "
              f"{C.CYAN}{path_str}{C.RESET}  {C.DIM}{ts}{C.RESET}")
        draw_path(entry['path'], entry['src_mac'], entry['dst_mac'])


# ─── Single path query ────────────────────────────────────── #
def display_single_path(src_mac, dst_mac):
    hdr(f"Path: {src_mac}  →  {dst_mac}")
    data = fetch(f"/path/{src_mac}/{dst_mac}")
    if data is None:
        return

    if 'error' in data:
        print(f"\n  {C.RED}{data['error']}{C.RESET}")
        known = data.get('known_hosts', [])
        if known:
            print(f"\n  Known hosts:")
            for h in known:
                print(f"    {h}")
        return

    path = data.get('path')
    draw_path(path, src_mac, dst_mac)
    print(f"\n  Readable: {C.CYAN}{data.get('readable')}{C.RESET}")


# ─── MAC table ────────────────────────────────────────────── #
def display_mac_table():
    hdr("MAC Learning Table")
    data = fetch("/mac_table")
    if data is None:
        return

    mac_to_dpid = data.get('mac_to_dpid', {})
    mac_to_port = data.get('mac_to_port', {})

    print(f"\n  {'MAC':<22} {'SWITCH':>8}  {'PORT':>6}")
    print(f"  {'─'*22} {'─'*8}  {'─'*6}")
    for mac, dpid in mac_to_dpid.items():
        port = mac_to_port.get(str(dpid), {}).get(mac, '?')
        print(f"  {C.YELLOW}{mac:<22}{C.RESET} {C.GREEN}S{dpid:>6}{C.RESET}  {C.CYAN}{port:>6}{C.RESET}")

    if not mac_to_dpid:
        print(f"  {C.DIM}(empty – trigger traffic in Mininet CLI){C.RESET}")


# ─── Full dashboard ───────────────────────────────────────── #
def dashboard():
    print(f"\n{C.BOLD}{C.HEADER}"
          f"  ╔══════════════════════════════════════════════════════╗\n"
          f"  ║       Path Tracing Tool (SDN-based)  –  Dashboard   ║\n"
          f"  ║               Project 20                            ║\n"
          f"  ╚══════════════════════════════════════════════════════╝"
          f"{C.RESET}")
    print(f"  {C.DIM}Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}{C.RESET}")

    display_topology()
    display_paths()
    display_mac_table()
    print()


# ─── Entry point ──────────────────────────────────────────── #
def main():
    parser = argparse.ArgumentParser(description='Path Tracing Tool – CLI Display')
    parser.add_argument('--watch',  action='store_true',
                        help='Auto-refresh dashboard every 3 seconds')
    parser.add_argument('--path',   nargs=2, metavar=('SRC_MAC', 'DST_MAC'),
                        help='Query path between two specific MACs')
    parser.add_argument('--topo',   action='store_true',
                        help='Show topology only')
    parser.add_argument('--paths',  action='store_true',
                        help='Show traced paths only')
    args = parser.parse_args()

    if args.path:
        display_single_path(args.path[0], args.path[1])
    elif args.topo:
        display_topology()
    elif args.paths:
        display_paths()
    elif args.watch:
        try:
            while True:
                print('\033[2J\033[H', end='')  # clear screen
                dashboard()
                print(f"  {C.DIM}(Refreshing every 3s … Ctrl-C to stop){C.RESET}")
                time.sleep(3)
        except KeyboardInterrupt:
            print("\n  Stopped.")
    else:
        dashboard()


if __name__ == '__main__':
    main()
