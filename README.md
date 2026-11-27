# 光猫桥接改造与故障排查实战教程

以 **ZTE ZXHN G7615AV5**（GPON ONT）为例，讲一套可复用的方法：怎么判断桥接是否改干净、怎么定位「WiFi 已连接但无互联网 / 无 DNS 解析」、怎么在动手前备份、怎么在改坏后恢复出厂。

**主角只有光猫**。主路由（任何品牌）、手机、终端都不在教程范围内——它们只是故障的现象放大器，不是原因。

**第一次来请先读 [00-full-walkthrough.md](docs/00-full-walkthrough.md)**：那一篇按真实顺序讲清了「我们做了什么、哪里走错了、最后靠什么定案」，后面 01~09 是可按需查阅的分章手册。

---

## 适用场景

```
运营商光纤 ── 光猫(桥接, VLAN 改写) ── 主路由(PPPoE 拨号) ── 终端
                 192.168.1.1                 192.168.x.1
                 仅管理用                     终端网段
```

判断标准：

- 光猫**不拨号**：没有 `pppd` 进程，没有 `ppp0` 接口
- 主路由**拨号成功**：拿到公网地址，DNS 指向公共 DNS
- 光猫**不做 DHCP / DNS / RA**：LAN 侧只透传二层帧

只要有一项不满足，就会出现「有网但解析不了」或「连上 WiFi 但无互联网」。

---

## 教程目录

| 文档 | 内容 |
|---|---|
| [00-full-walkthrough.md](docs/00-full-walkthrough.md) | **完整实战复盘**：从症状、弯路、A/B 定案到修复验证的总路线图 |
| [01-principles.md](docs/01-principles.md) | 桥接的四个硬性条件，故障为什么会表现为「无 DNS」 |
| [02-prepare.md](docs/02-prepare.md) | 动手前准备：telnet、备份、物理接触条件 |
| [03-old-modem-reference.md](docs/03-old-modem-reference.md) | **从能用的旧光猫读取哪些信息**，建立 A/B 参照 |
| [04-audit.md](docs/04-audit.md) | 逐项审计新光猫：五类常见残留 |
| [05-fix.md](docs/05-fix.md) | 修复手册：命令、持久化、重启、回滚 |
| [06-verify.md](docs/06-verify.md) | 验证方法：DNS 探针、DHCP 探针、监听排查 |
| [07-reset.md](docs/07-reset.md) | 重置与恢复出厂：软重置、硬件长按、远程重置 |
| [08-firmware-analysis.md](docs/08-firmware-analysis.md) | 固件整体转储 + Ghidra 反编译工具链 |
| [09-publish-checklist.md](docs/09-publish-checklist.md) | 发布前脱敏扫描清单 |
| [10-itms-dns-hijack.md](docs/10-itms-dns-hijack.md) | **最终定案**：ITMS 未注册导致 DNS 全量劫持的判定与修复 |
| [11-enable-telnet.md](docs/11-enable-telnet.md) | **telnet 默认关闭时怎么开**：所需材料、工厂模式、固化与验证 |
| [tools/](tools/) | 探测、转储、监测、扫描、开 telnet 脚本 |

---

## 快速结论

**首先排查**：主路由能拨号拿公网 IP、但所有域名都解析成光猫管理地址时，先查 **ITMS 注册状态**（`sendcmd 1 DB p PDTCTUSERINFO`，`Status=99` 即未注册）。这是本次故障的真正根因，详见 [10-itms-dns-hijack.md](docs/10-itms-dns-hijack.md)，一键修复 `tools/fix_itms_dns.py`。

桥接模式下最容易漏掉的五件事：

1. **DNS 劫持**：向光猫查任何域名（包括不存在的）都返回 `192.168.1.1` —— 优先排除 ITMS 未注册，再查强制门户行为
2. **DHCP 没关**：光猫在 LAN 侧继续发 `192.168.1.x`，与主路由网段冲突
3. **IPv6 空前缀通告**：`Prefix="::" / PrefixLen=0 / Enable=1 / 有效期无限`，终端判定无互联网
4. **端口绑定错误**：绑到没插线的口，或绑了全部口
5. **连接是从 PPPoE 改的**：残留 `IsNAT=1` / `IsDefGW=1` / 账号密码

验证 DNS 劫持最快的办法：

```sh
python3 tools/probe_dns.py 192.168.1.1
```

查一个不存在的域名，正常应返回 `NXDOMAIN(rcode=3)`；如果 `rcode=0` 且有 A 记录，就是劫持。

---

## 固件素材

**[→ fw-guide-v1：脱敏固件素材](https://github.com/xiaolanzi1121/g7615av5-bridge-guide/releases/tag/fw-guide-v1)**

6 个固件分区 + rootfs 文件树 + 反编译产物 + 校验清单，170 MB / 3 分片。**不含任何账号、密码、序列号、MAC、公网 IP、provisioning 数据**；针对 21 个专属标识逐一扫描，命中数 0。脱敏方法与扫描脚本见 [09-publish-checklist.md](docs/09-publish-checklist.md)。

---

## 免责声明

- 改光猫有断网风险，**必须在能物理接触设备、能插拔网线的条件下操作**
- 恢复出厂会清 LOID / 注册信息，可能导致光猫无法重新注册，**先记录再动手**
- 本教程仅用于个人设备的故障排查与学习，固件镜像不可用于刷写其他设备
