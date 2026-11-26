#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络状态采样器 —— 抓「断网那一刻」的现场

每次运行采一行 CSV。适合 crontab / launchd 每分钟跑一次。
只测通用指标：网关可达性、公共 DNS、公共 IP 的 HTTPS、DNS 劫持特征。
不依赖任何特定品牌的路由器 API。

用法:
    python3 net_watch.py                    # 采样一次
    python3 net_watch.py --loop 60          # 每 60 秒采样
    python3 net_watch.py --gw 192.168.1.1   # 指定光猫管理地址

输出: net_watch.csv（追加）
"""
import argparse
import csv
import os
import random
import socket
import struct
import subprocess
import sys
import time

GW = "192.168.1.1"
PUBLIC_DNS = "223.5.5.5"
PROBE_DOMAIN = "www.baidu.com"
FAKE_DOMAIN = "nonexistent-xyz-12345.com"
CSV_PATH = os.environ.get("NET_WATCH_CSV", "net_watch.csv")
FIELDS = ["ts", "gw_ping", "dns_public", "dns_hijack", "https4", "https6", "note"]


def run(cmd, timeout=6):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except Exception:
        return ""


def dns_query(server, name, timeout=3):
    """发一个原始 UDP DNS A 查询，返回 (rcode, [IP])。"""
    tid = random.randint(0, 65535)
    pkt = struct.pack("!HHHHHH", tid, 0x0100, 1, 0, 0, 0)
    for part in name.split("."):
        pkt += bytes([len(part)]) + part.encode()
    pkt += b"\x00" + struct.pack("!HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    try:
        s.sendto(pkt, (server, 53))
        d, _ = s.recvfrom(2048)
    except Exception:
        return "TIMEOUT", []
    finally:
        s.close()
    rcode = d[3] & 0x0F
    ancount = struct.unpack("!H", d[6:8])[0]
    i = 12
    while i < len(d) and d[i] != 0:
        i += d[i] + 1
    i += 5
    ips = []
    for _ in range(ancount):
        if i + 10 > len(d):
            break
        while i < len(d) and d[i] != 0:
            if d[i] & 0xC0 == 0xC0:
                i += 2
                break
            i += d[i] + 1
        else:
            i += 1
        if i + 10 > len(d):
            break
        typ, cls, ttl, dl = struct.unpack("!HHIH", d[i:i + 10])
        i += 10
        if typ == 1 and dl == 4:
            ips.append(".".join(str(b) for b in d[i:i + 4]))
        i += dl
    return rcode, ips


def sample(gw):
    row = {"ts": time.strftime("%Y-%m-%d %H:%M:%S")}
    p = subprocess.run(["ping", "-c", "1", "-W", "800", gw], capture_output=True)
    row["gw_ping"] = "0" if p.returncode == 0 else "1"

    rc, ips = dns_query(PUBLIC_DNS, PROBE_DOMAIN)
    row["dns_public"] = f"{rc}/{','.join(ips[:2]) or '-'}"

    rc, ips = dns_query(gw, FAKE_DOMAIN)
    row["dns_hijack"] = "YES" if (rc == 0 and ips) else "no"

    for fam, key in (("-4", "https4"), ("-6", "https6")):
        out = run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                   "--noproxy", "*", fam, "--max-time", "6",
                   "https://" + PROBE_DOMAIN])
        row[key] = out or "000"

    notes = []
    if row["dns_hijack"] == "YES":
        notes.append("gateway_dns_hijack")
    if row["gw_ping"] == "1":
        notes.append("gateway_unreachable")
    if row["https4"] == "000" and row["https6"] == "000":
        notes.append("no_internet")
    row["note"] = ",".join(notes)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gw", default=GW)
    ap.add_argument("--loop", type=int, default=0, help="间隔秒数，0 表示只采一次")
    a = ap.parse_args()

    new = not os.path.exists(CSV_PATH)
    while True:
        row = sample(a.gw)
        with open(CSV_PATH, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if new:
                w.writeheader()
                new = False
            w.writerow(row)
        print(f"{row['ts']}  gw={row['gw_ping']} dns={row['dns_public']} "
              f"hijack={row['dns_hijack']} v4={row['https4']} v6={row['https6']} "
              f"{row['note']}")
        if not a.loop:
            break
        time.sleep(a.loop)


if __name__ == "__main__":
    main()
