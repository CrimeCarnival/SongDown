#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从正在运行的 QQ 音乐客户端提取最新 Cookie 并保存到 qmdec 配置。

用法:
    python update_cookie.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
QMDEC_SRC = PROJECT_ROOT / "input" / "Tools" / "qmdec" / "src"


def update_cookie() -> dict:
    """提取 QQ 音乐进程内存中的 Cookie 并写入 qmdec 配置。"""
    if str(QMDEC_SRC) not in sys.path:
        sys.path.insert(0, str(QMDEC_SRC))

    from qmdec.auth import extract_cookie_from_process
    from qmdec.cli import save_config

    result = extract_cookie_from_process()
    if not result.get("ok"):
        return result

    save_config({"cookie": result["cookie"], "uin": result["uin"]})
    return {"ok": True, "uin": result["uin"], "cookie_len": len(result["cookie"])}


def main() -> int:
    print("正在从 QQ 音乐客户端提取 Cookie ...")
    result = update_cookie()
    if not result.get("ok"):
        print(f"[失败] {result.get('error', '未知错误')}")
        print("请确认：")
        print("  1) QQ 音乐客户端已启动并登录；")
        print("  2) 若权限不足，请以管理员身份运行本脚本。")
        return 1

    print(f"[成功] Cookie 已更新：uin={result['uin']}，长度={result['cookie_len']}")
    print(f"配置文件：{Path.home() / '.config' / 'qmdec' / 'config.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())