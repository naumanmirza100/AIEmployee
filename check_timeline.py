import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()
from marketing_agent.models import Reply, ReplySubSequenceRun, Campaign

camp = Campaign.objects.filter(name='new1234').first()
print(f"Campaign: {camp.name}\n")
print("Replies (oldest first) — when created, and did/when a run get created:")
for r in Reply.objects.filter(campaign=camp).select_related('lead').order_by('created_at'):
    run = ReplySubSequenceRun.objects.filter(reply=r).first()
    run_at = run.created_at.strftime('%H:%M:%S') if run else '—'
    print(f"  reply#{r.id}  {r.created_at.strftime('%Y-%m-%d %H:%M:%S')}  "
          f"{r.lead.email:30} {r.interest_level:14} run_created={run_at}")
