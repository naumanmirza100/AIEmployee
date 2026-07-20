"""
Why didn't the sub-sequence email go out for the 'Requested Info' lead?
Run:  python manage.py shell < inspect_subseq.py
"""
from marketing_agent.models import CampaignContact, EmailSequence, Reply

EMAIL = 'noor262004fatima@gmail.com'
out = []

contacts = CampaignContact.objects.filter(lead__email__iexact=EMAIL).select_related('sequence', 'sub_sequence', 'lead')
out.append(f"CONTACTS for {EMAIL}: {contacts.count()}")
for c in contacts:
    out.append(
        f"  contact#{c.id} seq={c.sequence.name if c.sequence else None} "
        f"replied={c.replied} interest={c.reply_interest_level!r} "
        f"sub_seq={c.sub_sequence.name if c.sub_sequence else None} "
        f"sub_step={c.sub_sequence_step} sub_done={c.sub_sequence_completed} "
        f"replied_at={c.replied_at}"
    )

# What sub-sequences exist on this campaign's main sequence(s)?
out.append("SUB-SEQUENCES available (per main sequence):")
for c in contacts:
    if not c.sequence:
        continue
    subs = EmailSequence.objects.filter(parent_sequence=c.sequence, is_sub_sequence=True)
    for s in subs:
        out.append(
            f"  under '{c.sequence.name}': sub='{s.name}' interest_level={s.interest_level!r} "
            f"active={s.is_active} steps={s.steps.count()}"
        )
    if not subs.exists():
        out.append(f"  under '{c.sequence.name}': (no sub-sequences)")

# Latest replies + detected interest
out.append("REPLIES:")
for r in Reply.objects.filter(lead__email__iexact=EMAIL).order_by('-created_at')[:5]:
    out.append(f"  reply#{r.id} interest={r.interest_level!r} at={r.created_at} content={(r.reply_content or '')[:60]!r}")

print("SUBSEQ_DEBUG || " + " || ".join(out))
