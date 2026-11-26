#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从光猫批量转储分区到本机

前提:
    1. 本机已启动接收服务: python3 fw_recv.py 8000
    2. 设置了 ZTE_PASS 环境变量
    3. 光猫能访问本机（同网段直连）

用法:
    python3 dump_partitions.py --recv 192.168.1.18:8000 13:rootfs2 5:usercfg 7:kernel1
    python3 dump_partitions.py --recv 192.168.1.18:8000 --all

注意: 活动 rootfs 的判断方法见 docs/07-firmware-dump.md
      （对照 df 的容量，不要猜）
"""
import argparse
import time
from zte_telnet import connect

# mtd 编号 : 分区名
ALL_PARTS = [
    (1, "uboot"), (3, "paramtags"), (4, "wlan"), (5, "usercfg"),
    (6, "middle"), (7, "kernel1"), (8, "kernel2"), (9, "osgi1"),
    (10, "osgi2"), (11, "plugin"), (12, "rootfs1"), (13, "rootfs2"),
]


def dump(sh, recv, mtd, name):
    url = f"http://{recv}/mtd{mtd}_{name}.bin.gz"
    cmd = (
        f"dd if=/dev/mtdblock{mtd} bs=65536 2>/dev/null | gzip -1 | "
        f"curl -s -T - {url}; echo DONE_$?"
    )
    print(f">>> mtd{mtd} {name}", flush=True)
    t0 = time.time()
    out = sh.cmd(cmd, 1200)
    ok = "DONE_0" in out
    print(f"<<< {'OK ' if ok else 'FAIL'} {time.time()-t0:.1f}s  {out.strip()[-100:]}", flush=True)
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recv", required=True, help="接收端地址 IP:PORT")
    ap.add_argument("targets", nargs="*", help="形如 13:rootfs2")
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()

    jobs = ALL_PARTS if args.all else []
    for t in args.targets:
        mtd, name = t.split(":", 1)
        jobs.append((int(mtd), name))
    if not jobs:
        ap.error("请指定分区，或用 --all")

    sh = connect()
    ok = 0
    for mtd, name in jobs:
        if dump(sh, args.recv, mtd, name):
            ok += 1
    sh.close()
    print(f"\n完成 {ok}/{len(jobs)}")


if __name__ == "__main__":
    main()
