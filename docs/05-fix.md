# 05 · 修复手册

**前置**：已完成 [02-prepare.md](02-prepare.md) 的备份。每条命令执行后用 `sendcmd 1 DB p <表>` 回读确认。

字段名在不同固件版本可能略有差异；本文用 `sendcmd 1 DB p <表>` 的实际输出为准，不要照抄字段名。

## 第 0 步：记录原值

```sh
sendcmd 1 DB p DHCPSHostCfg
sendcmd 1 DB p DHCP6SHostCfg
sendcmd 1 DB p PrefixCfg
sendcmd 1 DB p PortBinding
```

把输出存到本地文件。回滚时逐项 `sendcmd 1 DB set <表> <行> <字段> <原值>` 写回。

## 第 1 步：关 DHCP 服务

```sh
sendcmd 1 DB set DHCPSHostCfg 0 ServerEnable 0
sendcmd 1 DB set DHCP6SHostCfg 0 ServerEnable 0
sendcmd 1 DB set DHCP6SHostCfg 0 IAPDEnable 0
```

## 第 2 步：关 IPv6 空前缀与 RA

```sh
sendcmd 1 DB set PrefixCfg 0 Enable 0
# 如果存在第二条前缀，同样置 0
sendcmd 1 DB p PrefixCfg | grep 'Row No'
```

`RaCfg` 的 `bState` 是位掩码；部分机型需要在 Web 页关「IPv6 RA 通告」。以重启后 `netstat -lnup` 中 `:547` 消失为准。

## 第 3 步：清空错误的端口绑定

```sh
sendcmd 1 DB p PortBinding
sendcmd 1 DB delr PortBinding 0
```

只有当绑定确实指向未插线口、或与 A/B 参照不一致时才做。清空后所有 LAN 口都能透传。

## 第 4 步：保存并重启

```sh
sendcmd 1 DB save
reboot
```

**不 save 等于没做**：重启会从 `/userconfig` 读回旧值。**不重启也不算生效**：进程仍用内存里的旧配置。

等待设备恢复（典型 40~90 秒），然后逐项回读确认持久化。

## 第 5 步：阻断 DNS 劫持（如仍存在）

先实发 DNS 探测。若仍返回假地址，用防火墙兜底：

```sh
iptables -I INPUT -i br0 -p udp --dport 53 -j DROP
iptables -I INPUT -i br0 -p tcp --dport 53 -j DROP
```

运行时规则重启即失效。要持久化需找到固件启动脚本的挂载点，或改用配置库开关。本教程不提供通用启动脚本路径——不同固件差异太大，以实际 `ls /etc/init.d` 与 `ps` 看到的进程为准。

## 第 6 步：验证

见 [06-verify.md](06-verify.md)。六项全过才算修完。

## 回滚

```sh
# 按第 0 步记录的原值逐项写回
sendcmd 1 DB set DHCPSHostCfg 0 ServerEnable 1
sendcmd 1 DB set DHCP6SHostCfg 0 ServerEnable 1
sendcmd 1 DB set DHCP6SHostCfg 0 IAPDEnable 1
sendcmd 1 DB set PrefixCfg 0 Enable 1
# 端口绑定需要重建行，不能只 set；见备份文件里的原始 XML
sendcmd 1 DB save
reboot
```

改坏了又不想逐项回滚，见 [07-reset.md](07-reset.md)。

## 附：从零重建桥接连接

只在有物理接触、且当前连接确实不可救药时做。

1. **先删除**原 PPPoE / 路由连接，不要在原连接上改
2. **新建 Bridge 类型连接**，填运营商 VLAN ID
3. VLAN 模式选**改写(tag)**，不要选透传
4. **只绑实际使用的 LAN 口**，不勾 WLAN（勾了 hardware offload 永不激活）
5. TR069 保持开启，除非你明确接受失联
6. 建完再按第 1~3 步关掉 LAN 侧服务

```sh
# 删除前务必确认已备份
sendcmd 1 DB delr WANC <行号>
```
