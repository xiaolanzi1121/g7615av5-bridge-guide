#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP PUT 接收服务 —— 用于从光猫拉取分区/文件

光猫没有 nc/tftp/scp，但有 curl。
光猫侧:
    dd if=/dev/mtdblock13 bs=65536 | gzip -1 | \\
        curl -s -T - http://<本机IP>:8000/mtd13_rootfs2.bin.gz

用法:
    python3 fw_recv.py 8000
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_PUT(self):
        name = os.path.basename(self.path.lstrip("/")) or "upload.bin"
        total = int(self.headers.get("Content-Length", 0))
        done = 0
        try:
            with open(name, "wb") as f:
                remain = total
                while remain > 0:
                    chunk = self.rfile.read(min(65536, remain))
                    if not chunk:
                        break
                    f.write(chunk)
                    remain -= len(chunk)
                    done = total - remain
                    if total and done % (20 * 1024 * 1024) < 65536:
                        pct = done * 100 // total
                        print(f"\r  {name}: {done/1048576:.1f}MB / {total/1048576:.1f}MB ({pct}%)", end="", flush=True)
            print(f"\r  {name}: {done/1048576:.1f}MB 完成" + " " * 20)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception as e:
            print(f"\n  写入失败: {e}")
            self.send_response(500)
            self.end_headers()

    def do_GET(self):
        # 健康检查
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ready")

    def log_message(self, fmt, *args):
        pass  # 静默，避免刷屏


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    srv = HTTPServer(("0.0.0.0", port), Handler)
    print(f"接收服务已启动: http://0.0.0.0:{port}")
    print(f"光猫侧测试: curl -s http://<本机IP>:{port}/")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n停止")


if __name__ == "__main__":
    main()
