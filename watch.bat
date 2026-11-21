@echo off
rem Leave this window open: new shipping*.pdf downloads are stamped automatically.
cd /d "%~dp0"
call :pick
%PY% stamp_sku.py --watch
pause
exit /b
:pick
for %%P in ("py -3" "python") do (
  %%~P -c "import pdfplumber, pypdf, reportlab" >nul 2>nul && (set PY=%%~P& goto :eof)
)
echo No Python with the required packages found. Run:  py -m pip install -r requirements.txt
set PY=python
goto :eof
