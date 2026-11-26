# 00 · 完整实战复盘：从「WiFi 无互联网」到锁定光猫

> 这一篇是整套教程的**总路线图**。其他章节是工具手册，这一篇讲的是：我们当时面对的是什么、哪些判断被证伪、最后靠什么证据定案、后来的人应该按什么顺序做才能少走弯路。
>
> 全文已脱敏：不出现任何品牌路由器 API、真实账号/口令、SN/MAC/LOID、具体 SSID 或个人网络参数。

---

## 0. 先给结论（TL;DR）

**现象**：终端连上 WiFi 显示「已连接，无互联网」；浏览器打不开网页；DNS 解析结果异常。换上旧光猫立刻恢复，换回新光猫立刻复现。

**真正原因**：新光猫虽然被改成了「桥接」，但桥接只改了一半：

- LAN 侧 DHCP / DNS / DHCPv6 / RA 仍在跑；
- 向光猫查询一个不存在的域名，它返回 `rcode=0` 加一个指向自身管理地址的 A 记录——典型的强制门户式 DNS 劫持；
- 端口绑定或 PPPoE→Bridge 的模板残留，让错误配置有机会被下发到终端或上挂路由。

于是终端或上挂路由拿到的是「光猫管理地址当 DNS + 一个没有出口的默认路由」，看起来连着网，实际所有域名都被拐到光猫自己。

**最有效的定位手段不是猜 DNS，而是两件事**：

1. **A/B 替换**：用确定能上网的旧光猫做参照，执行完全相同的命令集做 diff；
2. **直连光猫实发包探测**：DNS 探针查不存在域名，DHCP 探针实发 DISCOVER，而不是只看配置表。

**修复核心**：关 LAN 侧服务 → 清错误端口绑定 → `save` → `reboot` → 用实包验证。配置层面查不出东西时，才升级到固件转储和逆向。

---

## 1. 现场与关键事实

脱敏后的拓扑：

```
运营商光纤
    │
    ▼
光猫（被改成桥接，但可能残留 LAN 服务）
    │  二层透传 / VLAN 改写
    ▼
上挂主路由（负责 PPPoE 拨号、终端 DHCP、DNS）
    │
    ├── 有线终端
    └── WiFi 终端
```

当时能确认的事实只有这些：

| 事实 | 意义 |
|---|---|
| 终端 WiFi 显示「已连接，无互联网」 | 只是症状，不能直接推出 DNS 故障 |
| 旧光猫换上后一切正常 | 有一个完美 A/B 参照物 |
| 旧光猫同样是桥接 | **「桥接开关」不是充分条件**，差异一定在别处 |
| 新光猫换上后复现 | 问题可稳定复现，可以逐层收敛 |
| 光猫管理地址可达 | 有 telnet，能读运行时状态 |

这一条最重要：**旧机也是桥接却能用，说明不要停在「我已经改成桥接了」这一步**。桥接的四个硬性条件见 [01-principles.md](01-principles.md)。

---

## 2. 我们走过的弯路（这一节最值得后来者读）

| 阶段 | 当时的怀疑 | 为什么是弯路 | 正确做法 |
|---|---|---|---|
| 终端层 | 「DNS 服务器坏了，换个公共 DNS 就好」 | 手机/系统的「无互联网」提示不等于 DNS 故障；代理和虚拟网卡的 DNS 也不是真实链路 | 在一台有线终端上复现，绑定真实网卡、绕过代理做原始 DNS 查询 |
| 其他 WiFi | 把一次误连到其他 WiFi 当成链路证据 | 连错 SSID 之后所有结论都无效 | 先确认当前 SSID / BSSID，再谈任何网络层判断 |
| 上挂路由 | 反复改路由的 DHCP / DNS 参数 | 路由只是症状放大器；不同固件字段名还不一样，容易改了个寂寞 | 先做设备替换：换光猫看是否复现，一层层锁定 |
| 光猫配置界面 | 「界面显示桥接，所以桥接没问题」 | 界面只看连接模式；运行时可能还有 `pppd`、LAN 服务、错误端口绑定 | 用 `ps` / `ifconfig` / `netstat` / `sendcmd` 看运行时 |
| 修复动作 | 「关了 DHCP 开关就完事」 | 进程可能仍在监听；配置不 `save`、不重启等于没做 | `save` + `reboot` 后用实发包验证，不靠「看起来对」 |
| 取证顺序 | 先想反汇编固件找 bug | 配置 A/B diff 已经能定案，逆向成本高且容易过度解读 | 配置层查不出东西时再上逆向 |
| 固件拷贝 | 先拷了编号靠前的 rootfs 分区 | A/B 槽位编号跟活动槽不一定一致 | 先用 `df` / `/proc/mounts` 对齐活动 rootfs 再 dump |
| 发布分享 | 原始转储直接打包上传 | `paramtag` / `userconfig` 里有 SN、MAC、口令、LOID | 按 [09-publish-checklist.md](09-publish-checklist.md) 剔除并扫描后才发布 |

一句话总结：**我们最大的错误不是不会改桥接，而是在错误层级上反复优化。** 后来把顺序改成「先分层、先替换、先备份、后逆向」，问题当天就定案了。

---

## 3. 正确路线：后来者照着走

### 第 0 步：先立安全底线

1. **必须有物理接触**：能看到指示灯、能插拔网线、知道 RESET 位置。
2. **先记录身份信息**：LOID / 注册密码、INTERNET VLAN、设备 SN/MAC、TR069 配置、当前端口绑定。只写本地笔记，不入仓库。
3. **先备份**：全表明文 + 运行配置库 + 分区转储，三样缺一不可。做法见 [02-prepare.md](02-prepare.md)。
4. **不要先动光纤、不要先恢复出厂**。恢复出厂会清 LOID，可能导致光猫无法重新注册。

### 第 1 步：把问题分层

按顺序问三个问题，每层只做最小验证：

| 层 | 要回答的问题 | 最小验证 |
|---|---|---|
| 终端 | 真的拿到错误配置了吗？ | 有线单终端复现；看 IP/网关/DNS；绑定网卡查一个不存在的域名 |
| 上挂路由 | PPPoE 真的拨上了吗？ | 管理页 WAN 状态要有公网 IPv4；不要看手机 WiFi 图标 |
| 光猫 | 桥接真的干净吗？ | `ps | grep pppd`、`ifconfig | grep ppp`、`netstat -lnup`、`sendcmd 1 DB p ...` |

**在这一步不要跨层下结论。** 手机提示、公共 DNS、代理 DNS、WiFi 图标都只是旁证。

### 第 2 步：用旧光猫做 A/B 参照

这是整套方法里性价比最高的一步。在两台设备上执行**完全相同**的命令集，分别存成 `old_*.txt` / `new_*.txt`，只 diff 结构字段，不 diff 身份字段。

必读清单（完整版见 [03-old-modem-reference.md](03-old-modem-reference.md)）：

```sh
# 连接模式与业务承载
sendcmd 1 DB p WANC
sendcmd 1 DB p WANCD
sendcmd 1 DB p WANCPPP
sendcmd 1 DB p PDTWANCEXT
sendcmd 1 DB p GEMPORT

# VLAN 与端口绑定
sendcmd 1 DB p VLANBIND
sendcmd 1 DB p VLANInfo
sendcmd 1 DB p PortBinding
sendcmd 1 DB p BrGrp
sendcmd 1 DB p BrportConf
brctl show

# LAN 侧服务（桥接下应全部不响应）
sendcmd 1 DB p DHCPSHostCfg
sendcmd 1 DB p DHCP6SHostCfg
sendcmd 1 DB p PrefixCfg
sendcmd 1 DB p RaCfg
sendcmd 1 DB p WLANCfg
netstat -lnup | grep -E ':53|:67|:547'
```

比什么：

- INTERNET VLAN 与 GEM 映射是否一致；
- VLAN 处理模式是不是「改写(tag)」而不是「透传」；
- 桥接连接上有没有残留 `IsNAT=1` / `IsDefGW=1` / PPPoE 账号；
- 端口绑定是不是指向实际插线的口；
- 新机是不是还在 `:53` / `:67` / `:547` 上监听/应答。

### 第 3 步：用实发包定案

配置表只能说明「打算怎么跑」，实发包才能说明「实际怎么跑」。

```sh
# 查一个不存在的域名：正常应 NXDOMAIN；返回光猫地址就是劫持
python3 tools/probe_dns.py <光猫管理IP> --iface <直连网卡>

# 实发 DHCP DISCOVER：桥接机不应应答
python3 tools/probe_dhcp.py --iface <直连网卡>
```

定案证据链在我们的实战里是这四条：

1. `ps | grep pppd` 为空、`ifconfig | grep ppp` 为空 → **桥接本身成立**；
2. WANC / WANCD / PDTWANCEXT / GEMPORT 与旧机一致 → **VLAN 与业务通道没问题**；
3. `netstat -lnup` 仍能看到 `:53` / `:67` → **LAN 侧服务残留**；
4. 不存在域名返回 `rcode=0` + 指向光猫管理地址的 A 记录 → **DNS 劫持，症状定案**。

这四条合起来，就把问题从「可能是运营商 / 路由 / WiFi / DNS」收敛到「新光猫桥接残留」。

### 第 4 步：修复

完整命令与回滚见 [05-fix.md](05-fix.md)，核心动作如下：

```sh
sendcmd 1 DB set DHCPSHostCfg 0 ServerEnable 0
sendcmd 1 DB set DHCP6SHostCfg 0 ServerEnable 0
sendcmd 1 DB set DHCP6SHostCfg 0 IAPDEnable 0
sendcmd 1 DB set PrefixCfg 0 Enable 0
sendcmd 1 DB delr PortBinding 0
sendcmd 1 DB save
reboot
```

仍被劫持时，用防火墙兜底（重启会失效，需找持久化挂载点）：

```sh
iptables -I INPUT -i br0 -p udp --dport 53 -j DROP
iptables -I INPUT -i br0 -p tcp --dport 53 -j DROP
```

两个硬约束：

- **不 `save` 等于没做**：重启会从 `/userconfig` 读回旧值；
- **不重启不算生效**：进程还在用内存里的旧配置。

### 第 5 步：验证，而不是「感觉好了」

六项全过才算修完，见 [06-verify.md](06-verify.md)：

```
[ ] pppd 进程不存在，无 ppp0
[ ] VLAN 与旧机一致，模式为改写(tag)
[ ] DNS 探针：不存在域名 NXDOMAIN 或超时
[ ] DHCP 探针：实发 DISCOVER 无应答
[ ] 无 IPv6 空前缀 / RA / DHCPv6 响应
[ ] PortBinding 与接线一致；重启后全部保持
```

额外确认 `iptables/ip6tables` 的 FORWARD 计数为 0——桥接透传时用户流量对光猫只是以太帧，非 0 说明它还在路由用户流量。

### 第 6 步：仍有问题时再升级

- **间歇性故障**：挂 [06-verify.md](06-verify.md) 的采样器抓断网那一刻，区分 PPPoE 断、DNS 劫持、二层转发停滞。
- **配置层完全查不出**：再做固件转储与逆向，见 [08-firmware-analysis.md](08-firmware-analysis.md)。
- **改坏了**：优先逐项回滚；不行再按 [07-reset.md](07-reset.md) 选择软重置或硬件 RESET。

---

## 4. 从旧光猫到底读哪些信息

一句话：**读结构，不读身份**。完整命令见 [03-old-modem-reference.md](03-old-modem-reference.md)。

| 类别 | 读什么 | 比什么 |
|---|---|---|
| 连接模式 | `WANC` / `WANCD` / `WANCPPP` / `PDTWANCEXT` / `GEMPORT` | VLAN、VLAN 处理模式、IsNAT/IsDefGW、是否还有 PPPoE 残留、GEM/Tcont 映射 |
| VLAN 与桥 | `VLANBIND` / `VLANInfo` / `PortBinding` / `BrGrp` / `BrportConf` / `brctl show` | 绑到哪个物理口、哪些口进 br0、有没有把 WLAN 勾进去 |
| LAN 服务 | `DHCPSHostCfg` / `DHCP6SHostCfg` / `PrefixCfg` / `RaCfg` / `WLANCfg` / `netstat` | 桥接机应全部不响应；特别看空前缀 `Prefix="::"` |
| 运行时 | `ifconfig` / `/proc/net/dev` / `iptables -L -n -v` / `carrier_changes` / `dmesg` | FORWARD 计数、真实接线口、链路是否震荡、是否误协商到 10M |
| 分区版本 | `/proc/mtd` / `df` / `/proc/mounts` / `BoardInfo` | 活动槽是哪一个、两机固件版本差异 |

**不要 diff / 不要发布**的身份字段：LOID、注册密码、PPPoE 账号密码、GPON SN、设备 MAC、WiFi PSK、Web 管理口令、公网 IP、手机号。

---

## 5. 固件逆向：做了什么、说明了什么

这一步不是主线，但在本次实战里确实做了，后来者需要知道它的边界。

**触发条件**：配置 A/B 已经能定案，逆向只用来解释「为什么这个固件会这样」，不用来替代配置排查。

**实际动作**：

1. `cat /proc/mtd` + `df` 对齐活动槽（当时活动 rootfs 是编号靠后的槽，先拷靠前的槽就拷错了）；
2. `dd | gzip | curl -T` 流式转储分区，本机 `fw_recv.py` 接收；
3. 另拉一份 `/` 的 tar 快照，因为 jffs2 里的运行时状态跟分区镜像可能不一致；
4. 用 REA + Ghidra 12.1.4 批量反编译内核模块，导出 38 个函数。

**得到的确定结论**：

- 某交换驱动的 `sw_port_set_port_floodcontrol()` 是空实现，打印 `not support now!`——风暴抑制并不存在；
- carrier 只由芯片上报链路变化更新，驱动不会主动拉低；
- 链路 up 会调用 `set_ratelmt_according_linkspeed()`，按速率做出口整形。

**不能回答的问题**：故障到底是误协商到 10M 被限速、芯片真报链路 down、还是 PPPoE 在 PON 侧被断——这三者在静态代码里长得一样，必须靠故障时刻的 `speed` / `carrier_changes` 运行时采样区分。

**工具坑**：REA 只认 Ghidra 12.1.x，12.2 会报 `unsupported_version`；macOS x86_64 官方包缺反编译器，需要自编译 `ghidra_opt`；详见 [08-firmware-analysis.md](08-firmware-analysis.md)。

---

## 6. 重置与回滚：别把最后一张牌打早

决策表（完整版见 [07-reset.md](07-reset.md)）：

| 情况 | 用什么 |
|---|---|
| 只改坏几项，知道是哪几项 | 按 [05-fix.md](05-fix.md) 逐项写回原值 |
| 只搞坏 WiFi 配置 | `sendcmd 1 DB partrst WLANCfg` 按模块恢复 |
| 配置大面积混乱，LOID 已记录 | `sendcmd 1 DB reset` + `save` + `reboot` |
| 连管理页都进不去 | 硬件 RESET 长按约 10 秒（**先找到 LOID**） |
| 改完过几天又被改回去 | 不是重置问题，是 TR069 远程回推 |

重置前必须记录 LOID / 注册密码，并把配置备份拉回本地——`/userconfig` 会被一起清掉，只存在光猫里的备份等于没备份。

---

## 7. 一页检查清单

### 动手前

```
[ ] 能物理接触设备，能插拔网线
[ ] LOID / 注册密码已记在本地
[ ] 全表明文 + 运行配置库 + 分区转储已备份到本机
[ ] 直连网卡已设静态 IP，所有探测绑定该网卡
[ ] 旧光猫可用，准备做 A/B 参照
```

### 修复后

```
[ ] 无 pppd / ppp0，桥接成立
[ ] VLAN 与旧机一致，模式为改写(tag)
[ ] DNS 探针：不存在域名 NXDOMAIN 或超时
[ ] DHCP 探针：实发 DISCOVER 无应答
[ ] 无空前缀 / RA / DHCPv6 响应
[ ] PortBinding 与接线一致
[ ] FORWARD 计数为 0
[ ] 重启后以上全部保持
```

### 发布前

```
[ ] 剔除 userconfig / paramtag / 活动 rootfs 中的身份数据
[ ] 用 scan_secrets.py 扫仓库和固件，命中数为 0
[ ] 文档里没有真实账号、口令、SN/MAC/LOID、个人 IP、具体 SSID
[ ] 大文件放 Release assets，不进 git 历史
[ ] 仓库设为 private（除非确认全部脱敏）
```

---

## 8. 给后来者的十条硬规则

1. **手机提示「无互联网」不是诊断结论**，先找一台有线终端复现。
2. **先确认当前连的是哪个 SSID**，别把误连当证据。
3. **代理 / 虚拟网卡的 DNS 不是真实链路**，探测必须绑网卡、绕过代理。
4. **旧机也是桥接说明桥接不等于干净**，差异一定在别处。
5. **配置界面不算证据**，运行时 `ps` / `netstat` / `sendcmd` 才算。
6. **A/B 替换优先于猜测**，有一台能用的旧设备就赢了一半。
7. **实发包优先于看配置表**：DNS 查不存在域名，DHCP 实发 DISCOVER。
8. **`save` 加 `reboot` 才算生效**，重启后复核才算修完。
9. **先备份再动手，先记录 LOID 再重置**。
10. **配置层能定案就不要先逆向；逆向能解释机制但不能替代故障时刻的采样。**

---

## 9. 下一步读什么

| 想做什么 | 去哪一章 |
|---|---|
| 理解桥接为什么会有这些坑 | [01-principles.md](01-principles.md) |
| 动手前准备与备份 | [02-prepare.md](02-prepare.md) |
| 从旧光猫读什么 | [03-old-modem-reference.md](03-old-modem-reference.md) |
| 逐项审计新光猫 | [04-audit.md](04-audit.md) |
| 修 | [05-fix.md](05-fix.md) |
| 验 | [06-verify.md](06-verify.md) |
| 重置 / 回滚 | [07-reset.md](07-reset.md) |
| 固件转储与逆向 | [08-firmware-analysis.md](08-firmware-analysis.md) |
| 脱敏与发布 | [09-publish-checklist.md](09-publish-checklist.md) |
