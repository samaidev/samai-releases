# install_samai.ps1 —— Windows 一条命令装 saminstaller
# 用法: iwr -useb https://raw.githubusercontent.com/samaidev/samai-releases/main/bootstrap/install_samai.ps1 | iex
# 逻辑: 三渠道回退下载 catalog.json -> 下载 saminstaller 本体 zip -> 解压到 %LOCALAPPDATA%\SamAI\bin -> 加入用户 PATH

$ErrorActionPreference = "Stop"

$catalogUrls = @(
  "https://modelscope.cn/api/v1/models/luoyunlan168/samai-releases/repo?Revision=master&FilePath=catalog.json",
  "https://hf-mirror.com/datasets/tchbcn/samai-releases/resolve/main/catalog.json",
  "https://raw.githubusercontent.com/samaidev/samai-releases/main/catalog.json"
)

function Get-FirstOk($urls, $out) {
  foreach ($u in $urls) {
    try {
      Write-Host "[bootstrap] try $u"
      Invoke-WebRequest -Uri $u -OutFile $out -UseBasicParsing -TimeoutSec 15
      return $true
    } catch { Write-Host "[bootstrap] fail: $_" }
  }
  return $false
}

$installDir = Join-Path $env:LOCALAPPDATA "SamAI\bin"
New-Item -ItemType Directory -Force $installDir | Out-Null
$tmp = Join-Path $env:TEMP "samai_bootstrap"
New-Item -ItemType Directory -Force $tmp | Out-Null

# 1) 拉取 catalog（三渠道回退）
$catalog = Join-Path $tmp "catalog.json"
if (-not (Get-FirstOk $catalogUrls $catalog)) { throw "无法获取 catalog.json（三渠道均失败）" }

# 2) 下载 saminstaller 本体（catalog 中约定 id=saminstaller 的条目承载安装器自身分发）
$zipUrl = "https://github.com/samaidev/samai-releases/releases/latest/download/saminstaller.zip"
if (-not (Get-FirstOk @(
    "https://modelscope.cn/api/v1/models/luoyunlan168/samai-releases/repo?Revision=master&FilePath=saminstaller.zip",
    "https://hf-mirror.com/datasets/tchbcn/samai-releases/resolve/main/saminstaller.zip",
    $zipUrl) (Join-Path $tmp "saminstaller.zip"))) {
  throw "无法下载 saminstaller 本体"
}

# 3) 解压并加入用户 PATH
Expand-Archive -Path (Join-Path $tmp "saminstaller.zip") -DestinationPath $installDir -Force
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$installDir*") {
  [Environment]::SetEnvironmentVariable("Path", "$userPath;$installDir", "User")
}

Write-Host "[bootstrap] saminstaller 已安装到 $installDir"
Write-Host "[bootstrap] 新开终端后运行:  saminstaller list   /   saminstaller install pcguy"
