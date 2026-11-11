@echo off
echo Menghentikan Berbisik AI (backend :8000 dan frontend :5173)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ids = Get-NetTCPConnection -State Listen -LocalPort 8000,5173 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique;" ^
  "if (-not $ids) { Write-Host 'Tidak ada yang berjalan.'; exit };" ^
  "foreach ($id in $ids) { $p = Get-Process -Id $id -ErrorAction SilentlyContinue; if ($p) { Write-Host ('Stop ' + $p.ProcessName + ' (PID ' + $id + ')'); Stop-Process -Id $id -Force } }"
taskkill /FI "WINDOWTITLE eq TTS Backend*" >nul 2>&1
taskkill /FI "WINDOWTITLE eq TTS Frontend*" >nul 2>&1
echo Selesai.
timeout /t 3 >nul
