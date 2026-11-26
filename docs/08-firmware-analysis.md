# 08 · 固件整体转储与逆向

配置层面查不出东西时，才需要走到这一步。目标是拿到**运行中的根文件系统 + 全部 MTD 分区**，再做静态分析。

## 1. 先看分区布局

```sh
cat /proc/mtd
cat /proc/partitions
df -k                    # 判断哪个 mtd 是活动 rootfs
cat /proc/mounts | grep ' / '
```

**坑**：`df` 显示 `/dev/root` 的大小往往对应**活动槽**（本例是 mtd13 rootfs2），而不是编号靠前的 mtd12 rootfs1。先对齐大小再 dump，否则拷的是 A/B 里的备用槽。

## 2. 建立传输通道

光猫通常没有 `nc` / `tftp` / `scp`，但有 `curl`。在本机起一个接收服务：

```sh
python3 tools/fw_recv.py 8000
```

光猫侧流式推送：

```sh
dd if=/dev/mtdblock13 bs=65536 2>/dev/null | gzip -1 | \
  curl -s -T - http://<本机IP>:8000/mtd13_rootfs2.bin.gz
```

批量转储：

```sh
python3 tools/dump_partitions.py --recv <本机IP>:8000 \
    1:uboot 4:wlan 7:kernel1 12:rootfs1 13:rootfs2
```

校验：

```sh
for f in *.gz; do gzip -t "$f" && echo "OK $f"; done
md5 -q *.gz > MANIFEST.md5
```

## 3. 运行目录快照

分区里的 jffs2 难以直接提取，且可能已经和运行时不一致。再拉一份文件树：

```sh
tar czf /tmp/rootfs_live.tar.gz -C / --exclude=proc --exclude=sys --exclude=dev .
curl -s -T /tmp/rootfs_live.tar.gz http://<本机IP>:8000/rootfs_live.tar.gz
```

本例 1329 个文件，26 MB。**注意这份快照包含全部涉密配置**，只能留本地。

## 4. 找切入点：先看未剥离符号的库

```sh
file bin/* sbin/* usr/bin/* lib/*.so* kmodule/*.ko | grep 'not stripped'
nm kmodule/switch.ko | grep ' [Tt] ' | wc -l
strings kmodule/switch.ko | grep -iE 'flood|storm|carrier|learn|rate'
```

优先顺序：

1. **内核模块**（`.ko`）——符号表通常完整，能直接看到函数名
2. **未剥离的 `.so`**——业务逻辑
3.  stripped 的主进程（如 2.7 MB 的 `cspd`）——最后再看

## 5. 工具链

| 工具 | 版本 | 说明 |
|---|---|---|
| [REA](https://www.npmjs.com/package/rea-agents) | 6.10.1 | `npm i -g rea-agents` |
| Ghidra | **12.1.4** | 12.2 会被 REA 判 `unsupported_version` |
| Temurin JDK | 21 | Ghidra 依赖 |

macOS x86_64 的 Ghidra 官方包**不含反编译器**，需自编译：

```sh
cd ghidra_12.1.4_PUBLIC/Ghidra/Features/Decompiler/src/decompile/cpp
make -j8 ghidra_opt ADDITIONAL_FLAGS="-w"
# 默认的 -mmacosx-version-min=10.6 会让 C++ 标准库头文件找不到
cp ghidra_opt ../../os/mac_x86_64/decompile
```

批量反编译（用教程附带的 Ghidra 脚本）：

```sh
export JAVA_HOME=/path/to/jdk21 GHIDRA_INSTALL_DIR=/path/to/ghidra_12.1.4_PUBLIC
$GHIDRA_INSTALL_DIR/support/analyzeHeadless /tmp/ghproj proj \
  -import switch.ko -scriptPath tools -postScript DumpDecomp.java out.c \
  FloodControl,Alarm,Carrier,LearnLimit,ratelmt -overwrite
```

## 6. 静态分析能回答什么、不能回答什么

本例反编译 38 个函数后得到的确定结论：

- `sw_port_set_port_floodcontrol()` 是空实现（`printk("not support now!")`）——**风暴抑制不存在**
- 驱动不会主动拉低 carrier，只在芯片回报链路变化时更新
- 链路 up 必调 `set_ratelmt_according_linkspeed()`，按 10M/100M/1000M/2500M 打出口整形
- `zte_api_sw_*` 全是 EXTERNAL，真正的 TM 逻辑在 `plat_132.ko` / `np.ko`

**不能回答的**：故障到底是 (a) 误协商到 10M 被限速、(b) 芯片真报链路 down、还是 (c) PPPoE 在 PON 侧被断。这三种在静态代码里长得一模一样，必须靠故障时刻的 `/sys/class/net/ethX/speed` 和 `carrier_changes` 区分——见 [06-verify.md](06-verify.md) 的采样器。

## 7. 发布前

**不要直接上传原始转储**。分区里的 `userconfig` / `paramtag` / `db_user_cfg.xml` 含账号、口令、SN、MAC、LOID。按 [09-publish-checklist.md](09-publish-checklist.md) 扫描并剔除后再发布。
