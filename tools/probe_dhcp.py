#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DHCP 探针 —— 验证设备是否还在分配地址

关键: 必须绑定到目标网卡。
      否则广播会走默认路由，被同网段的其他 DHCP 服务器（如路由器）应答，
      导致误判。

用法:
    sudo python3 probe_dhcp.py --iface en5
    python3 probe_dhcp.py --iface en5 --timeout 8

判定:
    收到 yiaddr=192.168.1.x  -> 光猫仍在分配
    超时无回复               -> 已停止
"""
import argparse
import random
import socket
import struct
import sys
import time

IP_BOUND_IF = 25


def build_discover(mac=b"\xc8\x4d\x44\x20\x39\xd0"):
    xid = random.randint(1, 0xFFFFFFFF)
    pkt = struct.pack(
        "!BBBBIHH4s4s4s4s16s64s128s",
        1, 1, 6, 0, xid, 0, 0x8000,          # op,htype,hlen,hops,xid,secs,flags
        b"\0" * 4, b"\0" * 4, b"\0" * 4, b"\0" * 4,   # ciaddr..giaddr
        mac + b"\0" * 10,                    # chaddr
        b"\0" * 64, b"\0" * 128,
    )
    pkt += b"\x63\x82\x53\x63"               # magic cookie
    pkt += bytes([53, 1, 1])                 # DHCP Message Type = DISCOVER
    pkt += bytes([55, 4, 1, 3, 6, 15])       # Parameter Request List
    pkt += bytes([255])                      # END
    return pkt


def parse_reply(data):
    if len(data) < 240:
        return None
    yiaddr = ".".join(str(b) for b in data[16:20])
    siaddr = ".".join(str(b) for b in data[20:24])
    return {"yiaddr": yiaddr, "siaddr": siaddr}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", required=True, help="网卡名，如 en5")
    ap.add_argument("--timeout", type=float, default=8.0)
    ap.add_argument("--port", type=int, default=68, help="本地端口（需要 root）")
    args = ap.parse_args()

    try:
        idx = socket.if_nametoindex(args.iface)
    except OSError:
        print(f"网卡不存在: {args.iface}")
        sys.exit(1)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    s.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, idx)
    try:
        s.bind(("0.0.0.0", args.port))
    except PermissionError:
        print(f"绑定端口 {args.port} 需要 root 权限，请用 sudo")
        sys.exit(1)

    s.sendto(build_discover(), ("255.255.255.255", 67))
    print(f"从 {args.iface} 发出 DHCP DISCOVER，等待 {args.timeout}s ...")

    s.settimeout(1.0)
    t0 = time.time()
    got = False
    while time.time() - t0 < args.timeout:
        try:
            data, addr = s.recvfrom(1024)
        except socket.timeout:
            continue
        info = parse_reply(data)
        if not info:
            continue
        got = True
        print(f"  回复 from {addr[0]}  yiaddr={info['yiaddr']}  server={info['siaddr']}")
        if info["yiaddr"].startswith("192.168."):
            print("  ⚠ 仍在分配地址")

    if not got:
        print("  ✓ 无任何回复 —— DHCP 已停止服务")
    s.close()


if __name__ == "__main__":
    main()
