#!/usr/bin/env pwsh
# Docker 构建脚本 - 支持进度条显示
# 使用方法：.\build.ps1 [-tag "markgit-editor:latest"] [-progress "plain"]

param(
    [string]$tag = "markgit-editor:latest",
    [ValidateSet("auto", "plain", "tty")]
    [string]$progress = "plain",
    [switch]$help
)

if ($help) {
    Write-Host @"
Docker 构建脚本 - 带进度条显示

使用方法:
  .\build.ps1                          # 使用默认参数构建
  .\build.ps1 -tag "myimage:1.0"       # 自定义镜像标签
  .\build.ps1 -progress "plain"        # 显示详细进度
  .\build.ps1 -progress "tty"          # 美化进度条（推荐在交互终端使用）

进度模式:
  auto   - 自动检测终端能力
  plain  - 显示详细进度和日志（推荐用于 CI/CD）
  tty    - 美化进度条（推荐用于本地开发）

"@
    exit
}

Write-Host "🐳 开始构建 Docker 镜像..." -ForegroundColor Cyan
Write-Host "   镜像标签：$tag" -ForegroundColor Yellow
Write-Host "   进度模式：$progress" -ForegroundColor Yellow
Write-Host ""

# 检查 Docker 是否运行
try {
    $null = docker info 2>&1
} catch {
    Write-Host "❌ Docker 未运行或不可用" -ForegroundColor Red
    exit 1
}

# 执行构建
$buildArgs = @(
    "buildx", "build",
    "--progress=$progress",
    "-t", $tag,
    "."
)

Write-Host "📦 执行命令：docker $($buildArgs -join ' ')" -ForegroundColor Gray
Write-Host ""

# 使用 Invoke-Expression 执行构建命令
docker @buildArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ 构建成功！" -ForegroundColor Green
    Write-Host "   镜像：$tag" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "运行容器：" -ForegroundColor Yellow
    Write-Host "   docker run -p 13131:13131 $tag" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ 构建失败" -ForegroundColor Red
    exit $LASTEXITCODE
}
