# 01 · 桥接的四个硬性条件

把光猫从路由模式改成桥接，不是把「路由」改成「桥接」一个开关就完事。它同时是 **PON 终端 + 二层网桥 + 一个仍在跑的嵌入式 Linux 主机**。以下四项缺一不可。

## 条件一：WAN 连接是真的桥，不是改名的 PPPoE

中兴配置库里，INTERNET 连接的内部对象名常常是 `IGD.WD1.WCD1.WCPPP2`。从名字看是 PPPoE，但如果你把它改成桥接，名字不会跟着变。**判据不是名字，是运行时**：

```sh
ps | grep pppd          # 桥接时应为空
ifconfig | grep ppp     # 桥接时应无 ppp0
```

再看权威配置字段：

```sh
sendcmd 1 DB p WANCD     # Mode 才是连接模式的权威判据
sendcmd 1 DB p WANC      # VLANID / ConnType / IsNAT / IsDefGW
```

`IsNAT=1`、`IsDefGW=1` 残留在桥接连接上是常见坑。

## 条件二：VLAN 模式必须是「改写(tag)」

运营商的 INTERNET 业务带 VLAN 标签（常见 10 / 11 / 100，各地不同）。桥接连接的 VLAN 处理有两种：

- **改写 / tag**：光猫把用户侧 untagged 帧打上运营商 VLAN 再送 PON —— **正确**
- **透传 / transparent**：把带标签的帧原样透传 —— 主路由发的是 untagged，结果 PPPoE 发现帧到不了局端，**直接拨不上号**

在配置库里这个字段可能藏在产品扩展表（`PDTWANCEXT`）或 WANC 的 VLAN 处理字段里，不能只看 `VLANID`。

## 条件三：LAN 侧服务必须停干净

桥接后光猫没有 WAN IP，但它的 Linux 协议栈还活着。如果以下服务还在跑，就会制造「假网络」：

| 服务 | 症状 |
|---|---|
| dnsmasq 监听 `192.168.1.1:53` | 把任意域名解析成 `192.168.1.1`，浏览器打开管理页或超时 |
| DHCP 监听 `192.168.1.1:67` | 给终端发 `192.168.1.x` + 错误 DNS，与主路由网段冲突 |
| IPv6 RA（ff02::1） | 通告空前缀，终端把 IPv6 默认路由指向无出口的光猫 |
| DHCPv6 / IAPD | 同样分配不可用的 IPv6 配置 |

```sh
netstat -lnup | grep -E ':53|:67|:547'
sendcmd 1 DB p DHCPSHostCfg
sendcmd 1 DB p DHCP6SHostCfg
sendcmd 1 DB p PrefixCfg
```

**特别注意**：就算在配置库里把 `ServerEnable` 置 0，dnsmasq 进程可能仍在监听，但不再应答——要用实际 DNS 探测区分「进程还在」和「还在劫持」。

## 条件四：端口绑定与物理接线一致

```sh
sendcmd 1 DB p PortBinding       # 业务连接绑到哪个 LAN 口
for i in eth0 eth1 eth2 eth3 eth4; do
  printf '%s link=' "$i"; cat /sys/class/net/$i/carrier 2>/dev/null
  printf ' speed='; cat /sys/class/net/$i/speed 2>/dev/null
  printf ' cc='; cat /sys/class/net/$i/carrier_changes 2>/dev/null
done
```

绑到没插线的口 = 业务不通。绑了全部口 = 管理网段与用户网段混在一个广播域。推荐做法：**只绑实际使用的那个 LAN 口**，或者干脆清空绑定让所有口透传。

## 为什么故障表现为「没有 DNS 解析」

桥接模式下，主路由的 PPPoE 会话承载所有用户流量。对光猫而言，这些是以太帧透传——它的 iptables FORWARD 计数器应该是 0，**协议上碰不到客户端的 DNS 包**。

那用户为什么会解析不了？两种路径：

1. **主路由 PPPoE 拨号失败 → fallback 到 DHCP** → 从光猫拿到 `192.168.1.x` 和 DNS `192.168.1.1` → 所有域名被劫持成光猫自己
2. **终端直连光猫 WiFi** → 同样拿到光猫的 DHCP 与劫持 DNS

所以排查顺序是：先确认 PPPoE 通不通，再确认光猫有没有在 LAN 侧发放错误配置。**一上来就怀疑运营商 DNS 或主路由 dnsmasq，是这段经历里走过的最大弯路。**
