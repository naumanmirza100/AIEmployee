"""Which replies got a ReplySubSequenceRun and which didn't — and why.
    python diagnose_runs.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Reply, ReplySubSequenceRun, EmailSequence, Campaign

camp = Campaign.objects.filter(name='new1234').first() or Campaign.objects.filter(status='active').first()
print(f"Campaign: {camp.name} (id={camp.id})\n")

# What sub-sequences exist and for which interest levels?
print("Sub-sequences available:")
for s in EmailSequence.objects.filter(campaign=camp, is_sub_sequence=True):
    print(f"  '{s.name}'  interest={s.interest_level!r}  active={s.is_active}  steps={s.steps.count()}  parent={s.parent_sequence_id}")
print()

# Each recent reply: interest + did it get a run?
print("Recent replies -> run?")
for r in Reply.objects.filter(campaign=camp).select_related('lead', 'sequence').order_by('-created_at')[:16]:
    run = ReplySubSequenceRun.objects.filter(reply=r).first()
    is_sub_reply = bool(r.sub_sequence_id)  # reply was TO a sub-seq email (design: no new run)
    print(
        f"  reply#{r.id} {r.lead.email:32} interest={r.interest_level:14} "
        f"reply_to_subseq={is_sub_reply}  RUN={'YES ' + run.sub_sequence.name if run else 'NO'}"
    )
