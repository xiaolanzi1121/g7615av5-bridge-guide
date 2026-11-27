# 工具说明

全部为 Python 3 标准库实现，无第三方依赖。凭据通过环境变量传入，**不要写进脚本或提交到仓库**。

| 脚本 | 用途 | 关键参数 |
|---|---|---|
| `zte_telnet.py` | telnet 客户端，读到提示符才发下一条命令 | 被 `zte_cmd.py` 引用 |
| `zte_cmd.py` | 批量执行光猫命令 | `export ZTE_PASS=...` 后跟命令列表 |
| `probe_dns.py` | 用不存在的域名识别 DNS 劫持 | `--iface en5` 绑定网卡 |
| `probe_dhcp.py` | 实发 DHCP DISCOVER 验证服务是否关闭 | **必须** `--iface` |
| `net_watch.py` | 定时采样抓断网现场 | `--loop 60 --gw <光猫IP>` |
| `fw_recv.py` | 本机 HTTP PUT 接收服务 | 监听端口 |
| `dump_partitions.py` | 批量转储 MTD 分区 | `--recv <IP>:8000 1:uboot ...` |
| `DumpDecomp.java` | Ghidra 批量反编译脚本 | 作为 `-postScript` 参数 |
| `scan_secrets.py` | 发布前涉密串扫描 | `--patterns-file /tmp/my_secrets.txt` |
| `fix_itms_dns.py` | **修复 ITMS 未注册导致的 DNS 全量劫持** | `--check` 只查看；无参数写入并重启 |
| `zte_factory.py` | **工厂模式开临时 telnet**（zteOnu 协议复刻） | `-i <IP> -p 80 -u <用户> -w '<口令>' -m <本机MAC>` |

## 用法示例

```sh
export ZTE_PASS='<telnet 密码>'

# 读配置表
python3 zte_cmd.py "sendcmd 1 DB p WANC" "sendcmd 1 DB p PortBinding"

# DNS / DHCP 探针
python3 probe_dns.py 192.168.1.1 --iface en5
python3 probe_dhcp.py --iface en5

# 固件转储
python3 fw_recv.py 8000 &
python3 dump_partitions.py --recv 192.168.1.18:8000 1:uboot 7:kernel1

# 发布前扫描
python3 scan_secrets.py ../firmware --patterns-file /tmp/my_secrets.txt
```

详细步骤见 `../docs/` 下各章。
