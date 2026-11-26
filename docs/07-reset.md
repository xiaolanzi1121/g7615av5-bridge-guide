# 09 · 重置与恢复出厂

改坏了怎么退回去。按影响范围从小到大排列，**先看清第 0 节，再动手**。

---

## 第 0 节：重置前必须记录的东西

恢复出厂会清掉的不只是你改过的那几项。对 GPON 光猫，最致命的是 **LOID / 注册密码**——清掉后光猫在 OLT 侧掉线，界面显示 `O5 → O1`，需要重新注册才能上网。

| 项目 | 取法 | 为什么不能丢 |
|---|---|---|
| LOID / 逻辑 ID | Web 管理页 → 网络 → 远程管理 → ONT 注册，或 `sendcmd 1 DB p GPONCFG` | 掉了要打运营商客服要 |
| LOID 密码 | 同上（部分省份为空） | 同上 |
| PPPoE 账号 / 密码 | `sendcmd 1 DB p WANCPPP` | 桥接模式下由路由器拨号，但重配需要 |
| INTERNET VLAN ID | `sendcmd 1 DB p WANC` 看 `VLANID`（本例为 10） | 填错直接拨不上 |
| 设备 SN / MAC | 机身贴纸，`sendcmd 1 DB p BoardInfo` | 部分省份绑 SN |
| TR069 参数 | `sendcmd 1 DB p TR069Cfg` | 影响运营商远程管理 |
| 当前完整配置 | 见下 | 一切回滚的最后保险 |

```sh
# 运行配置库（加密 XML，但可解密还原，务必离线保存）
cat /userconfig/cfg/db_user_cfg.xml > /tmp/backup_cfg.xml
# 全表明文导出（可读，便于逐项对照）
sendcmd 1 DB all > /tmp/backup_all.txt
```

把这两个文件拉回本地。**别只留在光猫里**——恢复出厂会连 `/userconfig` 一起清掉，备份跟着一起消失。

---

## 第 1 节：只回滚本次改动（推荐）

本项目的 5 处修改在 `05-fix.md` 末尾有逐项回滚命令。除非配置已经乱到无法逐项定位，否则**不要用恢复出厂**——它解决的问题远比它制造的问题少。

---

## 第 2 节：软重置（恢复默认配置库）

`sendcmd` 的 DB 模块自带重置子命令，实测列出如下（`sendcmd 1 DB` 的帮助输出原文）：

```
rreset:remote reset
lreset:local reset
lplreset:long press local reset
reset:local reset
partrst [ModName]: part restore now!
```

| 子命令 | 用途 |
|---|---|
| `reset` | 本地重置，等价 `lreset` |
| `lreset` | 本地重置（Web 页“恢复出厂设置”底层调的就是它） |
| `rreset` | 远程重置，由 TR069/ACS 下发 |
| `lplreset` | 长按 RESET 键触发，处理逻辑在 `bin/cspd` |
| `partrst [ModName]` | **按模块**恢复默认，比如只重置 `WLANCfg` |

按模块恢复是最有用的一个，能把“只搞坏了 WiFi 配置”和“整机重置”区分开：

```sh
# 只恢复某个配置表到出厂值
sendcmd 1 DB partrst WLANCfg
sendcmd 1 DB save
```

整机软重置：

```sh
sendcmd 1 DB reset      # 配置库回到 /etc/db_default_Normal_cfg.xml
sendcmd 1 DB save       # 写入 /userconfig
reboot                  # 让所有进程按新配置重启
```

**注意**：`reset` 只重置配置库，不碰 rootfs、不碰内核、不碰 LOID 之外的分区。它不会解除 telnet，也不会还原你删掉的系统文件。

**执行后不 save 等于没做**——重启会从 `/userconfig` 读回旧值。反过来，`reset` 后不重启，光猫仍在用内存里的旧配置运行，看起来像没生效。

---

## 第 3 节：硬件 RESET 键

机身背面/侧面的小孔，长按。这是 `lplreset` 的触发路径，由 `cspd`（`bin/cspd`，2.7 MB 主控进程）处理长按事件。

通用做法是**通电状态下长按 10 秒**，指示灯全亮/全灭后松手，设备自动重启。中兴机型常见 5～10 秒，具体时长固件里没有可读字符串，按 10 秒更保险。

效果等同于 `lplreset`：配置库恢复出厂 + 重启。**这个动作会清 LOID**，如果没记下来，重置完就是一台上不了网的光猫。

---

## 第 4 节：远程重置（说明为什么你的修改会被回推）

`rreset` 由 ACS 通过 TR069 下发。这是运营商侧的能力，你本地关不掉——只要 `TR069` VLAN（本例 VLAN 4003）通着，ACS 就能远程改配置、重开 WiFi、恢复出厂。

本项目改完 WiFi 后曾出现“重启后 CMCC SSID 又回来了”，原因就在这里。要彻底防回推只有两条路：

1. 断开 TR069 的 VLAN 绑定（代价：运营商无法远程排障、部分省份会判定设备异常）
2. 每次改完立刻核对，接受周期性被回推

**不建议**在没有把握时动 TR069——它在桥接场景下也是运营商侧判断“设备在线”的依据之一。

---

## 第 5 节：重置后的重建顺序

恢复出厂后要重建桥接，顺序错了会卡在“拨号失败”上。完整流程见 `05-fix.md` 的「附：如果要从零重建桥接」，核心约束是：

1. **VLAN 模式必须是“改写(tag)”**，不能是“透传”——透传直接拨不上，这是恩山同型号实测结论
2. 桥接连接**只绑实际在用的 LAN 口**，不要全选，更不要勾 WLAN
3. 先删原 PPPoE 路由连接，再新建 Bridge，不要在原连接上改
4. 建完再关光猫自身的 DHCP / IPv6 RA / 空前缀通告（本项目那 5 处修改）

---

## 附：一句话决策表

| 情况 | 用什么 |
|---|---|
| 只改坏了几项，知道是哪几项 | `05-fix.md` 的逐项回滚 |
| 只搞坏了 WiFi | `sendcmd 1 DB partrst WLANCfg` |
| 配置大面积混乱，但 LOID 记得 | `sendcmd 1 DB reset` + save + reboot |
| 连管理页都进不去 | 硬件 RESET 长按 10 秒（先把 LOID 找到） |
| 被运营商远程改回去了 | 不是重置问题，见第 4 节 |
