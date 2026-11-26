#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修复中兴光猫「ITMS 未注册导致 DNS 被劫持」

现象：
    光猫桥接、路由器 PPPoE 正常拿到公网 IP，但所有域名都被解析成 192.168.1.1
    （TTL 3600）。换任何路由器、重启光猫都无效。TCP/53、IPv6 DNS、DoH 却正常。

原理：
    中兴方案固件在 ITMS 未注册（PDTCTUSERINFO.Status=99）时，会在内核里启用
    DNS 劫持，对本机 PPPoE 路径上的 IPv4 UDP/53 查询直接伪造应答，指向光猫 LAN IP。
    同一固件在已注册（Status=0）状态下不会启用该逻辑。

修复：
    sendcmd 1 DB set PDTCTUSERINFO 0 Status 0
    sendcmd 1 DB set PDTCTUSERINFO 0 Result 1
    sendcmd 1 DB save
    reboot                     # 该标志由内核模块在启动时读取，必须重启才生效

用法：
    export ZTE_PASS='<telnet密码>'
    python3 fix_itms_dns.py --check      # 只查看当前状态
    python3 fix_itms_dns.py              # 写入并重启
    python3 fix_itms_dns.py --no-reboot  # 只写入，稍后自己重启
"""
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from zte_telnet import connect  # noqa: E402

FIELD = re.compile(r'<DM name="(Status|Result)" val="([^"]*)"')


def read_status(sh):
    out = sh.cmd("sendcmd 1 DB p PDTCTUSERINFO", 6.0)
    vals = dict(FIELD.findall(out))
    return vals.get("Status"), vals.get("Result")


def main():
    check_only = "--check" in sys.argv
    no_reboot = "--no-reboot" in sys.argv

    sh = connect()
    status, result = read_status(sh)
    print("当前 PDTCTUSERINFO: Status=%s Result=%s" % (status, result))

    ok = status == "0" and result == "1"
    if ok:
        print("ITMS 已标记为注册成功，DNS 劫持不应发生。")
        if check_only:
            sh.close()
            return 0
    elif check_only:
        print("→ ITMS 处于未注册状态，这就是 DNS 被劫持到 192.168.1.1 的原因。")
        print("  运行不带 --check 的本脚本即可修复。")
        sh.close()
        return 1
    else:
        print("→ 标记为已注册 ...")
        for cmd in (
            "sendcmd 1 DB set PDTCTUSERINFO 0 Status 0",
            "sendcmd 1 DB set PDTCTUSERINFO 0 Result 1",
            "sendcmd 1 DB save",
        ):
            sh.cmd(cmd, 6.0)
        status, result = read_status(sh)
        print("写入后: Status=%s Result=%s" % (status, result))
        if status != "0" or result != "1":
            print("写入未生效，请检查权限或表名。")
            sh.close()
            return 2

    if no_reboot:
        print("\n已保存。请手动重启光猫后生效。")
        sh.close()
        return 0

    print("\n重启光猫以让内核模块重读该标志 ...")
    try:
        sh.cmd("reboot", 3.0)
    except Exception:
        pass  # 重启会断开 telnet，属正常
    sh.close()

    print("等待光猫重新上线 ...")
    for i in range(40):
        time.sleep(3)
        if os.system("ping -c1 -t1 -W1000 192.168.1.1 >/dev/null 2>&1") == 0:
            print("光猫已上线（约 %d 秒）" % ((i + 1) * 3))
            print("\n请验证：nslookup www.baidu.com 223.5.5.5")
            print("返回真实公网地址即修复成功；仍为 192.168.1.1 则需检查 Status 是否被平台改回 99。")
            return 0
    print("光猫未在 120 秒内响应，请检查指示灯或手动 ping 192.168.1.1。")
    return 3


if __name__ == "__main__":
    sys.exit(main())
