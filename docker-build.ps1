#!/usr/bin/env pwsh
# Docker Compose 构建脚本 - 自动检测网络并选择镜像源
# 使用方法：.\docker-build.ps1 [-rebuild] [-mirror "domestic"|"overseas"]

param(
    [switch]$rebuild,
    [ValidateSet("domestic", "overseas")]
    [string]$mirror = "domestic",
    [switch]$help
)

if ($help) {
    Write-Host @"
Docker Compose 构建脚本 - 自动网络检测

使用方法:
  .\docker-build.ps1                    # 使用国内镜像构建
  .\docker-build.ps1 -rebuild           # 无缓存重新构建
  .\docker-build.ps1 -mirror "overseas" # 强制使用国外镜像
  .\docker-build.ps1 -help              # 显示帮助

参数说明:
  -rebuild    无缓存重新构建（相当于 --no-cache）
  -mirror     选择镜像源：domestic（国内）或 overseas（国外）

"@
    exit
}

# 设置构建参数
if ($mirror -eq "domestic") {
    $baseImage = "swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim"
    $aptMirror = "mirrors.ustc.edu.cn"
    Write-Host "🇨🇳 使用国内镜像源加速构建" -ForegroundColor Green
} else {
    $baseImage = "python:3.11-slim"
    $aptMirror = "archive.ubuntu.com"
    Write-Host "🌍 使用国外官方镜像源构建" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "📦 基础镜像：$baseImage" -ForegroundColor Yellow
Write-Host "📦 APT 镜像：$aptMirror" -ForegroundColor Yellow
Write-Host ""

# 设置环境变量
$env:BASE_IMAGE = $baseImage
$env:APT_MIRROR = $aptMirror

# 构建命令
$buildArgs = @("compose", "build")
if ($rebuild) {
    $buildArgs += "--no-cache"
    Write-Host "🔄 无缓存重新构建模式" -ForegroundColor Yellow
}

Write-Host "🐳 开始构建..." -ForegroundColor Cyan
Write-Host ""

# 执行构建
docker @buildArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "✅ 构建成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "启动服务：" -ForegroundColor Yellow
    Write-Host "   docker-compose up -d" -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "❌ 构建失败" -ForegroundColor Red
    exit $LASTEXITCODE
}
