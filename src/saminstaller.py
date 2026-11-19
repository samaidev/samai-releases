#!/usr/bin/env python3
"""saminstaller —— SamAI 统一安装器（独立 CLI，同时提供可嵌入 pcguy 的 API）。

设计要点：
  - 底层复用 downinstall（catalog 回退、三渠道测速、断点续传、SHA256 校验）
  - 三平台安装策略：
      Windows : 下载 setup.exe → /SILENT 静默安装（Inno Setup 原生支持）
      macOS   : 下载 tar.gz → 解包 → 执行 install.sh（无开发者 ID，仅命令行）
      Linux   : 同 macOS
  - 既可独立运行，也可被 pcguy import 后渲染产品面板一键安装
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile

# 允许同目录直接 import downinstall
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "downinstall"))
import downinstall as di  # noqa: E402


def _catalog() -> dict:
    return di.fetch_catalog()


# ---------------------------- API（供 pcguy 嵌入） ----------------------------

def list_products() -> list[dict]:
    """返回产品列表：id/name/desc/latest/platforms/installed_version，pcguy 直接渲染。"""
    cat = _catalog()
    out = []
    for p in cat["products"]:
        out.append({
            "id": p["id"],
            "name": p.get("name") or p["id"],
            "desc": p.get("desc", ""),
            "latest": p.get("latest"),
            "platforms": p.get("platforms") or [],
            "installed": installed_version(p["id"]),
        })
    return out


def install_product(product: str, platform: str | None = None,
                    progress_cb=None, portable: bool = False) -> str:
    r"""下载并安装任一集团产品，返回安装包本地路径。progress_cb(done_bytes, total) 可选。
    portable=True 时下载便携版（extras，免安装），解包到 %LOCALAPPDATA%\SamAI\<id> 或 ~/.samai/<id>。"""
    cat = _catalog()
    name, entry = di.resolve_file(cat, product, platform, portable=portable)
    dest = os.path.join(tempfile.gettempdir(), name)
    di.download(di.candidate_urls(entry, cat), dest, entry.get("sha256"))
    if progress_cb:
        progress_cb(-1, os.path.getsize(dest))
    plat = platform or ("win" if sys.platform.startswith("win")
                        else "mac" if sys.platform == "darwin" else "linux")
    if portable:
        base = (os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SamAI", product)
                if plat == "win" else os.path.expanduser(f"~/.samai/{product}"))
        os.makedirs(base, exist_ok=True)
        if dest.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(dest) as zf:
                zf.extractall(base)
        else:
            with tarfile.open(dest) as tf:
                tf.extractall(base)
        print(f"[saminstaller] 便携版已解包到 {base}")
        try:
            with open(os.path.expanduser(f"~/.samai/{product}.version"), "w") as f:
                f.write(str(cat_version(cat, product) or ""))
        except Exception:
            pass
        return base
    if plat == "win":
        # Inno Setup 静默安装；/VERYSILENT 完全无界面，二选一
        subprocess.run([dest, "/SILENT", "/NORESTART"], check=True)
        try:
            os.makedirs(os.path.expanduser("~/.samai"), exist_ok=True)
            with open(os.path.expanduser(f"~/.samai/{product}.version"), "w") as f:
                f.write(str(cat_version(cat, product) or ""))
        except Exception:
            pass
    else:
        extract_dir = tempfile.mkdtemp(prefix=f"samai_{product}_")
        with tarfile.open(dest) as tf:
            tf.extractall(extract_dir)
        script = os.path.join(extract_dir, "install.sh")
        if os.path.exists(script):
            subprocess.run(["bash", script], check=True)
        else:
            print(f"[saminstaller] 包内无 install.sh，已解包到 {extract_dir}，请手动处理")
    return dest


def cat_version(cat: dict, product: str) -> str | None:
    p = next((x for x in cat["products"] if x["id"] == product), None)
    return p.get("latest") if p else None


def installed_version(product: str) -> str | None:
    """已装版本识别（骨架）：Windows 查卸载注册表 AppId=samai.cc.<id>；unix 查数据目录标记。"""
    appid = f"samai.cc.{product}"
    if sys.platform.startswith("win"):
        try:
            import winreg
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for wow in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"):
                    try:
                        k = winreg.OpenKey(root, wow + "\\" + appid)
                        v, _ = winreg.QueryValueEx(k, "DisplayVersion")
                        return v
                    except OSError:
                        continue
        except Exception:  # noqa: BLE001
            return None
        return None
    marker = os.path.expanduser(f"~/.samai/{product}.version")
    return open(marker).read().strip() if os.path.exists(marker) else None


def update_all() -> None:
    """全产品检查升级：catalog.latest > installed 才重装。"""
    for p in list_products():
        if not p["latest"]:
            continue
        if p["installed"] and p["installed"] >= p["latest"]:
            print(f"[update] {p['id']}: {p['installed']} 已是最新")
        else:
            print(f"[update] {p['id']}: {p['installed'] or '未安装'} -> {p['latest']}，开始安装")
            install_product(p["id"])


# ---------------------------- CLI ----------------------------

def cmd_list(_args):
    rows = list_products()
    print(f"{'产品':<10} {'已装':<10} {'最新':<10} 简介")
    for r in rows:
        print(f"{r['id']:<10} {str(r['installed'] or '-'):<10} {str(r['latest'] or '-'):<10} {r['desc']}")


def cmd_install(args):
    path = install_product(args.product, args.platform, portable=args.portable)
    print(f"安装完成（安装包: {path}）")


def cmd_update(_args):
    update_all()


def main() -> int:
    ap = argparse.ArgumentParser(prog="saminstaller",
                                 description="SamAI 统一安装器：安装/升级集团任一软件")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="罗列集团产品与简介")
    p = sub.add_parser("install", help="安装指定产品（测速路由下载）")
    p.add_argument("product")
    p.add_argument("--platform", choices=["win", "mac", "linux"])
    p.add_argument("--portable", action="store_true", help="便携版：只解包不安装，免管理员权限")
    sub.add_parser("update", help="全部产品检查升级")
    args = ap.parse_args()
    {"list": cmd_list, "install": cmd_install, "update": cmd_update}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
