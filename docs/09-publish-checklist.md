# 09 · 发布前脱敏清单

固件转储和配置导出一旦进了 git 历史，**删文件也删不干净**——任何一次 clone 都会带走。发布前必须逐项过一遍。

## 一、必须剔除的位置

| 位置 | 里面有什么 |
|---|---|
| `mtd5_usercfg` / `userconfig/` | `db_user_cfg.xml`（AES 加密但密钥公开）、日志、校准结果 |
| 活动 rootfs 的原始 jffs2 镜像 | 可写分区，`/userconfig` 就在里面 |
| `mtd3_paramtags` / `tagparam/` / `wlan/paramtag` | **TAGPARAM provisioning**：GPON SN、MAC、WiFi PSK、Web 口令、运营商配置码。同一份数据常有 `.bak` / `.bjtest_bak` / `.gpon_bak` 多份拷贝 |
| `etc/wireless/*.dat` | WiFi 预共享密钥 |
| `etc/shadow` / `etc/passwd` | 口令哈希 |
| 运行时快照里的 `/tmp` `/var/run` `/var/lock` | 租约、临时状态 |
| 主目录和文档里 | 宽带账号、PPPoE 密码、路由器管理密码、公网 IP、设备 MAC、SN、手机号 |

**保留**：固件代码分区（uboot / wlan cal / middle / kernel / osgi / plugin / rootfs 备用槽）、剔除敏感路径后的 rootfs 文件树、反编译产物。

## 二、扫描方法

用教程附带的 `tools/scan_secrets.py`。它只在**可打印 ASCII 串**里匹配，避免二进制随机字节和 tar 头八进制时间戳造成误报。

```sh
# 1) 把你自己的设备专属串写进一个本地文件（不要提交）
cat > /tmp/my_secrets.txt <<'EOF'
<宽带账号>
<PPPoE 密码>
<WiFi 密码>
<管理密码>
<设备 MAC>
<GPON SN>
<公网 IP 前缀>
<手机号>
EOF

# 2) 通用模式 + 你的专属串一起扫
python3 tools/scan_secrets.py ./firmware --patterns-file /tmp/my_secrets.txt
```

通用模式包括：手机号、12 位以上连续数字（SN / LOID）、标准格式 MAC、`ZTEG` 开头的序列号、运营商默认 SSID 前缀。

**判定标准：命中文件数 = 0 才允许发布。**

## 三、常见误报及处理

| 误报 | 原因 | 处理 |
|---|---|---|
| tar 包里扫出「手机号」 | tar 头的八进制 mtime 字段（看起来像 11 位号码） | 逐 member 扫描，不要扫整包字节流 |
| 二进制里扫出 MAC / 长数字 | 压缩/随机数据恰好匹配 | 只扫可打印 ASCII 串；再人工核对是否为已知 OUI |
| 固件里的构建时间戳 | 形如 YYYYMMDDHHMMSS 的数字串 | 属固件元数据，非个人信息，可保留 |

## 四、文档也要扫

脚本本身不能包含任何真实凭据。本教程的 `scan_secrets.py` 把专属串改为 `--patterns-file` 从本地读，就是为了避免「扫描工具自己泄露密钥」。

对 `docs/` 与 `README.md` 再跑一次：

```sh
python3 tools/scan_secrets.py . --patterns-file /tmp/my_secrets.txt
```

## 五、发布渠道

- 大文件放 **Release assets**，不要塞进 git 历史；GitHub 单文件上限 2 GB，且资产可单独删除
- 超过 100 MB 时分片：

```sh
split -b 60m fw.tar fw-part
cat fw-part* > fw.tar
```

- 上传后核对 GitHub 返回的 asset `digest` 字段与本地 `shasum -a 256` 一致
- 仓库设为 **private**，除非你确认所有身份信息都已剔除

## 六、token hygiene

如果在自动化里用过 Personal Access Token：

- 用完立即吊销（GitHub Settings → Developer settings → Personal access tokens）
- **不要**把 token 贴进聊天窗口或命令行参数——它会进日志和会话记录
- 改用 `gh auth login` 设备码流程，凭证存系统钥匙串
- 必须用 token 时建 fine-grained token：只勾一个仓库、只给所需权限、有效期 7 天
