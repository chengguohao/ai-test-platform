# AI 测试工作流平台 · 一键启动脚本
# 启动后端 (FastAPI / uvicorn, 端口 8000) + 前端 (Vite, 端口 5173)
# 幂等：依赖已装则跳过安装；可重复双击运行
# 虚拟环境位于项目根目录 .venv（已存在，本脚本不创建 venv）

$ErrorActionPreference = 'Stop'
$Root        = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend     = Join-Path $Root 'backend'
$Frontend    = Join-Path $Root 'frontend'
$Venv        = Join-Path $Root '.venv'
$VenvPython  = Join-Path $Venv 'Scripts\python.exe'
$Req         = Join-Path $Backend 'requirements.txt'
$NodeModules = Join-Path $Frontend 'node_modules'

function Write-Step($msg) { Write-Host ''; Write-Host ("==> " + $msg) -ForegroundColor Cyan }
function Write-Ok($msg)   { Write-Host ("    [OK] " + $msg) -ForegroundColor Green }
function Write-Warn($msg) { Write-Host ("    [!!] " + $msg) -ForegroundColor Yellow }
function Write-Err($msg)  { Write-Host ("    [X]  " + $msg) -ForegroundColor Red }

# ---------- 1. 检查 .venv 是否就绪（不创建，仅校验） ----------
Write-Step '检查虚拟环境 .venv'
if (-not (Test-Path $VenvPython)) {
    Write-Err "未找到虚拟环境 Python：$VenvPython"
    Write-Host '    请在项目根目录手动创建：python -m venv .venv' -ForegroundColor Yellow
    Read-Host '按回车键退出'
    exit 1
}
Write-Ok "使用已有虚拟环境：$VenvPython"

# ---------- 2. 检查后端依赖（用 import 探测，已装则跳过 pip install） ----------
Write-Step '检查后端依赖 (fastapi / uvicorn import 探测)'
$importCheck = & $VenvPython -c "import fastapi, uvicorn; print('ok')" 2>&1
if ($importCheck -eq 'ok') {
    Write-Ok '后端依赖已就绪（fastapi / uvicorn 可正常 import）'
} else {
    Write-Warn '检测到依赖缺失，开始安装 requirements.txt（使用清华源加速）'
    & $VenvPython -m pip install -r $Req -i https://pypi.tuna.tsinghua.edu.cn/simple --disable-pip-version-check | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Err '后端依赖安装失败，请检查网络后重试'
        Read-Host '按回车键退出'
        exit 1
    }
    Write-Ok '后端依赖安装完成'
}

# ---------- 3. 检查 Node.js / npm ----------
Write-Step '检查 Node.js / npm'
$nodeExe = Get-Command node -ErrorAction SilentlyContinue
$npmExe  = Get-Command npm -ErrorAction SilentlyContinue
if (-not $nodeExe -or -not $npmExe) {
    Write-Err '未检测到 Node.js 或 npm，请先安装 Node.js 18+ 并加入 PATH'
    Read-Host '按回车键退出'
    exit 1
}
Write-Ok "Node: $($nodeExe.Source)"

# ---------- 4. 安装前端依赖（幂等） ----------
if (-not (Test-Path $NodeModules)) {
    Write-Step '安装前端依赖 (npm install，使用淘宝源加速)'
    Push-Location $Frontend
    & npm install --registry=https://registry.npmmirror.com
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) {
        Write-Err '前端依赖安装失败，请检查网络后重试'
        Read-Host '按回车键退出'
        exit 1
    }
    Write-Ok '前端依赖安装完成'
} else {
    Write-Ok '前端依赖已就绪（node_modules 存在）'
}

# ---------- 5. 启动后端前清理 8000 端口的旧 python 进程 ----------
# 避免 uvicorn 启动时报 WinError 10013（端口被占用，常见于上一次启动的后端没杀干净）
Write-Step '检查 8000 端口是否被占用'
$portConn = Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue
if ($portConn) {
    $oldPid = $portConn[0].OwningProcess
    $oldProc = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($oldProc -and $oldProc.ProcessName -eq 'python') {
        Write-Warn "8000 端口被旧后端占用（PID $oldPid, $($oldProc.ProcessName)），自动杀掉"
        Stop-Process -Id $oldPid -Force
        Start-Sleep -Seconds 1
        Write-Ok '旧后端进程已清理'
    } elseif ($oldProc) {
        Write-Err "8000 端口被非本项目的 $($oldProc.ProcessName) 进程占用（PID $oldPid）"
        Write-Host '    请手动关闭该进程，或在 backend/app/main.py 里改用其它端口' -ForegroundColor Yellow
        Read-Host '按回车键退出'
        exit 1
    }
} else {
    Write-Ok '8000 端口空闲'
}

# ---------- 6. 启动后端（独立窗口） ----------
Write-Step '启动后端 (uvicorn, http://localhost:8000)'
$beArg = '/k title AI-Test-Backend (uvicorn :8000) & cd /d "{0}" & "{1}" -m uvicorn app.main:app --reload --port 8000' -f $Backend, $VenvPython
Start-Process -FilePath 'cmd.exe' -ArgumentList $beArg -WindowStyle Normal
Write-Ok '后端已在独立窗口启动'

# ---------- 7. 启动前端（独立窗口） ----------
Write-Step '启动前端 (Vite dev, http://localhost:5173)'
$feArg = '/k title AI-Test-Frontend (Vite :5173) & cd /d "{0}" & npm run dev' -f $Frontend
Start-Process -FilePath 'cmd.exe' -ArgumentList $feArg -WindowStyle Normal
Write-Ok '前端已在独立窗口启动'

Write-Host ''
Write-Host '================================================  =====' -ForegroundColor Cyan
Write-Host '  启动完成！' -ForegroundColor Green
Write-Host '    后端 API : http://localhost:8000/api/health' -ForegroundColor White
Write-Host '    前端 UI  : http://localhost:5173' -ForegroundColor White
Write-Host '  关闭后端 / 前端独立窗口即可停止对应服务' -ForegroundColor White
Write-Host '================================================  =====' -ForegroundColor Cyan
Write-Host ''
Write-Host '本启动窗口可直接关闭；后端 / 前端运行于各自的独立窗口。' -ForegroundColor Gray
Start-Sleep -Seconds 3