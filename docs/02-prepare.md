# 02 · 动手前的准备

## 必须有物理接触条件

改桥接、清空端口绑定、恢复出厂，任何一步填错都可能导致管理页进不去。**准备好：能随时插拔网线、能看到光猫指示灯、知道 RESET 孔在哪。**

不要在没有物理接触的情况下远程改这些字段。

## 确认访问方式

```sh
telnet <光猫管理IP>
```

- 用户名/密码从设备机身贴纸或运营商处获取；教程不复现任何具体口令
- Web 管理页通常需要「超级管理员」账号，普通 `user` 账号看不到桥接配置
- 部分省份 TR069 会周期性回推配置，改完要复查（见 [07-reset.md](07-reset.md)）

## 设置一个直连网卡

用 USB 网卡或独立网卡直连光猫的 LAN 口，设静态 IP（与光猫管理地址同网段）：

```sh
# macOS 示例，接口名按实际替换
sudo networksetup -setmanual "USB Ethernet" 192.168.1.18 255.255.255.0 192.168.1.1
# 改回 DHCP
sudo networksetup -setdhcp "USB Ethernet"
```

**关键**：所有指向光猫的探测必须绑定这个接口，否则广播/单播会走默认路由到主路由，测出来的结果全是假的。DNS 探针工具提供 `--iface` 参数，DHCP 探针必须 `--iface`。

## 备份：三个层次，缺一不可

```sh
# 1) 全表明文导出（可读，便于逐项对照与回滚）
sendcmd 1 DB all > /tmp/backup_all.txt

# 2) 运行配置库（加密 XML，但密钥公开，等同明文 —— 只留在本地）
cat /userconfig/cfg/db_user_cfg.xml > /tmp/backup_cfg.xml

# 3) 全部分区（能为 A/B diff 提供素材）
cat /proc/mtd
# 见 08-firmware-analysis.md 的转储流程
```

把备份拉回本机并确认可读。**恢复出厂会连 `/userconfig` 一起清掉**，备份只留在光猫里等于没备份。

## 记录身份信息（只写本地笔记，不要发布）

| 项目 | 为什么必须记 |
|---|---|
| LOID / 逻辑 ID + 密码 | 恢复出厂后光猫在 OLT 侧掉线，需要重新注册 |
| GPON SN / 设备 MAC | 部分运营商绑定 SN |
| INTERNET VLAN ID | 重建连接时填错就拨不上 |
| PPPoE 账号密码 | 判断残留、必要时重建 |
| TR069 配置 | 决定会不会被远程回推 |
| 当前端口绑定与接线位置 | 回滚时需要原样恢复 |

这六项就是教程里反复说的「涉密信息」。所有命令输出在贴到公开场合之前，都要过一遍 [09-publish-checklist.md](09-publish-checklist.md) 的扫描。

## 工具

`tools/` 下的脚本都是 Python 3 标准库实现，无第三方依赖：

| 脚本 | 用途 |
|---|---|
| `zte_telnet.py / zte_cmd.py` | telnet 执行器（读到提示符才发下一条） |
| `probe_dns.py` | 用不存在的域名识别 DNS 劫持 |
| `probe_dhcp.py` | 绑定网卡实测 DHCP 是否还在应答 |
| `net_watch.py` | 定时采样抓故障现场 |
| `fw_recv.py / dump_partitions.py` | 固件转储 |
| `scan_secrets.py` | 发布前扫描涉密串 |

凭据一律通过环境变量传入（`ZTE_PASS` 等），**不要写进脚本、不要贴进聊天记录**。
