@echo off
cd /d "%~dp0"
python -c "import streamlit, requests" 2>nul || python -m pip install -r requirements.txt
python -m streamlit run app.py --browser.gatherUsageStats=false
pause
