import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()
from django.utils import timezone
from datetime import timedelta
from marketing_agent.models import Campaign, ReplySubSequenceRun

camp = Campaign.objects.filter(name='new1234').first()
now = timezone.now()
horizon = now + timedelta(hours=24)
print(f"Campaign: {camp.name}   now={now}\n")

runs = ReplySubSequenceRun.objects.filter(campaign=camp).select_related('lead', 'sub_sequence', 'reply')
print(f"Total runs: {runs.count()}")
print("Pending/incomplete runs (completed=False, cancelled=False):")
for r in runs.filter(completed=False, cancelled=False):
    sub = r.sub_sequence
    steps = list(sub.steps.all().order_by('step_order'))
    nxt = next((s for s in steps if s.step_order == r.step + 1), None)
    if not nxt:
        state = f"NO next step (step={r.step}, total={len(steps)}) -> nothing to send"
    else:
        if r.step == 0:
            ref = (r.reply.replied_at if r.reply_id else None) or r.created_at
        else:
            ref = r.last_sent_at or now
        send_time = ref + timedelta(days=nxt.delay_days, hours=nxt.delay_hours, minutes=nxt.delay_minutes)
        when = 'PENDING (due now)' if send_time <= now else ('UPCOMING (<=24h)' if send_time <= horizon else f'later ({send_time})')
        state = f"step={r.step} next=step{nxt.step_order} send_time={send_time.strftime('%H:%M')} -> {when}"
    print(f"  run#{r.id} {r.lead.email:28} '{sub.name}'  {state}")

print("\nCompleted runs:", runs.filter(completed=True).count(), " Cancelled:", runs.filter(cancelled=True).count())
