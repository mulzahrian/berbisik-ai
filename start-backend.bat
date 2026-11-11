@echo off
cd /d "%~dp0backend"
if not exist .venv\Scripts\python.exe (
  echo [!] Virtualenv belum ada. Lihat README.md bagian Instalasi.
  pause
  exit /b 1
)
set HF_HUB_OFFLINE=1
set TRANSFORMERS_OFFLINE=1
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
