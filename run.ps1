<#
.SYNOPSIS
    mini-agent 一键启动：缺配置就自动生成，然后运行 agent.py。

.DESCRIPTION
    省掉「复制 config.example.py → 改名 config.py → 打开编辑器填 Key」这三步。

    - 没有 config.py  -> 自动从模板生成
    - Key 还是占位符  -> 提示你粘贴，自动写进 config.py（不会显示明文）
    - 已经有 Key      -> 直接启动

    --mock 不需要任何配置，也不会触发上面的流程。

.EXAMPLE
    .\run.cmd --mock
    .\run.cmd
    .\run.cmd "在当前目录建个 hello.py 然后运行它"

.EXAMPLE
    # 非交互（CI / 脚本调用）
    $env:DEEPSEEK_API_KEY = "sk-xxxx"
    .\run.cmd "任务"
#>

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
Push-Location -LiteralPath $Root

function Fail([string]$Message) {
    Write-Host $Message -ForegroundColor Red
    Pop-Location
    exit 1
}

# ---------------------------------------------------------------- Python

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {
    Fail "找不到 python。请先安装 Python 3.8+ 并确保在 PATH 里。"
}

# ---------------------------------------------------------------- mock 模式
# 假模型不联网、不需要 Key，直接开跑

if ($args -contains "--mock") {
    & $python "agent.py" @args
    $code = $LASTEXITCODE
    Pop-Location
    exit $code
}

# ---------------------------------------------------------------- 准备配置

$config = Join-Path $Root "config.py"
$example = Join-Path $Root "config.example.py"

if (-not (Test-Path $config)) {
    if (-not (Test-Path $example)) {
        Fail "config.example.py 不见了，仓库不完整？"
    }
    Copy-Item -Path $example -Destination $config
    Write-Host "首次运行：已从 config.example.py 生成 config.py" -ForegroundColor Cyan
}

$needKey = (Get-Content -Raw -Encoding UTF8 -Path $config) -match "你的DeepSeekKey"

if ($needKey) {
    $key = $env:DEEPSEEK_API_KEY
    if (-not $key) {
        Write-Host ""
        Write-Host "需要 DeepSeek API Key（只配一次，写进 config.py，不会提交）："
        Write-Host "  申请地址 https://platform.deepseek.com"
        $secure = Read-Host "  粘贴 Key（输入不显示）" -AsSecureString
        $key = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
    }
    if (-not $key) { Fail "没有拿到 Key，退出。" }

    if (-not $key.StartsWith("sk-")) {
        Write-Host "提醒：DeepSeek 的 Key 一般以 sk- 开头，确认一下没粘错。" -ForegroundColor Yellow
    }

    # 逐行替换，避免正则转义把 Key 里的字符吃掉
    $lines = Get-Content -Encoding UTF8 -Path $config
    $lines = $lines | ForEach-Object {
        if ($_ -match '^\s*API_KEY\s*=') { 'API_KEY = "' + $key + '"' } else { $_ }
    }
    Set-Content -Path $config -Value $lines -Encoding UTF8
    Write-Host "已写入 config.py（.gitignore 已忽略，不会进仓库）" -ForegroundColor Cyan
    Write-Host ""
}

# ---------------------------------------------------------------- 启动

& $python "agent.py" @args
$code = $LASTEXITCODE
Pop-Location
exit $code
