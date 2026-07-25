import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()
from marketing_agent.models import Reply
from django.utils import timezone

print("Now (UTC):", timezone.now())
print("Latest 6 replies (any lead):")
for r in Reply.objects.order_by('-created_at')[:6]:
    print(f"  #{r.id} {r.lead.email}  at={r.created_at}  interest={r.interest_level!r}  subj={(r.reply_subject or '')[:40]!r}")
