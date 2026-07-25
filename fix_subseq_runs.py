"""
Re-activate the campaign's sub-sequences (they got deactivated when the campaign
was paused), then create the missing ReplySubSequenceRun for any main-sequence
reply that should have triggered one but didn't (because no ACTIVE sub-seq
existed at the time).

DRY RUN by default. Apply with:  python fix_subseq_runs.py --apply
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Campaign, EmailSequence, Reply, ReplySubSequenceRun

APPLY = '--apply' in sys.argv
camp = Campaign.objects.filter(name='new1234').first() or Campaign.objects.filter(status='active').first()
print(f"Campaign: {camp.name} (id={camp.id}, status={camp.status})\n")

# 1) Re-activate sub-sequences (and their parent main sequences) for this campaign.
subs = EmailSequence.objects.filter(campaign=camp, is_sub_sequence=True)
inactive = subs.filter(is_active=False)
print(f"Sub-sequences inactive: {inactive.count()} of {subs.count()}")
if APPLY:
    subs.update(is_active=True)
    # Parent main sequences too, so sending isn't blocked.
    parent_ids = [s.parent_sequence_id for s in subs if s.parent_sequence_id]
    EmailSequence.objects.filter(id__in=parent_ids).update(is_active=True)
    print("  -> re-activated all sub-sequences and their parents.")

# 2) Backfill missing runs. For each main-sequence reply with a real interest and
#    no run yet, find the matching active sub-seq (exact interest -> 'any') and
#    create a run.
INTERESTS = ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']
created = 0
checked = 0
for r in Reply.objects.filter(campaign=camp).select_related('lead', 'contact', 'sequence'):
    if r.sub_sequence_id:            # reply was TO a sub-seq email — never creates a run
        continue
    if ReplySubSequenceRun.objects.filter(reply=r).exists():
        continue
    lvl = (r.interest_level or 'not_analyzed')
    if lvl not in INTERESTS:
        continue
    parent_seq = r.sequence or getattr(r.contact, 'sequence', None)
    if not parent_seq:
        continue
    sub = (EmailSequence.objects.filter(parent_sequence=parent_seq, is_sub_sequence=True, is_active=True, interest_level=lvl).first()
           or EmailSequence.objects.filter(parent_sequence=parent_seq, is_sub_sequence=True, is_active=True, interest_level='any').first())
    checked += 1
    if not sub:
        print(f"  reply#{r.id} {r.lead.email} interest={lvl}: no matching active sub-seq — skipped")
        continue
    print(f"  reply#{r.id} {r.lead.email} interest={lvl} -> would create run '{sub.name}'")
    if APPLY:
        ReplySubSequenceRun.objects.get_or_create(
            reply=r,
            defaults={'contact': r.contact, 'campaign': camp, 'lead': r.lead,
                      'sub_sequence': sub, 'interest_level': lvl},
        )
        created += 1

print(f"\n{'CREATED' if APPLY else 'WOULD CREATE'} {created if APPLY else checked} run(s).")
if not APPLY:
    print("DRY RUN — re-run with --apply to activate sub-seqs and backfill runs.")
