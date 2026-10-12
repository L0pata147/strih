# Sestaví přenosnou verzi pro Windows: vložený Python 3.11 + knihovny + výchozí model -> ZIP.
# Spouští se na Windows (GitHub Actions nebo ručně):  pwsh tools\build_portable.ps1
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest je s progress barem extrémně pomalý

$PyVersion = "3.11.9"  # poslední 3.11 s oficiálními binárkami pro Windows
$Root = Split-Path -Parent $PSScriptRoot
$Dist = Join-Path $Root "dist"
$App = Join-Path $Dist "Strih"
$PyDir = Join-Path $App "python"
$Py = Join-Path $PyDir "python.exe"
$ZipPath = Join-Path $Dist "Strih-portable-win64.zip"

function Invoke-Checked {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Příkaz selhal ($LASTEXITCODE): $Exe $Arguments" }
}

if (Test-Path $Dist) { Remove-Item -Recurse -Force $Dist }
New-Item -ItemType Directory -Force $PyDir | Out-Null

Write-Host "== Stahuji vložený Python $PyVersion =="
$PyZip = Join-Path $Dist "python-embed.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$PyVersion/python-$PyVersion-embed-amd64.zip" -OutFile $PyZip
Expand-Archive $PyZip $PyDir
Remove-Item $PyZip

# ._pth: zapnout site-packages (kvůli pipu) a přidat složku aplikace (..) do sys.path
Set-Content (Join-Path $PyDir "python311._pth") -Encoding ascii -Value @(
    "python311.zip", ".", "Lib\site-packages", "..", "import site"
)

Write-Host "== Instaluji pip =="
$GetPip = Join-Path $Dist "get-pip.py"
Invoke-WebRequest "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
Invoke-Checked $Py @($GetPip, "--no-warn-script-location")
Remove-Item $GetPip

Write-Host "== Instaluji knihovny =="
Invoke-Checked $Py @("-m", "pip", "install", "--no-warn-script-location", "--no-cache-dir",
    "-r", (Join-Path $Root "requirements.txt"), "onnxruntime>=1.18")

Write-Host "== Kopíruji aplikaci =="
foreach ($f in "app.py", "processing.py", "install_deps.py", "requirements.txt", "start.bat", "README.md") {
    Copy-Item (Join-Path $Root $f) $App
}

Write-Host "== Předstahuji výchozí model isnet-anime =="
$env:U2NET_HOME = Join-Path $App "models"
Invoke-Checked $Py @("-c", "from rembg import new_session; new_session('isnet-anime')")
Remove-Item Env:U2NET_HOME

# úklid: bytecode se vytvoří znovu při prvním spuštění
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "== Balím ZIP =="
Push-Location $Dist
Invoke-Checked "7z" @("a", "-tzip", "-mx=5", "-bso0", "-bsp0", $ZipPath, "Strih")
Pop-Location

$SizeMB = [math]::Round((Get-Item $ZipPath).Length / 1MB)
Write-Host "Hotovo: $ZipPath ($SizeMB MB)"
