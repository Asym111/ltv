@echo off
chdir /d "C:\Users\Ассым\ltv\ltv"
call .\.venv\Scripts\activate.bat
python diagnose_system.py
pause
