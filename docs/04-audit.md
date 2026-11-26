# 04 · 逐项审计新光猫

按 [03-old-modem-reference.md](03-old-modem-reference.md) 的命令集把新机拉一遍，然后对照下面五类残留逐项打勾。

## 1. DNS 劫持（最高优先级）

```sh
python3 tools/probe_dns.py <光猫IP>
```

判定：

| 查询结果 | 结论 |
|---|---|
| 不存在的域名 → `NXDOMAIN (rcode=3)` | 正常 |
| 不存在的域名 → `rcode=0` 且 A 记录指向光猫自己 | **劫持** |
| 超时无应答 | 已从 LAN 侧阻断（可达目标状态） |

原理：桥接无 WAN 时，固件把 dnsmasq 的上游模板变量留成未替换的占位符，等于零上游；同时强制把所有域名解析到管理页。改上游 `nameserver` 往往无效——这是固件故意行为，不是配置缺失。

**处理方式**：关掉 LAN 侧服务；若进程仍监听但已不应答，可用防火墙兜底：

```sh
iptables -I INPUT -i br0 -p udp --dport 53 -j DROP
iptables -I INPUT -i br0 -p tcp --dport 53 -j DROP
```

注意规则必须带 `-i br0`，否则可能把本机自己的 DNS 也断了。这类运行时规则重启会丢，写进启动脚本或依赖配置库改动持久化。

## 2. DHCP 服务残留

```sh
sendcmd 1 DB p DHCPSHostCfg
sendcmd 1 DB p DHCPSHostInfo      # 租约表里有没有终端
netstat -lnup | grep ':67'
```

**ServerEnable=1 就是错的**。桥接光猫发 `192.168.1.x` 有两个后果：与主路由网段撞车；DNS 指向被劫持的光猫。

配置库置 0 后需重启才生效。验证不要只看端口是否还在监听（进程可能常驻），要**实发 DHCP DISCOVER**：

```sh
python3 tools/probe_dhcp.py --iface <直连网卡>
```

**必须绑网卡**。否则广播走默认路由到主路由，收到的是主路由的应答，会误判成光猫还在发地址。

## 3. IPv6 空前缀与 RA

```sh
sendcmd 1 DB p PrefixCfg
sendcmd 1 DB p RaCfg
sendcmd 1 DB p DHCP6SHostCfg
```

危险配置长这样：

```
Prefix="::"   PrefixLen=0   Enable=1   ValidLifetime=4294967295
```

设备收到后把 IPv6 默认路由指向没有出口的光猫。Android / iOS 的联网检测优先走 IPv6，直接显示「已连接但无互联网」。

处理：

```sh
sendcmd 1 DB set PrefixCfg 0 Enable 0
sendcmd 1 DB set DHCP6SHostCfg 0 ServerEnable 0
sendcmd 1 DB set DHCP6SHostCfg 0 IAPDEnable 0
sendcmd 1 DB save
```

重启后确认 `netstat -lnup` 里 `:547` 消失。

## 4. 端口绑定与物理接线

```sh
sendcmd 1 DB p PortBinding
for i in eth0 eth1 eth2 eth3 eth4; do printf '%s ' "$i"; cat /sys/class/net/$i/carrier 2>/dev/null; done
```

如果绑定指向 `link=0` 的口，就是错的。两种修法：

- 只绑实际在用的那个 LAN 口（保守）
- 清空绑定，让所有口透传（简单，但管理帧可能泄漏到用户网段）

```sh
sendcmd 1 DB delr PortBinding 0
sendcmd 1 DB save
```

## 5. 连接是从 PPPoE 改来的

```sh
sendcmd 1 DB p WANCPPP
sendcmd 1 DB p WANC | grep -E 'IsNAT|IsDefGW|VLANID|ConnType'
```

桥接连接上残留账号密码、`IsNAT=1`、`IsDefGW=1` 是常见现象。**当前能拨号时不建议动它**——重建桥接涉及几十个字段，一个填错就彻底断网。记录为遗留项，等有机会物理接触时再做「删除原连接 → 新建纯 Bridge」。

## 审计结论模板

```
[ ] pppd 进程不存在，无 ppp0
[ ] INTERNET VLAN 与旧机一致，VLAN 模式为改写(tag)
[ ] DNS 探针：不存在域名返回 NXDOMAIN 或超时
[ ] DHCP 探针：实发 DISCOVER 无应答
[ ] PrefixCfg 无空前缀，RA/DHCPv6 已关
[ ] PortBinding 与实际接线一致
[ ] WLAN VAP 全部 Enable=0
[ ] iptables/ip6tables FORWARD 计数为 0
[ ] 重启后以上全部保持（未被 TR069 回推）
```
