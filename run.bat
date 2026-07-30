@echo off

:: Start Django backend
start "Backend" cmd /k "call venv\Scripts\activate && python manage.py runserver"

:: Start React/Vite frontend
start "Frontend" cmd /k "cd PaPerProjectFront && npm run dev"