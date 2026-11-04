param([int]$Port = 8030)
# Dev API for Birokratko (technical name: nabavaradar). DATABASE_URL is the root .env URL with /nabavaradar.
$root = "C:\ajmobree\projekt1\datathon-2026"
Set-Location $root
$env:PYTHONUTF8 = "1"
$line = (Get-Content "$root\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=', ''
$env:DATABASE_URL = ($line.Trim() -replace '/blizu$', '/nabavaradar')
$env:DATA_DIR = "apps/nabavaradar/data"
$env:RATE_LIMIT = "600/minute"
& uv run --package nabavaradar-api python -X utf8 -m uvicorn nabavaradar_api.main:app --host 127.0.0.1 --port $Port
