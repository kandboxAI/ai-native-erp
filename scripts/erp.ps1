# Windows entry point without relying on the global python command or activation.
$erpRoot = Split-Path -Parent $PSScriptRoot
$erpPython = Join-Path $erpRoot 'plugins/core/backend/.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $erpPython -PathType Leaf)) {
    Write-Error '请先创建 plugins/core/backend/.venv 并安装 plugins/core/backend/requirements.txt 中的依赖。'
    exit 2
}
& $erpPython (Join-Path $PSScriptRoot 'erp.py') @args
exit $LASTEXITCODE
