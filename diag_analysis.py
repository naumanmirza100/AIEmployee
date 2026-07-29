"""Check whether inbox emails / campaign replies actually have AI analysis
stored. If the fields are empty, the frontend correctly renders nothing —
the problem is upstream (analysis not run), not the UI.

Run:  python manage.py shell -c "exec(open('diag_analysis.py').read())"
"""
from reply_draft_agent.models import InboxEmail

qs = InboxEmail.objects.filter(direction='in').order_by('-received_at')[:15]
print("Recent INBOX emails (direction='in'):")
print("id | received | interest_level | analysis_len | subject")
for m in qs:
    a = (m.analysis or '')
    print("  %s | %s | %r | %d | %r" % (
        m.id,
        m.received_at.strftime('%Y-%m-%d %H:%M') if m.received_at else '-',
        m.interest_level,
        len(a),
        (m.subject or '')[:40],
    ))

total = InboxEmail.objects.filter(direction='in').count()
with_analysis = InboxEmail.objects.filter(direction='in').exclude(analysis='').exclude(analysis__isnull=True).count()
with_interest = InboxEmail.objects.filter(direction='in').exclude(interest_level='').exclude(interest_level__isnull=True).count()
print("\nTotals (inbound): %d emails, %d have analysis text, %d have interest_level" % (
    total, with_analysis, with_interest))
