param([string]$Db = "otporno_test", [int]$Port = 8020)
# Dev API for Otporko: DATABASE_URL is the root .env URL with the database name replaced.
$root = "C:\ajmobree\projekt1\datathon-2026"
Set-Location $root
$env:PYTHONUTF8 = "1"
$line = (Get-Content "$root\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=', ''
$env:DATABASE_URL = ($line.Trim() -replace '/blizu$', "/$Db")
$env:DATA_DIR = "apps/otporno/data"
$mail = (Get-Content "$root\.env" | Where-Object { $_ -match '^CONTACT_EMAIL=' } | Select-Object -First 1) -replace '^CONTACT_EMAIL=', ''
if ($mail) { $env:CONTACT_EMAIL = $mail.Trim() }
$env:RATE_LIMIT = "600/minute"
& uv run --package otporno-api python -X utf8 -m uvicorn otporno_api.main:app --host 127.0.0.1 --port $Port
