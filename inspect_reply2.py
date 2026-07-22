"""Why is the 'lets do it i like ur content' reply not analyzed?
Run:  python inspect_reply2.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Reply

EMAIL = 'noorfatima262004@gmail.com'
for r in Reply.objects.filter(lead__email__iexact=EMAIL).order_by('-created_at')[:6]:
    print("-" * 60)
    print(f"reply#{r.id}  at={r.created_at}")
    print(f"  interest_level = {r.interest_level!r}")
    print(f"  subject        = {(r.reply_subject or '')!r}")
    print(f"  content        = {(r.reply_content or '')[:100]!r}")
    print(f"  analysis       = {(r.analysis or '')[:180]!r}")
    print(f"  seq={r.sequence.name if r.sequence else None} sub={r.sub_sequence.name if r.sub_sequence else None}")
