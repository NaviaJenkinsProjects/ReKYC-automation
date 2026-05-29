@echo off
cd /d %~dp0
set "LOCAL_PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
set "CODEX_PY=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if exist "%LOCAL_PY%" (
  "%LOCAL_PY%" -m pytest --version >nul 2>nul
  if not errorlevel 1 (
    "%LOCAL_PY%" ReKYC_Agent.py
    goto done
  )
)

python -m pytest --version >nul 2>nul
if not errorlevel 1 (
  python ReKYC_Agent.py
  goto done
)

if exist "%CODEX_PY%" (
  "%CODEX_PY%" ReKYC_Agent.py
) else (
  python ReKYC_Agent.py
)

:done
pause
