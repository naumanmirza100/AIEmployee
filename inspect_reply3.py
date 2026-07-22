import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()
from marketing_agent.models import Reply

EMAIL = 'noor262004fatima@gmail.com'
for r in Reply.objects.filter(lead__email__iexact=EMAIL).order_by('-created_at')[:4]:
    print("-" * 60)
    print(f"reply#{r.id} at={r.created_at}")
    print(f"  interest = {r.interest_level!r}")
    print(f"  subject  = {(r.reply_subject or '')!r}")
    print(f"  content  = {(r.reply_content or '')[:120]!r}")
    print(f"  analysis = {(r.analysis or '')[:200]!r}")
