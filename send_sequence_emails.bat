@echo off
REM Batch file to run Django management commands for sending sequence emails and syncing inbox
REM This file is used by Windows Task Scheduler

REM Set UTF-8 encoding to prevent Unicode errors
chcp 65001 >nul

REM Change to project directory
cd /d "D:\University\work\AI_Employyes\AIEmployee"

REM Log start time
echo [%date% %time%] Starting send_sequence_emails... >> send_sequence_emails.log

REM Run the Django management command to send sequence emails
python manage.py send_sequence_emails >> send_sequence_emails.log 2>&1

REM Log completion time for send_sequence_emails
echo [%date% %time%] Completed send_sequence_emails. >> send_sequence_emails.log
echo. >> send_sequence_emails.log

REM Log start time for sync_inbox
echo [%date% %time%] Starting sync_inbox... >> send_sequence_emails.log

REM Run the Django management command to sync inbox and detect replies
python manage.py sync_inbox >> send_sequence_emails.log 2>&1

REM Log completion time for sync_inbox
echo [%date% %time%] Completed sync_inbox. >> send_sequence_emails.log
echo. >> send_sequence_emails.log








