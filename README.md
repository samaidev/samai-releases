# samai-releases — SamAI 统一发布目录（单一事实源）

- `catalog.json` 集团全部产品目录：版本 / sha256 / 三渠道直链（GitHub Release、ModelScope、HuggingFace）
- `saminstaller.zip` / `saminstaller.tar.gz` 统一安装器本体（纯标准库，Python 3.8+）
- `bootstrap/install_samai.ps1` / `install_samai.sh` 一条命令安装

## 一条命令安装 saminstaller

```powershell
# Windows
iwr -useb https://raw.githubusercontent.com/samaidev/samai-releases/main/bootstrap/install_samai.ps1 | iex
```
```bash
# macOS / Linux
curl -fsSL https://raw.githubusercontent.com/samaidev/samai-releases/main/bootstrap/install_samai.sh | bash
```

## 常用命令

```bash
saminstaller list                 # 罗列集团产品
saminstaller install openbox      # 测速选线下载 + 静默安装
saminstaller install openbox --portable   # 便携版解包即用
saminstaller update               # 全部产品检查升级
```

## catalog 副本（三渠道任一可引导）

1. ModelScope: `https://modelscope.cn/api/v1/models/luoyunlan168/samai-releases/repo?Revision=master&FilePath=catalog.json`
2. HuggingFace: `https://hf-mirror.com/datasets/tchbcb/samai-releases/resolve/main/catalog.json`（主站同名）
3. GitHub: `https://raw.githubusercontent.com/samaidev/samai-releases/main/catalog.json`

CI 发布产品时经 GitHub Contents API 自动回写本仓 catalog.json（见各产品仓 `ci/publish_channels.py`）。
