#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫描固件转储里的设备专属/涉密字符串。用法: python3 scan_secrets.py <目录>"""
import sys, os, re, gzip, tarfile

# 已知来自本次设备的专属标识（原文不入库，仅用于本地扫描）
# 设备专属标识不要写进脚本。用 --patterns-file 从本地文件读（该文件不要提交）。
KNOWN = []
# 通用模式：手机号 / 长数字串（序列号、LOID）/ MAC / 公网 IP
PATTERNS = [
    ("phone", re.compile(rb"(?<!\d)1[3-9]\d{9}(?!\d)")),
    ("longnum", re.compile(rb"(?<!\d)\d{12,}(?!\d)")),
    ("mac", re.compile(rb"(?<![0-9a-fA-F:])(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}(?![0-9a-fA-F:])")),
    ("ztesn", re.compile(rb"ZTEG[0-9A-F]{6,12}")),
    ("cmcc", re.compile(rb"CMCC-(?!(?:QLINK|GUIDE-LINK|SMARTAOSNET-LINK))[A-Za-z0-9_-]{3,}")),
]

ASCII_RUN = re.compile(rb"[\x20-\x7e]{6,}")
# 协议保留地址 / 测试填充，不是任何设备的身份信息
IGNORE = {
    b"ff:ff:ff:ff:ff:ff", b"FF:FF:FF:FF:FF:FF",
    b"01:80:c2:00:00:00", b"01:02:03:04:05:06",
    b"00:00:00:00:00:00", b"12:34:56:78:9A:BC", b"12:34:56:78:9a:bc",
}

def scan_bytes(d):
    """只在可打印 ASCII 串里匹配，避免二进制随机字节/tar 头造成误报。"""
    hits = {}
    for k in KNOWN:
        n = d.count(k)
        if n:
            hits[k.decode("utf-8", "replace")] = n
    for run in ASCII_RUN.findall(d):
        for name, pat in PATTERNS:
            m = pat.findall(run)
            if m:
                # 过滤固件构建时间戳（YYYYMMDDHHMMSS）和全零 MAC 占位符
                m = [x for x in m
                     if not re.fullmatch(rb"(?:19|20)\d{12}", x)
                     and x.lower() not in IGNORE
                     and not re.fullmatch(rb"0{12,}", x)
                     and not re.fullmatch(rb"(\d)\1{11,}", x)
                     and not re.fullmatch(rb"1[3-9]\d{12}", x)
                     and not re.search(rb"0123456789", x)
                     and not re.search(rb"98776655", x)]
                if m:
                    vals = sorted(set(x.decode("utf-8", "replace") for x in m))
                    k = name + ":" + ",".join(vals[:4])
                    hits[k] = hits.get(k, 0) + len(m)
    return hits

def stream_scan(fh):
    """流式扫描，保留 64 字节重叠避免跨块漏匹配。"""
    hits = {}
    tail = b""
    while True:
        b = fh.read(1 << 20)
        if not b:
            break
        d = tail + b
        for k, v in scan_bytes(d).items():
            hits[k] = hits.get(k, 0) + v
        tail = d[-64:]
    return hits

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("root")
    ap.add_argument("--patterns-file", help="本地机密串清单，每行一个（不要提交）")
    a = ap.parse_args()
    root = a.root
    if a.patterns_file:
        for line in open(a.patterns_file, encoding="utf-8"):
            line = line.strip().encode()
            if line:
                KNOWN.append(line)
    print(f"扫描目录: {root}\n")
    total_bad = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in (".git", "__pycache__")]
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            if fn.endswith((".tgz", ".tar.gz")):
                h = {}
                try:
                    with tarfile.open(p, "r:gz") as tf:
                        for m in tf:
                            if m.isfile() and m.size < 20_000_000:
                                f = tf.extractfile(m)
                                if f:
                                    for k, v in stream_scan(f).items():
                                        h[k] = h.get(k, 0) + v
                except Exception as e:
                    print(f"  !! {rel}: {e}")
                    continue
            elif fn.endswith(".gz"):
                try:
                    with gzip.open(p, "rb") as fh:
                        h = stream_scan(fh)
                except Exception as e:
                    print(f"  !! {rel}: {e}")
                    continue
            elif fn.endswith(".tar"):
                h = {}
                try:
                    with tarfile.open(p) as tf:
                        for m in tf:
                            if m.isfile() and m.size < 8_000_000:
                                f = tf.extractfile(m)
                                if f:
                                    for k, v in stream_scan(f).items():
                                        h[k] = h.get(k, 0) + v
                except Exception as e:
                    print(f"  !! {rel}: {e}")
                    continue
            else:
                try:
                    with open(p, "rb") as fh:
                        h = stream_scan(fh)
                except Exception:
                    continue
            if h:
                total_bad += 1
                print(f"[命中] {rel}")
                for k, v in sorted(h.items(), key=lambda x: -x[1])[:8]:
                    print(f"        {k[:100]} x{v}")
    print(f"\n命中文件数: {total_bad}")

if __name__ == "__main__":
    main()
