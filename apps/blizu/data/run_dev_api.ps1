param([int]$Port = 8010)
# Dev API for Blizu: DATABASE_URL is the root .env URL (database blizu); derived graph files in apps/blizu/data.
$root = "C:\ajmobree\projekt1\datathon-2026"
Set-Location $root
$env:PYTHONUTF8 = "1"
$line = (Get-Content "$root\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=', ''
$env:DATABASE_URL = $line.Trim()
$env:DATA_DIR = "apps/blizu/data"
$env:RATE_LIMIT = "600/minute"
& uv run --package blizu-api python -X utf8 -m uvicorn blizu_api.main:app --host 127.0.0.1 --port $Port
