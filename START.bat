@echo off
title GMB Lead Extractor Pro
color 0A
echo.
echo  ============================================
echo   GMB LEAD EXTRACTOR PRO - Starting...
echo  ============================================
echo.
echo  [1/2] Checking Python...
python --version
echo.
echo  [2/2] Starting Server...
echo.
echo  Browser mein yeh address kholo:
echo  -----------------------------------
echo   http://localhost:8080
echo  -----------------------------------
echo.
echo  Band karna ho toh Ctrl+C dabaao
echo.
python app.py
pause
