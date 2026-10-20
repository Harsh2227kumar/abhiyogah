@echo off
rem Windows entry point for the developer commands; no GNU make needed.
rem Usage (cmd or PowerShell, from the repository root): .\make check
rem Every target lives in scripts\dev.py, the same one the Makefile calls. See CLAUDE.md "Commands".
if "%UV%"=="" set "UV=uv"
"%UV%" run --no-project python "%~dp0scripts\dev.py" %*
