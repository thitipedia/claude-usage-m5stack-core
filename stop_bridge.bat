@echo off
rem Stop any running bridge (hidden or not).
powershell -NoProfile -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -and $_.CommandLine -like '*claude_usage_bridge.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force; Write-Host Stopped PID $_.ProcessId }"
