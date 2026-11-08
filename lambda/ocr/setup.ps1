param([switch]$WithComparison)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:UV_CACHE_DIR = Join-Path $projectRoot '.cache/uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $projectRoot '.cache/python'
$env:TEMP = Join-Path $projectRoot '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot '.cache/pycache'
$env:PYTHONIOENCODING = 'utf-8'
New-Item -ItemType Directory -Force -Path $env:TEMP,$env:UV_CACHE_DIR | Out-Null
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'uv is required; install or provide uv before running setup.' }
Push-Location $projectRoot
try {
    uv python install 3.12 --no-bin --no-registry
    if ($LASTEXITCODE -ne 0) { throw 'Python installation failed' }
    if (-not (Test-Path '.venv/Scripts/python.exe')) {
        uv venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
    }
    # Install without removing any unrelated packages the user may have added.
    uv pip install --python .venv/Scripts/python.exe -r lambda/ocr/requirements-dev.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
    if ($WithComparison) {
        $modelDir = Join-Path $projectRoot '.downloads/tessdata'
        New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
        $revision = '87416418657359cb625c412a48b6e1d6d41c29bd'
        $hashes = @{
            chi_sim = 'A5FCB6F0DB1E1D6D8522F39DB4E848F05984669172E584E8D76B6B3141E1F730'
            eng = '7D4322BD2A7749724879683FC3912CB542F19906C83BCC1A52132556427170B2'
        }
        foreach ($lang in @('chi_sim','eng')) {
            $target = Join-Path $modelDir "$lang.traineddata"
            if (-not (Test-Path -LiteralPath $target)) {
                Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$revision/$lang.traineddata" -OutFile $target
            }
            if ((Get-FileHash -LiteralPath $target -Algorithm SHA256).Hash -ne $hashes[$lang]) {
                throw "Checksum mismatch for $lang model; existing file has been preserved."
            }
        }
        $license = Join-Path $modelDir 'LICENSE'
        if (-not (Test-Path -LiteralPath $license)) {
            Invoke-WebRequest -Uri "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/$revision/LICENSE" -OutFile $license
        }
        $env:TESSDATA_PREFIX = $modelDir
    }
    Write-Output 'OCR environment ready under the project directory.'
} finally {
    Pop-Location
}
