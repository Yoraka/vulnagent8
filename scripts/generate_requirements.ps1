############################################################################
# Generate requirements.txt from pyproject.toml
# Usage:
# .\scripts\generate_requirements.ps1 : Generate requirements.txt
# .\scripts\generate_requirements.ps1 upgrade : Upgrade requirements.txt
############################################################################

param(
    [string]$Action = ""
)

# 辅助函数
function Print-HorizontalLine {
    Write-Host "------------------------------------------------------------"
}

function Print-Heading {
    param([string]$Message)
    Print-HorizontalLine
    Write-Host "-*- $Message"
    Print-HorizontalLine
}

function Print-Info {
    param([string]$Message)
    Write-Host "-*- $Message"
}

# 获取脚本目录和仓库根目录
$CURR_DIR = Split-Path -Parent $MyInvocation.MyCommand.Path
$REPO_ROOT = Split-Path -Parent $CURR_DIR

Print-Heading "正在生成 requirements.txt..."

if ($Action -eq "upgrade") {
    Print-Heading "正在生成 requirements.txt（升级模式）"
    $env:UV_CUSTOM_COMPILE_COMMAND = ".\scripts\generate_requirements.ps1 upgrade"
    & uv pip compile "$REPO_ROOT\pyproject.toml" --no-cache --upgrade -o "$REPO_ROOT\requirements.txt"
} else {
    Print-Heading "正在生成 requirements.txt"
    $env:UV_CUSTOM_COMPILE_COMMAND = ".\scripts\generate_requirements.ps1"
    & uv pip compile "$REPO_ROOT\pyproject.toml" --no-cache -o "$REPO_ROOT\requirements.txt"
} 