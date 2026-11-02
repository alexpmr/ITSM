$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    py -3.12 -m venv .venv
}
$python = Join-Path $repo ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Erro instalando pip" }
& $python -m pip install -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw "Erro instalando dependências" }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw "Testes falharam" }
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --name PT2VHF-ITSM --paths src main.py
if ($LASTEXITCODE -ne 0) { throw "Falha no empacotamento" }
Write-Host "Gerado: dist\PT2VHF-ITSM.exe"
