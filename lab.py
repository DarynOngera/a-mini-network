#!/usr/bin/env python3
r"""
Mini network-diagnosis lab for Mininet.

Topology:

   h1 10.0.1.11 \                                   / web 10.0.2.10 (HTTP :80)
                  s1 --- r1 (10.0.1.1 | 10.0.2.1) --- s2
   h2 10.0.1.12 /          Linux router

Usage (needs root):
   sudo python3 lab.py --list
   sudo python3 lab.py --scenario healthy
   sudo python3 lab.py --scenario no_forwarding
   sudo python3 lab.py --scenario mystery        # random fault, answer hidden
   sudo python3 lab.py --scenario mystery --reveal   # (after you're done) show answer

Each scenario injects ONE fault, then drops you into the Mininet CLI.
Inside the CLI, run commands like:  h1 ping -c3 web   |  h1 curl -m5 http://10.0.2.10/
"""
import argparse
import os
import random
import sys

from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.net import Mininet
from mininet.node import Node, OVSBridge

ANSWER_FILE = "/tmp/mininet_lab_answer.txt"


class LinuxRouter(Node):
    """A host with IP forwarding enabled."""

    def config(self, **params):
        super().config(**params)
        self.cmd("sysctl -w net.ipv4.ip_forward=1")

    def terminate(self):
        self.cmd("sysctl -w net.ipv4.ip_forward=0")
        super().terminate()


def build():
    net = Mininet(controller=None, switch=OVSBridge, waitConnected=False)

    r1 = net.addHost("r1", cls=LinuxRouter, ip=None)
    s1 = net.addSwitch("s1")
    s2 = net.addSwitch("s2")

    h1 = net.addHost("h1", ip="10.0.1.11/24", defaultRoute="via 10.0.1.1")
    h2 = net.addHost("h2", ip="10.0.1.12/24", defaultRoute="via 10.0.1.1")
    web = net.addHost("web", ip="10.0.2.10/24", defaultRoute="via 10.0.2.1")

    net.addLink(h1, s1)
    net.addLink(h2, s1)
    net.addLink(s1, r1, intfName2="r1-eth1", params2={"ip": "10.0.1.1/24"})
    net.addLink(s2, r1, intfName2="r1-eth2", params2={"ip": "10.0.2.1/24"})
    net.addLink(web, s2)
    return net


def start_services(net):
    web = net["web"]
    web.cmd("mkdir -p /tmp/www && head -c 2000000 /dev/urandom > /tmp/www/big.bin "
            "&& echo 'hello from web' > /tmp/www/index.html")
    web.cmd("cd /tmp/www && python3 -m http.server 80 >/tmp/web_http.log 2>&1 &")


# ---------------------------------------------------------------- scenarios
# Each returns a (one-line cause, symptom hint) tuple.

def healthy(net):
    return ("No fault", "Everything should work. Learn the baseline output first.")


def wrong_gateway(net):
    net["h1"].cmd("ip route replace default via 10.0.1.99")
    return ("h1 default gateway points to a non-existent host (10.0.1.99)",
            "h1 can ping h2 but nothing off-subnet; h2 is fine.")


def no_forwarding(net):
    net["r1"].cmd("sysctl -w net.ipv4.ip_forward=0")
    return ("r1 has IP forwarding disabled",
            "Gateway answers ping, but nothing crosses to 10.0.2.0/24.")


def firewall_drop(net):
    net["web"].cmd("iptables -A INPUT -p tcp --dport 80 -j DROP")
    return ("web drops TCP/80 with iptables (DROP, silent)",
            "ping web works, but HTTP just times out.")


def firewall_reject(net):
    net["web"].cmd("iptables -A INPUT -p tcp --dport 80 -j REJECT --reject-with tcp-reset")
    return ("web REJECTs TCP/80 with a reset",
            "HTTP fails instantly ('connection refused') though the server is running.")


def service_down(net):
    net["web"].cmd("pkill -f 'http.server'")
    return ("HTTP server process on web is not running",
            "ping works, HTTP fails instantly with 'connection refused'.")


def high_latency_loss(net):
    net["web"].cmd("tc qdisc add dev web-eth0 root netem delay 200ms 50ms loss 15%")
    return ("netem on web-eth0: 200ms +-50ms delay and 15% loss",
            "Reachable but slow, ping RTT huge and some packets lost.")


def bandwidth_limit(net):
    net["web"].cmd("tc qdisc add dev web-eth0 root tbf rate 500kbit burst 5kb latency 50ms")
    return ("web-eth0 shaped to 500 kbit/s",
            "Pings are fine, but downloading big.bin is painfully slow.")


def mtu_blackhole(net):
    r1 = net["r1"]
    r1.cmd("ip link set r1-eth1 mtu 1200")
    r1.cmd("iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP")
    r1.cmd("iptables -A FORWARD -p icmp --icmp-type fragmentation-needed -j DROP")
    return ("r1-eth1 MTU is 1200 and ICMP 'frag needed' is filtered (PMTUD blackhole)",
            "Ping and TCP handshake work, small pages load, big downloads hang.")


def duplicate_ip(net):
    h2 = net["h2"]
    h2.cmd("ip addr flush dev h2-eth0")
    h2.cmd("ip addr add 10.0.1.11/24 dev h2-eth0")
    h2.cmd("ip route add default via 10.0.1.1")
    return ("h2 was given h1's IP (10.0.1.11)",
            "Intermittent connectivity for h1; ARP replies come from two MACs.")


def link_down(net):
    net.configLinkStatus("r1", "s2", "down")
    return ("link r1 <-> s2 is down",
            "Router can't reach the server subnet at all (Destination Host Unreachable from r1).")


SCENARIOS = {
    "healthy": healthy,
    "wrong_gateway": wrong_gateway,
    "no_forwarding": no_forwarding,
    "firewall_drop": firewall_drop,
    "firewall_reject": firewall_reject,
    "service_down": service_down,
    "high_latency_loss": high_latency_loss,
    "bandwidth_limit": bandwidth_limit,
    "mtu_blackhole": mtu_blackhole,
    "duplicate_ip": duplicate_ip,
    "link_down": link_down,
}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scenario", default="healthy", help="scenario name, or 'mystery'")
    ap.add_argument("--list", action="store_true", help="list scenarios and exit")
    ap.add_argument("--hint", action="store_true", help="print the symptom hint")
    ap.add_argument("--reveal", action="store_true", help="print the last mystery answer and exit")
    args = ap.parse_args()

    if args.list:
        for name in SCENARIOS:
            print(" ", name)
        return
    if args.reveal:
        print(open(ANSWER_FILE).read() if os.path.exists(ANSWER_FILE) else "No mystery answer saved.")
        return
    if os.geteuid() != 0:
        sys.exit("Run with sudo.")

    name = args.scenario
    mystery = name == "mystery"
    if mystery:
        name = random.choice([n for n in SCENARIOS if n != "healthy"])
    if name not in SCENARIOS:
        sys.exit("Unknown scenario. Use --list.")

    setLogLevel("info")
    net = build()
    net.start()
    start_services(net)
    cause, symptom = SCENARIOS[name](net)

    if mystery:
        with open(ANSWER_FILE, "w") as f:
            f.write(f"{name}: {cause}\n")
        info("*** Mystery fault injected. Diagnose it, then run: sudo python3 lab.py --reveal\n")
    else:
        info(f"*** Scenario: {name}\n")
    if args.hint:
        info(f"*** Symptom: {symptom}\n")
    if not mystery and name != "healthy":
        info("*** (cause hidden until you exit; shown below on exit)\n")

    CLI(net)
    if not mystery:
        info(f"*** Cause was: {cause}\n")
    net.stop()


if __name__ == "__main__":
    main()
