param([switch]$Compare, [string]$Font = 'C:/Windows/Fonts/msyh.ttc')
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$env:TEMP = Join-Path $projectRoot '.tmp'
$env:TMP = $env:TEMP
$env:PYTHONPYCACHEPREFIX = Join-Path $projectRoot '.cache/pycache'
$env:PYTHONIOENCODING = 'utf-8'
$env:TESSDATA_PREFIX = Join-Path $projectRoot '.downloads/tessdata'
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
Push-Location $projectRoot
try {
    & .venv/Scripts/python.exe -m pytest lambda/ocr/tests -q --tb=short -p no:cacheprovider
    if ($LASTEXITCODE -ne 0) { throw 'Unit tests failed' }
    & .venv/Scripts/python.exe lambda/ocr/generate_fixtures.py --output build/ocr-fixtures --font $Font
    if ($LASTEXITCODE -ne 0) { throw 'Fixture generation failed' }
    & .venv/Scripts/python.exe lambda/ocr/benchmark.py build/ocr-fixtures/manifest.json --output build/ocr-validation/rapidocr.csv
    if ($LASTEXITCODE -ne 0) { throw 'RapidOCR smoke test failed; inspect build/ocr-validation/rapidocr.csv' }
    & .venv/Scripts/python.exe lambda/ocr/integration_smoke.py build/ocr-fixtures
    if ($LASTEXITCODE -ne 0) { throw 'Lambda handler integration smoke test failed' }
    if ($Compare) {
        & .venv/Scripts/python.exe lambda/ocr/benchmark.py build/ocr-fixtures/manifest.json --engines rapidocr tesseract --output build/ocr-validation/comparison.csv
        if ($LASTEXITCODE -ne 0) { Write-Warning 'Some comparison cases failed; inspect comparison.csv. A nonzero result is not automatically a setup error.' }
    }
} finally {
    Pop-Location
}
