# 06 · 验证方法

不要相信「配置看起来对了」。六项都要用**实际发包**验证。

## 1. DNS 劫持

```sh
python3 tools/probe_dns.py <光猫IP> --iface <网卡名>
```

工具查三个域名：一个正常域名、一个不存在的域名、一个对照公共 DNS。

| 现象 | 判定 |
|---|---|
| 不存在域名 → `NXDOMAIN` | 正常 |
| 不存在域名 → `rcode=0` + 光猫 IP | 劫持未解除 |
| 不存在域名 → 超时 | 已从 LAN 侧静默，达标 |
| 公共 DNS 也返回光猫 IP | 检查本机 DNS 设置/代理，不是光猫问题 |

## 2. DHCP 是否真的停了

```sh
python3 tools/probe_dhcp.py --iface <网卡名> --timeout 8
```

必须绑定直连网卡。工具发一个 DHCP DISCOVER，8 秒内无应答即达标。不绑网卡的后果：广播走默认路由到主路由，收到 `192.168.x.x` 的应答，误判成光猫仍在发地址。

再回读租约表：

```sh
sendcmd 1 DB p DHCPSHostInfo | grep RowCount
```

## 3. IPv6 RA / DHCPv6

重启后：

```sh
netstat -lnup | grep -E ':53|:67|:547'
```

桥接机应无 `:53` / `:547` 响应；`:67` 进程可能仍在监听但不应答，以 DHCP 探针为准。

终端侧确认没有拿到 `fd00::/8` / `2409:` 之类来自光猫的前缀，也没有默认路由指向光猫的 link-local 地址。

## 4. 桥接透传与 FORWARD 计数

```sh
iptables -L -n -v | grep -A3 FORWARD
ip6tables -L -n -v | grep -A3 FORWARD
```

桥接模式下用户流量封装在 PPPoE 里，对光猫只是以太帧，FORWARD 链计数应保持 0。非 0 说明光猫在路由用户流量，配置不对。

## 5. 主路由拨号状态

不要依赖任何品牌的私有 API。通用判据：

- 主路由管理页 WAN 状态显示「已连接」，有公网 IPv4
- 从终端 `curl --noproxy '*' https://www.baidu.com` 返回 200
- `dig +short @223.5.5.5 www.baidu.com` 返回真实 IP（不是 `192.168.1.1`）

## 6. 重启后的持久性

这一步最容易被跳过，也最容易被 TR069 打脸：

```sh
cat /proc/uptime             # 确认确实重启过
sendcmd 1 DB p DHCPSHostCfg | grep ServerEnable
sendcmd 1 DB p DHCP6SHostCfg | grep -E 'ServerEnable|IAPDEnable'
sendcmd 1 DB p PrefixCfg | grep -E 'Row No|Enable'
sendcmd 1 DB p WLANCfg | grep -c 'Enable" val="0'
netstat -lnup | grep -E ':53|:67|:547'
```

**全部保持才算修完。** 如果部分字段被回推，见 [07-reset.md](07-reset.md) 第 4 节。

## 抓间歇性故障现场

间歇性断网无法靠一次采样定位。把监测器挂到定时任务：

```sh
python3 tools/net_watch.py --loop 60    # 前台，每 60 秒一行
```

输出 CSV 字段：

```
ts, gw_ping, dns_public, dns_hijack, https4, https6, note
```

`note` 会标记：

- `gateway_dns_hijack` —— 光猫又开始劫持
- `gateway_unreachable` —— 管理地址都 ping 不通（链路/物理层）
- `no_internet` —— IPv4/IPv6 HTTPS 全挂

拿到断网那一刻的这一行，就能区分是 PPPoE 会话断、DNS 被劫持、还是二层转发停滞——静态分析无法区分这三种。
