# Mininet Diagnosis Lab: Usage

Run from a Linux VM or WSL2 environment with Mininet and Open vSwitch installed.

```bash
sudo python3 lab.py --check                 # confirm the healthy lab works
sudo python3 lab.py --scenario healthy      # explore the baseline
sudo python3 lab.py --scenario wrong_gateway --hint
sudo python3 lab.py --scenario mystery      # random fault; cause stays hidden
python3 lab.py --reveal                     # reveal the previous mystery cause
```

Inside `mininet>`, prefix each command with a node name:

```text
h1 ping -c3 10.0.2.10
h1 curl -m5 http://10.0.2.10/
r1 ip route
web ss -tlnp
```

## Scenarios

| Scenario | What breaks | Fast first check |
|---|---|---|
| `healthy` | Nothing | `h1 ping -c3 10.0.2.10` |
| `wrong_gateway` | h1's default gateway | `h1 ip route` |
| `no_forwarding` | Routing through r1 | `r1 sysctl net.ipv4.ip_forward` |
| `firewall_drop` | HTTP silently times out | `web iptables -L -n -v` |
| `firewall_reject` | HTTP is reset/refused | `web iptables -L -n -v` |
| `service_down` | Web server is stopped | `web ss -tlnp` |
| `high_latency_loss` | Slow, lossy replies | `web tc qdisc show` |
| `bandwidth_limit` | Downloads are capped | `web tc qdisc show` |
| `mtu_blackhole` | Large transfers stall | `h1 ping -M do -s 1472 -c3 10.0.2.10` |
| `duplicate_ip` | h1 intermittently loses connectivity | `h1 ip neigh` |
| `link_down` | Server-side link is down | `r1 ip -br link` |

For a repeatable mystery exercise, copy the replay command printed at startup, or choose one yourself:

```bash
sudo python3 lab.py --scenario mystery --seed 42
```

If a crashed session leaves Mininet state behind, clean it up before retrying:

```bash
sudo mn -c
```
