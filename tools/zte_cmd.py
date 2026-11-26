#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量执行光猫命令

用法:
    export ZTE_PASS='<telnet密码>'
    python3 zte_cmd.py "sendcmd 1 DB p WANC" "netstat -lnup"

    # 只跑某张表
    python3 zte_cmd.py "sendcmd 1 DB p DHCPSHostCfg"
"""
import sys
from zte_telnet import connect

cmds = sys.argv[1:]
if not cmds:
    print(__doc__)
    sys.exit(1)

sh = connect()
for c in cmds:
    print("\n##### CMD:", c)
    print(sh.cmd(c, 6.0))
sh.close()
