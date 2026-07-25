"""
Verify the quote-stripping fix: a positive reply whose quoted thread contains
"dont send again" must NOT be classified as unsubscribe.
Run:  python test_analyzer_fix.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.utils.reply_analyzer import strip_quoted_thread, ReplyAnalyzer

# 1) Unit test the stripper directly (no LLM needed).
gmail_reply = (
    "Sure lets discuss.\r\n\r\n"
    "On Mon, 20 Jul 2026 at 21:54, <sales@laskontech.com> wrote:\r\n"
    "> Dont send again\r\n"
    "> View in browser\r\n"
)
stripped = strip_quoted_thread(gmail_reply)
print("STRIP TEST:")
print(f"  new-reply-only = {stripped!r}")
print(f"  contains 'dont send'? {'dont send' in stripped.lower()}  (should be False)")

outlook_reply = (
    "Great, count me in!\n"
    "-----Original Message-----\n"
    "From: sales@x.com\n"
    "Sent: Monday\n"
    "unsubscribe me\n"
)
stripped2 = strip_quoted_thread(outlook_reply)
print(f"  outlook new-reply-only = {stripped2!r}")
print(f"  contains 'unsubscribe'? {'unsubscribe' in stripped2.lower()}  (should be False)")

# 2) Rule-override path: feed the raw gmail reply through the analyzer's rule
#    overrides only (skip the LLM by calling _apply_rule_overrides on stripped text).
az = ReplyAnalyzer()
combined = f" {strip_quoted_thread(gmail_reply)}".lower()
override = az._apply_rule_overrides(combined, 'positive')
print("\nRULE-OVERRIDE TEST on 'Sure lets discuss' (quoted 'dont send again'):")
print(f"  override result = {override!r}  (should be None -> stays positive, NOT 'unsubscribe')")

print("\nRESULT:", "PASS ✅" if ('dont send' not in stripped.lower() and override != 'unsubscribe') else "FAIL ❌")
