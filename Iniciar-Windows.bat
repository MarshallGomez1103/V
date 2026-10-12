@echo off
rem DEPRECATED: use Start-V-Windows.bat. This wrapper stays for one release.
call "%~dp0Start-V-Windows.bat" %*
exit /b %errorlevel%
