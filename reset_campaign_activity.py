"""
Reset the EMAIL SENDING ACTIVITY of a campaign so it can be tested fresh, WITHOUT
deleting the campaign, its leads, sequences, sub-sequences or templates.

Deletes: EmailSendHistory, Reply, ReplySubSequenceRun for the campaign.
Resets:  CampaignContact progress (step counters, replied flags, sub-seq state).

DRY RUN by default — shows counts only. To actually delete, run with:
    python reset_campaign_activity.py --apply
"""
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import (
    Campaign, EmailSendHistory, Reply, ReplySubSequenceRun, CampaignContact,
)

CAMPAIGN_NAME = 'er5t6y7u89'
APPLY = '--apply' in sys.argv

camp = Campaign.objects.filter(name=CAMPAIGN_NAME).first()
if not camp:
    print(f"No campaign named {CAMPAIGN_NAME!r} found.")
    sys.exit(1)

print(f"Campaign: {camp.name} (id={camp.id}, company/owner={camp.owner_id}, status={camp.status})")

if camp.status == 'active':
    print("\n⚠️  WARNING: campaign is ACTIVE. The background scheduler runs every")
    print("   5 minutes, so it will RE-SEND emails (contacts get reset to step 0)")
    print("   and RE-SYNC the same replies from the mailbox right after you delete.")
    print("   With --apply this script PAUSES the campaign so the reset sticks.")
    print("   Re-activate it from the UI when you're ready to test.")
    print("   NOTE: the old reply emails are still in the Gmail inbox — inbox-sync")
    print("   may re-detect them. Delete/archive them in Gmail for a truly clean test.")

sends = EmailSendHistory.objects.filter(campaign=camp)
replies = Reply.objects.filter(campaign=camp)
runs = ReplySubSequenceRun.objects.filter(campaign=camp)
contacts = CampaignContact.objects.filter(campaign=camp)

print("\nWILL DELETE:")
print(f"  EmailSendHistory     : {sends.count()}")
print(f"  Reply                : {replies.count()}")
print(f"  ReplySubSequenceRun  : {runs.count()}")
print("\nWILL RESET (not delete):")
print(f"  CampaignContact rows : {contacts.count()}  (progress/replied/sub-seq state)")
print("\nKEPT (untouched): campaign, leads, sequences, sub-sequences, templates.")

if not APPLY:
    print("\nDRY RUN — nothing changed. Re-run with --apply to perform the reset.")
    sys.exit(0)

# --- Perform ---
# Pause first so the scheduler can't re-send / re-sync between delete and reset.
was_active = camp.status == 'active'
if was_active:
    camp.status = 'paused'
    camp.save(update_fields=['status'])
    print("Paused campaign (was active) so the reset sticks.")

d1 = runs.delete()
d2 = replies.delete()
d3 = sends.delete()

# Reset contact progress so main sequences start over and no stale sub-seq remains.
reset_count = contacts.update(
    current_step=0,
    last_sent_at=None,
    completed=False,
    completed_at=None,
    replied=False,
    replied_at=None,
    reply_subject='',
    reply_content='',
    reply_interest_level='not_analyzed',
    reply_analysis='',
    sub_sequence=None,
    sub_sequence_step=0,
    sub_sequence_last_sent_at=None,
    sub_sequence_completed=False,
)

print("\nDONE.")
print(f"  Deleted runs   : {d1}")
print(f"  Deleted replies: {d2}")
print(f"  Deleted sends  : {d3}")
print(f"  Reset contacts : {reset_count}")
