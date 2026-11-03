"""One-off: drain the stuck SDR qualification queue.

The embedded scheduler was not running (SDR_SCHEDULER_ENABLED unset), so ~1k
leads sat in qualification_status='pending' forever. This loops the real queue
drainer until the backlog clears or stops making progress.
"""
import os
import sys
import time

# Running `python scripts/x.py` puts scripts/ on sys.path, not the repo root,
# so the project package isn't importable. Add the repo root explicitly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.db.models import Count
from ai_sdr_agent.models import SDRLead
from ai_sdr_agent.tasks import qualify_queue_impl


def pending_count():
    return SDRLead.objects.filter(qualification_status='pending').count()


total_qualified = 0
stuck_rounds = 0
start_pending = pending_count()
print(f"START pending={start_pending}", flush=True)

for i in range(600):
    before = pending_count()
    if before == 0:
        print("DONE: queue empty", flush=True)
        break
    r = qualify_queue_impl()
    total_qualified += r.get('qualified', 0)
    after = pending_count()
    if i % 10 == 0:
        print(f"iter={i} processed={r['processed']} qualified={r['qualified']} "
              f"failed={r['failed']} pending={after}", flush=True)
    # Stop if we're not reducing the backlog (e.g. rate-limited / all failing).
    if after >= before:
        stuck_rounds += 1
        if stuck_rounds >= 8:
            print(f"STOP: no progress for {stuck_rounds} rounds (pending={after}). "
                  f"Likely LLM rate-limit/quota — will resume on next run.", flush=True)
            break
    else:
        stuck_rounds = 0
    time.sleep(0.4)  # be gentle on the Groq rate limit

status = dict((x['qualification_status'], x['n'])
              for x in SDRLead.objects.values('qualification_status').annotate(n=Count('id')))
print(f"FINAL total_qualified={total_qualified} status={status}", flush=True)
