@echo off
setlocal
cd /d "%~dp0"
set "SIMRATE_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "SIMRATE_PYTHON=.venv\Scripts\python.exe"
"%SIMRATE_PYTHON%" -m PyInstaller --noconfirm --clean -F -w -n MSFS-SimRate-Monitor -i mini_gui_icon.ico --add-data "mini_gui_icon.ico;." --add-binary "SimConnect\SimConnect.dll;SimConnect" mini_gui.py
exit /b %errorlevel%
