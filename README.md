# Mininet Network Diagnosis Lab

## Setup (Ubuntu/Debian, VM or WSL2 with a real kernel; not plain Docker)

    sudo apt update
    sudo apt install -y mininet openvswitch-switch tcpdump iperf3 curl traceroute mtr-tiny dnsutils iproute2 iptables
    sudo systemctl enable --now openvswitch-switch
    sudo mn --test pingall        # sanity check
    sudo mn -c                    # clean up after a crashed run

## Topology

```mermaid
graph LR
    subgraph LAN["LAN — 10.0.1.0/24"]
        h1["h1<br/>10.0.1.11/24<br/>default via 10.0.1.1"]
        h2["h2<br/>10.0.1.12/24<br/>default via 10.0.1.1"]
        s1(["s1"])
    end

    r1["r1 — Linux router<br/>eth1: 10.0.1.1/24<br/>eth2: 10.0.2.1/24"]

    subgraph SRV["Server — 10.0.2.0/24"]
        s2(["s2"])
        web["web<br/>10.0.2.10/24<br/>HTTP :80 · /big.bin 2 MB"]
    end

    h1 --- s1
    h2 --- s1
    s1 --- r1
    r1 --- s2
    s2 --- web
```

## Run

    sudo python3 lab.py --list
    sudo python3 lab.py --scenario healthy          # learn the baseline first
    sudo python3 lab.py --scenario wrong_gateway --hint
    sudo python3 lab.py --scenario mystery          # random, cause hidden
    sudo python3 lab.py --reveal                    # check your answer afterwards

In the `mininet>` prompt prefix a command with the node name: `h1 ping -c3 10.0.2.10`.
`xterm h1 r1` opens real terminals (needs X). `h1 tcpdump ...` works too; use `&` to background.

## Diagnosis method: bottom-up

| Layer | Question | Commands (run on the node) |
|---|---|---|
| Link | Is the interface up? | `ip -br link`, `ip -s link show dev h1-eth0` (errors/drops) |
| Address | Right IP/mask? Duplicates? | `ip -br addr`, `arping -D -I h1-eth0 10.0.1.11` |
| L2 | Does ARP resolve? | `ip neigh`, `arping -c3 10.0.1.1`, `tcpdump -n -i h1-eth0 arp` |
| Gateway | Right default route? | `ip route`, `ip route get 10.0.2.10` |
| L3 | Reach local, gateway, remote? | `ping -c3 10.0.1.1` then `ping -c3 10.0.2.10` (work outwards) |
| Path | Where does it stop? | `traceroute -n 10.0.2.10`, `mtr -n -r -c10 10.0.2.10` |
| Router | Is it forwarding? | `r1 sysctl net.ipv4.ip_forward`, `r1 ip route`, `r1 iptables -S` |
| MTU | Do big packets die? | `ping -M do -s 1472 -c3 10.0.2.10`, `tracepath -n 10.0.2.10` |
| L4 | Port open/filtered? | `ss -tlnp` (on server), `curl -v -m5 http://10.0.2.10/`, `nc -zv -w3 10.0.2.10 80` |
| Firewall | Rules/counters? | `iptables -S`, `iptables -L -n -v` (watch packet counters) |
| Perf | Latency/loss/throughput? | `ping -c20`, `iperf3 -s` on web + `iperf3 -c 10.0.2.10`, `tc qdisc show` |
| Capture | What is on the wire? | `tcpdump -n -i r1-eth1 host 10.0.2.10`, `tcpdump -n -i any icmp` |

## Reading the symptoms

- **Destination Host Unreachable from the gateway**: L2/L3 problem on the far side of that router.
- **Destination Host Unreachable from yourself**: ARP failing (nothing answered).
- **Timeout** (no reply, no error): silent drop, so suspect DROP firewall, no route back, or forwarding off.
- **Connection refused** (instant): host reachable, nothing listening or REJECT rule.
- **Handshake OK, big transfer stalls**: MTU/PMTUD blackhole; test with `ping -M do -s`.
- **Slow but working**: `ping` stats for loss/jitter, `tc qdisc show`, `iperf3`.
- **Works sometimes**: duplicate IP or flapping; check `ip neigh` for changing MACs.

## Useful tricks

- Compare captures on both sides of the router (`r1-eth1` and `r1-eth2`) to see where packets vanish.
- `tcpdump -n -i r1-eth2 -w /tmp/r2.pcap`, then open it in Wireshark on the host.
- `iptables -L -n -v` counters tell you which rule is actually eating packets.
- Change things live: `h1 ip route replace default via 10.0.1.1`, `r1 sysctl -w net.ipv4.ip_forward=1`, `web iptables -F`, `web tc qdisc del dev web-eth0 root`.
- Add your own faults: edit `lab.py`, write a function and register it in `SCENARIOS`.

## Ideas to extend

1. Add a second router and a static-route misconfiguration (asymmetric routing).
2. Add DNS with `dnsmasq` on a node and break resolution (`dig @10.0.2.53 web.lab`).
3. Add VLANs/OVS flows, or a NAT router with `iptables -t nat -A POSTROUTING -j MASQUERADE`.
4. Script a checker that runs your diagnosis commands and compares to the answer.
