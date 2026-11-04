$ErrorActionPreference = "Continue"
$root = "C:\ajmobree\projekt1\datathon-2026"
Set-Location $root
$env:PYTHONUTF8 = "1"
$line = (Get-Content "$root\.env" | Where-Object { $_ -match '^DATABASE_URL=' } | Select-Object -First 1) -replace '^DATABASE_URL=', ''
$env:DATABASE_URL = ($line.Trim() -replace '/blizu$', '/otporno')
$env:DATA_DIR = "apps/otporno/data"
$log = "$root\apps\otporno\data\cache_heat.log"
while ($true) {
  "[{0}] start heat-grid job" -f (Get-Date -Format s) | Add-Content $log
  & uv run --package otporno-api python -X utf8 -m otporno_api.cli ingest heat-grid --lau HR_01791 --lau HR_01333 --grid-first 30 *>> $log
  if ($LASTEXITCODE -eq 0) { "[{0}] job finished" -f (Get-Date -Format s) | Add-Content $log; break }
  "[{0}] job exited with {1}; restarting in 120 s" -f (Get-Date -Format s), $LASTEXITCODE | Add-Content $log
  Start-Sleep 120
}
