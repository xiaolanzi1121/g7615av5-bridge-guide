#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
DNS 探针 —— 识别本地劫持

核心思路: 查一个**绝对不存在**的域名。
  正常 DNS -> NXDOMAIN (rcode=3)，无 A 记录
  被劫持   -> rcode=0，返回一个具体 IP

用法:
    python3 probe_dns.py 192.168.1.1
    python3 probe_dns.py 192.168.1.1 --iface en5
    python3 probe_dns.py 192.168.1.1 223.5.5.5

注意: 不走系统代理。macOS 上可用 --iface 绑定物理网卡，
      避免查询被代理隧道接管。
"""
import argparse
import random
import socket
import struct
import sys

# macOS 的 IP_BOUND_IF
IP_BOUND_IF = 25

TEST_DOMAINS = [
    "www.baidu.com",
    "www.qq.com",
    "nonexistent-xyz-12345.com",   # 不存在，用于识别劫持
]


def query(server, qname, timeout=3.0, iface=None):
    """返回 (rcode, [ip...], raw_answers)"""
    qid = random.randint(1, 65535)
    hdr = struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0)
    qn = b"".join(bytes([len(p)]) + p.encode() for p in qname.split(".")) + b"\x00"
    pkt = hdr + qn + struct.pack("!HH", 1, 1)

    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    if iface:
        try:
            s.setsockopt(socket.IPPROTO_IP, IP_BOUND_IF, socket.if_nametoindex(iface))
        except Exception as e:
            print(f"  ! 绑定接口 {iface} 失败: {e}", file=sys.stderr)

    try:
        s.sendto(pkt, (server, 53))
        data, _ = s.recvfrom(2048)
    except socket.timeout:
        return None, [], "TIMEOUT"
    except Exception as e:
        return None, [], f"ERR:{e}"
    finally:
        s.close()

    rcode = data[3] & 0x0F
    ancount = struct.unpack("!H", data[6:8])[0]

    # 跳过问题段
    i = 12
    while i < len(data) and data[i] != 0:
        i += data[i] + 1
    i += 5

    ips = []
    for _ in range(ancount):
        if i + 12 > len(data):
            break
        # 跳过 name
        while i < len(data) and data[i] != 0:
            if data[i] & 0xC0 == 0xC0:
                i += 2
                break
            i += data[i] + 1
        else:
            i += 1
        if i + 10 > len(data):
            break
        typ, cls, ttl, dl = struct.unpack("!HHIH", data[i:i + 10])
        i += 10
        if typ == 1 and dl == 4:
            ips.append(".".join(str(b) for b in data[i:i + 4]))
        i += dl

    return rcode, ips, "OK"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("servers", nargs="+", help="DNS 服务器地址")
    ap.add_argument("--iface", help="绑定网卡，如 en5")
    ap.add_argument("--domain", action="append", help="自定义查询域名")
    args = ap.parse_args()

    domains = args.domain or TEST_DOMAINS

    for server in args.servers:
        print(f"\n=== {server} " + (f"(via {args.iface})" if args.iface else "") + " ===")
        hijacked = 0
        answered = 0
        for dom in domains:
            rcode, ips, status = query(server, dom, iface=args.iface)
            if status != "OK":
                print(f"  {dom:32s} -> {status}")
                continue
            answered += 1
            tag = ""
            if ips:
                tag = "  ips=" + ",".join(ips)
                if ips == ["192.168.1.1"]:
                    tag += "   <<< 指向光猫自身"
            else:
                tag = "  无A记录"
            if rcode == 3:
                tag += "  (NXDOMAIN，正常)"
            print(f"  {dom:32s} -> rcode={rcode}{tag}")

            # 判定：不存在的域名却返回 A 记录 = 劫持
            if "nonexistent" in dom and ips:
                hijacked += 1

        if hijacked:
            print("  ⚠ 判定: 劫持 —— 不存在的域名返回了 A 记录")
        elif answered:
            print("  ✓ 判定: 正常")


if __name__ == "__main__":
    main()
