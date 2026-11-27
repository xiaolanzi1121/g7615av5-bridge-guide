# -*- coding: utf-8 -*-
"""zteOnu 的 Python 复刻 —— 通过 webFac 工厂模式接口开临时 Telnet。

原理（逆向自 github.com/Septrum101/zteOnu）：
  1. POST /webFac  "SendSq.gch"            复位工厂会话
  2. POST /webFac  "RequestFactoryMode.gch" 请求工厂模式
  3. POST /webFac  "SendSq.gch?rand=<秒>"   拿握手版本
       - 空 body      -> v1
       - "newrand=N"  -> v2（需先 SendInfo 上报客户端 MAC）
  4. key = (密钥池[偏移:偏移+24]) ^ 0xA5        AES-192-ECB
  5. v2: /webFacEntry  ECB("SendInfo.gch?info=12|" + magic(mac))
         magic = 6 个 MAC 字节在 v^1271 mod 2537 下的最小前像，各占 4 字节(2 数据+2 零)
  6. /webFacEntry  ECB("CheckLoginAuth.gch?&version61&user=U&pass=P")
         200 -> 认证通过；401 -> 账号或密码错
  7. /webFacEntry  ECB("FactoryMode.gch?mode=2&user=notused")
         解密得 "user=<临时账号>&pass=<临时密码>"

用法（凭据一律从命令行传入，脚本不含任何设备专属账号/口令）：
    python3 zte_factory.py -i <光猫管理IP> -p 80 -u <工厂用户名> -w '<工厂口令>' -m <本机网卡MAC>

注意：新固件的工厂接口通常在 80 端口；8080 多为僵尸空响应。
"""
import argparse, base64, http.cookiejar, os, re, socket, subprocess, sys, time
import urllib.error, urllib.parse, urllib.request

# ---------- 密钥池 ----------
AES_KEY_POOL = bytes([
    0x7B, 0x56, 0xB0, 0xF7, 0xDA, 0x0E, 0x68, 0x52, 0xC8, 0x19,
    0xF3, 0x2B, 0x84, 0x90, 0x79, 0xE5, 0x62, 0xF8, 0xEA, 0xD2,
    0x64, 0x93, 0x87, 0xDF, 0x73, 0xD7, 0xFB, 0xCC, 0xAA, 0xFE,
    0x75, 0x43, 0x1C, 0x29, 0xDF, 0x4C, 0x52, 0x2C, 0x6E, 0x7B,
    0x45, 0x3D, 0x1F, 0xF1, 0xDE, 0xBC, 0x27, 0x85, 0x8A, 0x45,
    0x91, 0xBE, 0x38, 0x13, 0xDE, 0x67, 0x32, 0x08, 0x54, 0x11,
    0x75, 0xF4, 0xD3, 0xB4, 0xA4, 0xB3, 0x12, 0x86, 0x67, 0x23,
    0x99, 0x4C, 0x61, 0x7F, 0xB1, 0xD2, 0x30, 0xDF, 0x47, 0xF1,
    0x76, 0x93, 0xA3, 0x8C, 0x95, 0xD3, 0x59, 0xBF, 0x87, 0x8E,
    0xF3, 0xB3, 0xE4, 0x76, 0x49, 0x88,
])
AES_KEY_POOL_NEW = bytes([
    0x8C, 0x23, 0x65, 0xD1, 0xFC, 0x32, 0x45, 0x37, 0x11, 0x28,
    0x71, 0x63, 0x07, 0x20, 0x69, 0x14, 0x73, 0xE7, 0xD4, 0x53,
    0x13, 0x24, 0x36, 0xC2, 0xB5, 0xE1, 0xFC, 0xCF, 0x8A, 0x9A,
    0x41, 0x89, 0x3C, 0x49, 0xCF, 0x5C, 0x72, 0x8C, 0x9E, 0xEB,
    0x75, 0x0D, 0x3F, 0xD1, 0xFE, 0xCC, 0x57, 0x65, 0x7A, 0x35,
    0x21, 0x3E, 0x68, 0x53, 0x7E, 0x97, 0x02, 0x48, 0x74, 0x71,
    0x95, 0x34, 0x53, 0x84, 0xB4, 0xC3, 0xE2, 0xD6, 0x27, 0x3D,
    0xE6, 0x5D, 0x72, 0x9C, 0xBC, 0x3D, 0x03, 0xFD, 0x76, 0xC1,
    0x9C, 0x25, 0xA8, 0x92, 0x47, 0xE4, 0x18, 0x0F, 0x24, 0x3F,
    0x4F, 0x67, 0xEC, 0x97, 0xF4, 0x99,
])

MOD = 2537
EXP = 1271


def power(w):
    w %= MOD
    acc, e = 1, EXP
    while e > 0:
        if e & 1:
            acc = acc * w % MOD
        w = w * w % MOD
        e >>= 1
    return acc & 0xFF


_BUCKETS = None


def _buckets():
    global _BUCKETS
    if _BUCKETS is None:
        b = {}
        for v in range(MOD):
            b.setdefault(power(v), []).append(v)
        _BUCKETS = b
    return _BUCKETS


def mac_to_magic(mac: bytes) -> bytes:
    bk = _buckets()
    vals = [bk[b][0] if bk.get(b) else 0 for b in mac] + [0] * 6
    out = bytearray()
    for v in vals[:11]:
        out += bytes([v & 0xFF, (v >> 8) & 0xFF, 0, 0])
    out += bytes([vals[11] & 0xFF, (vals[11] >> 8) & 0xFF])
    return bytes(out)


def get_key(version: int, r: int, newr: int = 0) -> bytes:
    if version == 2:
        idx = (((0x1000193 * r) & 0x3F) ^ newr) % 60
        pool = AES_KEY_POOL_NEW[idx:idx + 24]
    else:
        pool = AES_KEY_POOL[r:r + 24]
    return bytes((b ^ 0xA5) & 0xFF for b in pool)


def aes_ecb(data: bytes, key: bytes, decrypt=False) -> bytes:
    if len(data) % 16:
        if decrypt:
            data = data + b"\x00" * (16 - len(data) % 16)
        else:
            data = data + b"\x00" * (16 - len(data) % 16)
    alg = {16: "aes-128-ecb", 24: "aes-192-ecb", 32: "aes-256-ecb"}[len(key)]
    args = ["openssl", "enc", "-" + alg, "-K", key.hex(), "-nopad", "-nosalt"]
    if decrypt:
        args.append("-d")
    p = subprocess.run(args, input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("openssl: " + p.stderr.decode()[:200])
    return p.stdout


def local_mac_for(ip: str):
    """按路由查出到光猫所用的本机网卡 MAC（等价于 Go 版的 dialMAC）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect((ip, 53))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    out = subprocess.run(["ifconfig"], capture_output=True).stdout.decode("utf-8", "replace")
    cur, mac = None, None
    for line in out.splitlines():
        m = re.match(r"^([a-z0-9]+):", line)
        if m:
            cur = m.group(1)
            m2 = re.search(r"ether\s+([0-9a-f:]{17})", line)
            if m2:
                mac = m2.group(1)
            continue
        if f"inet {local_ip} " in line and cur and mac:
            return cur, bytes(int(x, 16) for x in mac.split(":"))
    return None, None


class Fac:
    def __init__(self, ip, port, user, pwd, mac=None):
        self.base = f"http://{ip}:{port}"
        self.user, self.pwd, self.mac = user, pwd, mac
        self.key = None
        cj = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    def post(self, path, body, raw=False):
        data = body if isinstance(body, bytes) else body.encode()
        r = urllib.request.Request(self.base + path, data=data)
        r.add_header("User-Agent", "Mozilla/5.0")
        try:
            with self.op.open(r, timeout=15) as x:
                return x.status, x.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            return -1, str(e).encode()

    def get(self, path):
        r = urllib.request.Request(self.base + path)
        r.add_header("User-Agent", "Mozilla/5.0")
        try:
            with self.op.open(r, timeout=15) as x:
                return x.status, x.read()
        except urllib.error.HTTPError as e:
            return e.code, e.read()
        except Exception as e:
            return -1, str(e).encode()

    def run(self):
        print("[0] 激活 web 服务 ...")
        print("    GET / ->", self.get("/")[0])

        st, b = self.post("/webFac", "SendSq.gch")
        print("[1] reset factory      ->", st, b[:60])

        st, b = self.post("/webFac", "RequestFactoryMode.gch")
        print("[2] request factory    ->", st, b[:60] or "(连接关闭=正常)")

        r = int(time.time()) % 60
        st, b = self.post("/webFac", f"SendSq.gch?rand={r}\r\n")
        body = b.decode("utf-8", "replace").strip()
        print(f"[3] sendSq rand={r}     -> {st} {body!r}")
        if st != 200:
            print("    !! 握手失败，设备可能不支持或已不在工厂模式")
            return None
        if "newrand" in body:
            ver = 2
            newr = int(body.split("newrand=")[1].strip() or 0)
            self.key = get_key(2, r, newr)
            print(f"    版本 v2, newrand={newr}, key={self.key.hex()}")
        elif body == "":
            ver = 1
            self.key = get_key(1, r, 0)
            print(f"    版本 v1, key={self.key.hex()}")
        else:
            print("    !! 未知响应")
            return None

        if ver == 2:
            if not self.mac:
                print("    !! v2 需要客户端 MAC，但没取到")
                return None
            payload = b"SendInfo.gch?info=12|" + mac_to_magic(self.mac)
            st, b = self.post("/webFacEntry", aes_ecb(payload, self.key))
            print(f"[4] SendInfo(mac={self.mac.hex()}) -> {st}")
            if st != 200:
                print("    !! SendInfo 被拒（MAC 不在白名单？）")
                return None

        cmd = f"CheckLoginAuth.gch?&version61&user={self.user}&pass={self.pwd}"
        st, b = self.post("/webFacEntry", aes_ecb(cmd.encode(), self.key))
        print(f"[5] CheckLoginAuth({self.user}) -> {st}")
        if st == 401:
            print("    !! 账号或密码错误 —— 这组凭据不被工厂模式接受")
            return None
        if st != 200:
            print(f"    !! 异常状态 {st} {b[:80]}")
            return None
        print("    ✓ 认证通过！")

        st, b = self.post("/webFacEntry", aes_ecb(b"FactoryMode.gch?mode=2&user=notused", self.key))
        print(f"[6] enter factory mode -> {st}")
        if st != 200:
            print(f"    !! 失败 {st} {b[:80]}")
            return None
        dec = aes_ecb(b, self.key, decrypt=True).rstrip(b"\x00").decode("utf-8", "replace")
        print("    解密结果:", repr(dec))
        q = urllib.parse.parse_qs(urllib.parse.urlparse(dec).query)
        tu = (q.get("user") or [""])[0]
        tp = (q.get("pass") or [""])[0]
        if tu and tp:
            print("\n===== 临时 Telnet 凭据 =====")
            print("  账号:", tu)
            print("  密码:", tp)
            print("  端口: 23")
            return tu, tp
        print("    !! 响应里没有凭据")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-u", "--user", default="factorymode",
                    help="工厂模式用户名（自行填入，脚本不含任何口令）")
    ap.add_argument("-p", "--pass", dest="pwd", default="",
                    help="工厂模式口令，必须通过命令行传入")
    ap.add_argument("-i", "--ip", default="192.168.1.1")
    ap.add_argument("--port", type=int, default=80,
                    help="工厂接口端口，新固件多为 80")
    ap.add_argument("-m", "--mac", default="",
                    help="本机直连网卡的真实 MAC，如 00:11:22:33:44:55（示例）")
    a = ap.parse_args()

    if a.mac:
        mac = bytes(int(x, 16) for x in a.mac.split(":"))
        iface = "-"
    else:
        iface, mac = local_mac_for(a.ip)
    print(f"目标 {a.ip}:{a.port}  本机网卡 {iface}  MAC {mac.hex(':') if mac else '未知'}")
    f = Fac(a.ip, a.port, a.user, a.pwd, mac)
    res = f.run()
    sys.exit(0 if res else 2)


if __name__ == "__main__":
    main()
