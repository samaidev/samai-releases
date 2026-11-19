#!/usr/bin/env bash
# install_samai.sh —— macOS / Linux 一条命令装 saminstaller
# 用法: curl -fsSL https://raw.githubusercontent.com/samaidev/samai-releases/main/bootstrap/install_samai.sh | bash
# 逻辑: 三渠道回退下载 saminstaller 本体 -> 解压到 ~/.samai/bin -> 写 PATH

set -euo pipefail

INSTALL_DIR="$HOME/.samai/bin"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$INSTALL_DIR"

# 三渠道回退（国内优先：MS -> HF 镜像 -> HF 主站 -> GitHub）
URLS=(
  "https://modelscope.cn/api/v1/models/luoyunlan168/samai-releases/repo?Revision=master&FilePath=saminstaller.tar.gz"
  "https://hf-mirror.com/datasets/tchbcn/samai-releases/resolve/main/saminstaller.tar.gz"
  "https://huggingface.co/datasets/tchbcn/samai-releases/resolve/main/saminstaller.tar.gz"
  "https://github.com/samaidev/samai-releases/releases/latest/download/saminstaller.tar.gz"
)

ok=""
for u in "${URLS[@]}"; do
  echo "[bootstrap] try $u"
  if curl -fSL --connect-timeout 10 --retry 2 -o "$TMP/samai.tar.gz" "$u"; then
    ok=1
    break
  fi
done
[ -n "$ok" ] || { echo "[bootstrap] 三渠道均下载失败" >&2; exit 1; }

tar -xzf "$TMP/samai.tar.gz" -C "$INSTALL_DIR"

# 写 PATH（bash/zsh 通用，幂等）
for rc in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [ -f "$rc" ] && ! grep -q "\.samai/bin" "$rc"; then
    echo 'export PATH="$HOME/.samai/bin:$PATH"' >> "$rc"
  fi
done

echo "[bootstrap] saminstaller 已安装到 $INSTALL_DIR"
echo "[bootstrap] 新开终端后运行:  saminstaller list   /   saminstaller install pcguy"
