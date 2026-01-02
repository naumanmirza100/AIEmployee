@echo off
REM Batch file to run Django management command for sending sequence emails
REM This file is used by Windows Task Scheduler

REM Set UTF-8 encoding to prevent Unicode errors
chcp 65001 >nul

REM Change to project directory
cd /d "D:\University\work\AI_Employyes\AIEmployee"

REM Log start time
echo [%date% %time%] Starting send_sequence_emails... >> send_sequence_emails.log

REM Run the Django management command
python manage.py send_sequence_emails >> send_sequence_emails.log 2>&1

REM Log completion time
echo [%date% %time%] Completed. >> send_sequence_emails.log
echo. >> send_sequence_emails.log


