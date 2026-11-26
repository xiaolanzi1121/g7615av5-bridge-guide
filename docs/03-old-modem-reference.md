# 03 · 从能用的旧光猫读取哪些信息

这是整套方法里最值钱的一步：**你有一台确定能上网的旧光猫，就有一个完美参照物**。不要凭记忆或网上教程猜字段，直接把两台设备的同名配置拉出来做 A/B diff，差异点就是答案。

## 基本原则

1. **在两台设备上执行完全相同的命令集**，输出分别存成 `old_*.txt` / `new_*.txt`
2. 只对比**结构字段**（模式、开关、VLAN、绑定、服务监听），不要对比**身份字段**（SN、LOID、账号、密码）
3. 身份字段只在本地笔记里记录，用于确认「这台是哪个运营商、哪条业务」，**不进 diff、不进仓库**
4. 如果旧光猫是路由模式而新光猫要桥接，模式差异本身是预期差异；其余字段仍应一致

## 必读清单（按顺序执行）

### A. 连接模式与业务承载

```sh
sendcmd 1 DB p WANC          # 连接列表：VLANID / ConnType / Enable / IsNAT / IsDefGW / WANCName
sendcmd 1 DB p WANCD         # Mode —— 连接模式的权威判据
sendcmd 1 DB p WANCPPP       # PPPoE 配置：是否存在、MTU、EnablePassThrough
sendcmd 1 DB p PDTWANCEXT    # 产品扩展：VLAN 改写/透传、DhcpEnable
sendcmd 1 DB p GEMPORT       # GEM port / Tcont 映射，业务通道
```

**要比的**：

| 字段 | 期望 |
|---|---|
| INTERNET 的 `VLANID` | 两台一致；这是运营商业务 VLAN |
| VLAN 处理模式 | 桥接必须是「改写(tag)」，旧机可直接看它怎么配 |
| `ConnType` | 同一业务在两台上的语义要对应，不能只看数字 |
| `IsNAT` / `IsDefGW` | 桥接连接上应为 0 |
| `WANCPPP` 残留 | 旧机若有账号密码，说明它是路由拨号；新机桥接应无 pppd 进程 |
| GEM port 数量与 Tcont | 三条业务（上网 / TR069 / IPTV）是否走同一通道 |

### B. VLAN 与端口绑定

```sh
sendcmd 1 DB p VLANBIND
sendcmd 1 DB p VLANInfo
sendcmd 1 DB p PortBinding
sendcmd 1 DB p BrGrp
sendcmd 1 DB p BrportConf
brctl show
cat /proc/net/vlan/config 2>/dev/null
cat /sys/class/net/br0/bridge/vlan_filtering 2>/dev/null
```

**要比的**：

- 旧机把 INTERNET 绑到了哪个 LAN 口，新机是否绑到同一个**物理位置**（注意设备端口编号可能与丝印不一致）
- `BrportConf` 里到底哪几个口进 br0，是否把 WLAN 也勾选了（勾了会关闭 hardware offload，全程 CPU 软桥）
- `VLANBIND` / `VLANInfo` 是否为空表——有的机型用它们做 VLAN 隔离，有的不用
- `brctl show` 的桥成员是否一致

### C. LAN 侧服务（桥接下应全部关掉）

```sh
sendcmd 1 DB p DHCPSHostCfg       # ServerEnable
sendcmd 1 DB p DHCP6SHostCfg      # ServerEnable / IAPDEnable
sendcmd 1 DB p PrefixCfg          # Prefix / PrefixLen / Enable / ValidLifetime
sendcmd 1 DB p RaCfg              # bState
sendcmd 1 DB p WLANCfg            # Enable（每个 VAP）
netstat -lnup | grep -E ':53|:67|:547'
ps | grep -E 'dnsmasq|pppd|hostapd' | grep -v grep
```

**要比的**：

- 旧机如果在路由模式，DHCP/DNS 开着是正常的；新机桥接后**必须关**，否则就是死网络
- 特别检查 `PrefixCfg` 有没有 `Prefix="::" / PrefixLen=0 / Enable=1 / 有效期无限`——空前缀会让终端判定无互联网
- 新机 WLAN VAP 是否全为 `Enable=0`。桥接机开着自带 WiFi 但没出口，会让连上去的设备拿到假 DNS
- 监听端口：`53`（DNS）、`67`（DHCP）、`547`（DHCPv6）在桥接机上都不该响应

### D. 运行时状态（配置库看不出来）

```sh
ifconfig
cat /proc/net/dev                       # 各口收发计数
netstat -lnup
iptables -L -n -v                       # 关注 FORWARD 计数器
ip6tables -L -n -v
ps
cat /proc/uptime
for i in eth0 eth1 eth2 eth3 eth4; do
  printf '%s c=' "$i"; cat /sys/class/net/$i/carrier 2>/dev/null
  printf ' s='; cat /sys/class/net/$i/speed 2>/dev/null
  printf ' cc='; cat /sys/class/net/$i/carrier_changes 2>/dev/null
done
dmesg | grep -iE 'link|eth|reset|watchdog|error'
```

**要比的**：

| 观察项 | 说明 |
|---|---|
| `iptables FORWARD` 计数 | 桥接透传时两个 FORWARD 链都应该是 0；非 0 说明光猫在路由用户流量 |
| 哪个 eth 口有收发计数 | 确认真实接线位置，别信配置库里的编号 |
| `carrier_changes` | 基线通常是 1~3；几十上百说明物理链路震荡 |
| `speed` / `duplex` | 误协商到 10M 会导致出口整形限速，现象是灯亮但网速不可用 |
| `dmesg` | 有无反复 link up/down、watchdog 复位 |

### E. 分区与固件版本（用于 A/B 二进制 diff）

```sh
cat /proc/mtd
cat /proc/partitions
cat /proc/csp/boardinfo 2>/dev/null
sendcmd 1 DB p BoardInfo
sendcmd 1 DB p OPTICAL         # 光功率、PON 注册状态（只本地看，不发布）
```

把两台的同名分区 dump 出来（见 [08-firmware-analysis.md](08-firmware-analysis.md)），做 `strings` / `cmp` / 二进制 diff。**已知好对已知坏，差异点往往一眼就能看到**——这比在 4 MB 的 `np.ko` 里盲搜快几个数量级。

## diff 的执行方式

```sh
# 每台设备分别导出同名表
python3 tools/zte_cmd.py "sendcmd 1 DB p WANC"  > old_wanc.txt   # 在旧机上
python3 tools/zte_cmd.py "sendcmd 1 DB p WANC"  > new_wanc.txt   # 在新机上

# 去掉设备专属值再做结构化对比
diff -u old_wanc.txt new_wanc.txt
```

建议写一个小解析器把 XML 变成 `字段=值` 的字典，再按字段名逐个比较，避免行顺序与空字段干扰。

**diff 前先脱敏**：把 LOID、SN、MAC、账号、密码替换成占位符。教程附带的 `tools/scan_secrets.py` 可以扫一遍输出文件。

## 一个实际结论

本次实战中，旧机与新机的 A/B 对照最终锁定在「LAN 侧服务没关」这一类差异上，而不是 PPPoE 或运营商侧。关键证据是：

- 两台设备的 INTERNET VLAN 与 GEM 映射一致
- 新机的 `WANCPPP` 无 pppd 进程，桥接成立
- 新机 `netstat -lnup` 仍显示 `:53` / `:67` 在监听
- 向新机查一个不存在的域名，返回 `rcode=0` + A 记录 `192.168.1.1`

这套对照法不需要反汇编就能定案；固件逆向只在配置层面查不出东西时才需要。
