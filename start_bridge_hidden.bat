@echo off
rem Start the bridge with no console window. Output goes to bridge.log.
cd /d "%~dp0"
start "" "C:\Program Files\Python312\pythonw.exe" claude_usage_bridge.py --interval 60
