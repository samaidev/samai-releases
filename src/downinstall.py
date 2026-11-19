#!/usr/bin/env python3
"""downinstall —— SamAI 路由下载器（库 + CLI）。

职责：
  1. 三渠道回退拉取 catalog.json（ModelScope → HF(含镜像) → GitHub）
  2. 对同一文件的三渠道 URL 自动测速（TTFB + 256KB 采样），选最快线路
  3. Range 断点续传 + SHA256 校验，失败自动切换下一渠道

零第三方依赖（纯标准库），可独立 pip 打包，也可被 saminstaller / pcguy 直接 import。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import time
import urllib.request
import urllib.error

DEFAULT_TIMEOUT = 10          # 测速 / catalog 拉取超时（秒）
SAMPLE_SIZE = 256 * 1024      # 测速采样字节数
CHUNK = 1 << 16

# catalog.json 在三渠道上的固定位置（与 publish_channels.py 的写入路径一致；
# namespace 为真实账号：MS=luoyunlan168（samcommand 同主）、HF=tchbcn、GitHub=samaidev）
CATALOG_URLS = [
    # 1) ModelScope（国内最快）
    "https://modelscope.cn/api/v1/models/luoyunlan168/samai-releases/repo?Revision=master&FilePath=catalog.json",
    # 2) HuggingFace（国内优先镜像域名，URL 与主站一一对应）
    "https://hf-mirror.com/datasets/tchbcn/samai-releases/resolve/main/catalog.json",
    "https://huggingface.co/datasets/tchbcn/samai-releases/resolve/main/catalog.json",
    # 3) GitHub：samaidev/samai-releases 公开仓（海外兜底）
    "https://raw.githubusercontent.com/samaidev/samai-releases/main/catalog.json",
]


def _open(url: str, timeout: float, headers: dict | None = None) -> urllib.request.urlopen:
    req = urllib.request.Request(url, headers={"User-Agent": "samai-downinstall/1.0",
                                               **(headers or {})})
    return urllib.request.urlopen(req, timeout=timeout)


def fetch_catalog(urls: list[str] | None = None) -> dict:
    """按顺序尝试三个渠道，任一成功即返回 catalog dict。"""
    last_err: Exception | None = None
    for url in (urls or CATALOG_URLS):
        try:
            with _open(url, DEFAULT_TIMEOUT) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[catalog] {url} -> {e}", file=sys.stderr)
    raise RuntimeError(f"所有渠道拉取 catalog 失败: {last_err}")


def speed_test(urls: list[str]) -> list[dict]:
    """对候选 URL 测速：TTFB + SAMPLE_SIZE 采样速率，返回按得分降序排列。"""
    results = []
    for url in urls:
        rec = {"url": url, "ttfb": None, "kbps": 0.0, "ok": False}
        try:
            t0 = time.monotonic()
            r = _open(url, DEFAULT_TIMEOUT, {"Range": f"bytes=0-{SAMPLE_SIZE - 1}"})
            ttfb = time.monotonic() - t0
            n = 0
            while n < SAMPLE_SIZE:
                chunk = r.read(CHUNK)
                if not chunk:
                    break
                n += len(chunk)
            dt = max(time.monotonic() - t0 - 0.0, 1e-6)
            r.close()
            rec.update(ttfb=round(ttfb, 3), kbps=round(n / 1024 / dt, 1), ok=True)
        except Exception as e:  # noqa: BLE001
            rec["error"] = str(e)[:80]
        results.append(rec)
    # 得分 = 采样速率 / (1 + TTFB)，兼顾吞吐与响应
    for rec in results:
        if rec["ok"]:
            rec["score"] = rec["kbps"] / (1.0 + (rec["ttfb"] or 1.0))
        else:
            rec["score"] = -1.0
    return sorted(results, key=lambda x: -x["score"])


def download(urls: list[str], dest: str, sha256: str | None = None) -> str:
    """按测速顺序下载到 dest，支持断点续传，失败自动换线；下载后校验 SHA256。"""
    ranked = speed_test(urls)
    tmp = dest + ".part"
    last_err: Exception | None = None
    for rec in ranked:
        url = rec["url"]
        try:
            offset = os.path.getsize(tmp) if os.path.exists(tmp) else 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            print(f"[download] {url} (from {offset} bytes)")
            with _open(url, 30, headers) as r, open(tmp, "ab" if offset else "wb") as f:
                while True:
                    chunk = r.read(CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
            h = hashlib.sha256()
            with open(tmp, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            if sha256 and sha256 not in ("", "发布时由 CI 自动写入") and h.hexdigest() != sha256:
                raise ValueError(f"SHA256 mismatch: {h.hexdigest()[:12]}... expected {sha256[:12]}...")
            os.replace(tmp, dest)
            print(f"[download] done -> {dest}")
            return dest
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[download] {url} failed: {e}, try next channel", file=sys.stderr)
    raise RuntimeError(f"全部渠道下载失败: {last_err}")


def resolve_file(cat: dict, product: str, platform: str | None = None,
                 version: str | None = None, portable: bool = False) -> tuple[str, dict]:
    """从 catalog 取产品某平台文件条目，返回 (文件名, {url:{github,hf,ms},sha256,size})。
    portable=True 时改取 extras 中的便携版（kind=portable，免安装解包即用）。"""
    p = next((x for x in cat["products"] if x["id"] == product), None)
    if not p:
        raise KeyError(f"catalog 中无产品 {product}")
    plat = platform or ("win" if sys.platform.startswith("win")
                        else "mac" if sys.platform == "darwin" else "linux")
    if version:
        raise NotImplementedError("历史版本回溯：待 catalog 支持多版本后实现")
    files = p.get("files") or {}
    if plat not in files:
        raise KeyError(f"产品 {product} 暂无 {plat} 产物（现有: {list(files) or '无'}）")
    entry = files[plat]
    if portable:
        extras = [e for e in entry.get("extras", []) if e.get("kind") == "portable"]
        if not extras:
            raise KeyError(f"产品 {product} 的 {plat} 条目无便携版（extras）")
        return extras[0]["name"], extras[0]
    return entry["name"], entry


def candidate_urls(entry: dict, cat: dict) -> list[str]:
    """catalog URL 缺失时按渠道模板补齐，顺序 = 国内优先（ms → hf镜像 → hf → github）。"""
    urls = entry.get("url") or {}
    ordered = [urls.get("ms"), urls.get("hf"), urls.get("github")]
    out: list[str] = []
    for u in ordered:
        if u:
            out.append(u)
    # HF 链接自动补镜像线路
    hf = urls.get("hf")
    if hf and "hf-mirror.com" not in hf:
        mirror = cat.get("channels", {}).get("hf", {}).get("mirror")
        if mirror:
            out.insert(1, hf.replace("https://huggingface.co", mirror))
    return out


def cmd_list(args):
    cat = fetch_catalog()
    print(f"{'产品':<10} {'版本':<10} {'平台':<14} 简介")
    for p in cat["products"]:
        plats = ",".join(p.get("platforms") or [])
        print(f"{p['id']:<10} {str(p.get('latest') or '-'):<10} {plats:<14} {p.get('desc','')}")


def cmd_url(args):
    cat = fetch_catalog()
    name, entry = resolve_file(cat, args.product, args.platform, portable=args.portable)
    urls = candidate_urls(entry, cat)
    print(f"{name} 候选线路测速（按得分排序）:")
    for rec in speed_test(urls):
        print(f"  {rec['kbps']:>9.1f} KB/s  ttfb={rec['ttfb']}s  ok={rec['ok']}  {rec['url']}")


def cmd_fetch(args):
    cat = fetch_catalog()
    name, entry = resolve_file(cat, args.product, args.platform, portable=args.portable)
    out = args.out or os.path.join(tempfile.gettempdir(), name)
    download(candidate_urls(entry, cat), out, entry.get("sha256"))
    print(out)


def main() -> int:
    ap = argparse.ArgumentParser(prog="downinstall",
                                 description="SamAI 路由下载器：测速选线 + 断点续传 + 校验")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="罗列集团产品")
    p = sub.add_parser("url", help="测速并展示某产品候选线路")
    p.add_argument("product")
    p.add_argument("--platform", choices=["win", "mac", "linux", "android"])
    p.add_argument("--portable", action="store_true", help="取便携版（extras）")
    p = sub.add_parser("fetch", help="测速下载某产品当前平台安装包")
    p.add_argument("product")
    p.add_argument("--platform", choices=["win", "mac", "linux", "android"])
    p.add_argument("--portable", action="store_true", help="取便携版（extras）")
    p.add_argument("--out", help="输出路径（默认临时目录）")
    args = ap.parse_args()
    {"list": cmd_list, "url": cmd_url, "fetch": cmd_fetch}[args.cmd](args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
