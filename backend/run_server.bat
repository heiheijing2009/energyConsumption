@echo off
setlocal
cd /d "%~dp0\.."
if not defined APP_SECRET set APP_SECRET=change-this-secret-before-production
if not defined ADMIN_USERNAME set ADMIN_USERNAME=admin
if not defined ADMIN_PASSWORD set ADMIN_PASSWORD=admin123456
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
