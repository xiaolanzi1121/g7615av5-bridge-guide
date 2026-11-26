#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ZTE 光猫 telnet 客户端

光猫的 telnet 是裸 busybox shell，没有 expect。
命令发太快会丢，必须读到提示符才发下一条。

用法:
    from zte_telnet import Shell
    sh = Shell('192.168.1.1')
    sh.login(os.environ['ZTE_USER'], os.environ['ZTE_PASS'])
    print(sh.cmd('sendcmd 1 DB p WANC'))
    sh.close()
"""
import os
import socket
import time


class Shell:
    def __init__(self, host="192.168.1.1", port=23, timeout=8):
        self.s = socket.create_connection((host, port), timeout=timeout)
        self.s.settimeout(0.5)
        self.buf = b""

    def _read_more(self, timeout=1.0):
        self.s.settimeout(timeout)
        try:
            chunk = self.s.recv(8192)
            if chunk:
                self.buf += chunk
                return chunk
        except socket.timeout:
            pass
        return b""

    def read_until(self, marker, total_timeout=6.0):
        start = time.time()
        while marker not in self.buf and time.time() - start < total_timeout:
            self._read_more(0.4)
        idx = self.buf.find(marker)
        if idx >= 0:
            out = self.buf[: idx + len(marker)]
            self.buf = self.buf[idx + len(marker):]
        else:
            out = self.buf
            self.buf = b""
        return out

    def login(self, user, pwd):
        self.read_until(b"ogin:", 8)        # Login:
        self.s.sendall(user.encode() + b"\r\n")
        self.read_until(b"assword:", 8)     # Password:
        self.s.sendall(pwd.encode() + b"\r\n")
        return self.read_until(b"#", 8)

    def cmd(self, c, timeout=4.0):
        self._read_more(0.15)               # 清空残留
        self.s.sendall(c.encode() + b"\r\n")
        r = self.read_until(b"# ", timeout)
        if b"# " not in r:                  # 兜底再等一次
            r += self.read_until(b"# ", 2.0)
        return r.decode(errors="replace")

    def close(self):
        try:
            self.s.close()
        except Exception:
            pass


def connect(host=None, user=None, pwd=None):
    """从环境变量取默认凭据"""
    host = host or os.environ.get("ZTE_HOST", "192.168.1.1")
    user = user or os.environ.get("ZTE_USER", "root")
    pwd = pwd if pwd is not None else os.environ.get("ZTE_PASS", "")
    if not pwd:
        raise SystemExit("请设置 ZTE_PASS 环境变量")
    sh = Shell(host)
    sh.login(user, pwd)
    return sh


if __name__ == "__main__":
    import sys
    sh = connect()
    for c in sys.argv[1:] or ["cat /proc/uptime"]:
        print("\n##### CMD:", c)
        print(sh.cmd(c, 6.0))
    sh.close()
