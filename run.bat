@echo off
rem Double-click: stamps the newest shipping*.pdf in your Downloads folder.
rem Drag a PDF onto this file: stamps that PDF.
cd /d "%~dp0"
call :pick
%PY% stamp_sku.py %*
echo.
pause
exit /b
:pick
rem use the first Python that actually has the needed packages
for %%P in ("py -3" "python") do (
  %%~P -c "import pdfplumber, pypdf, reportlab" >nul 2>nul && (set PY=%%~P& goto :eof)
)
echo No Python with the required packages found. Run:  py -m pip install -r requirements.txt
set PY=python
goto :eof
