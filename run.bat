@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Username Bot
py -3.13 bot.py
if errorlevel 9009 python bot.py
pause
