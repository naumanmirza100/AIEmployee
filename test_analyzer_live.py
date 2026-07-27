"""Run the CURRENT on-disk analyzer on the failing reply text and show the real
error (if any). This uses freshly-loaded code, so it tells us whether the bug is
still in the code (disk) or only in a stale running process.
    python test_analyzer_live.py
"""
import os, django, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.utils.reply_analyzer import ReplyAnalyzer

text = ("thank you for the information\r\n\r\n"
        "On Mon, Jul 20, 2026 at 9:48 PM <sales@laskontech.com> wrote:\r\n\r\n"
        "> View in browser\r\n> <http://localhost:8000/token?...>\r\n")

az = ReplyAnalyzer()
try:
    res = az.analyze_reply(reply_subject="Re: Join Our New Community", reply_content=text, campaign_name="test")
    print("RESULT:", res)
except Exception as e:
    print("EXCEPTION:", repr(e))
    traceback.print_exc()
