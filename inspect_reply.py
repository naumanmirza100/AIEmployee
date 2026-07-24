"""
Why did the AI not detect interest on the latest reply?
Run:  python manage.py shell < inspect_reply.py
"""
from marketing_agent.models import Reply

qs = Reply.objects.order_by('-created_at')[:5]
print("=" * 70)
print(f"Latest {qs.count()} replies:")
for r in qs:
    print("-" * 70)
    print(f"  id={r.id}  lead={r.lead.email}  campaign={r.campaign.name}")
    print(f"  interest_level = {r.interest_level!r}")
    print(f"  created_at     = {r.created_at}")
    print(f"  subject        = {getattr(r, 'reply_subject', '?')!r}")
    print(f"  content        = {(getattr(r, 'reply_content', '') or '')[:120]!r}")
    print(f"  analysis       = {(getattr(r, 'analysis', '') or '')[:200]!r}")
    print(f"  is_sub_seq     = {getattr(r, 'is_sub_sequence_reply', '?')}")

print("=" * 70)
# Quick test: run the analyzer live on this reply's text to see if the LLM works at all
try:
    from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
    latest = qs[0]
    print("LIVE analyzer test on latest reply text:")
    res = ReplyAnalyzer().analyze_reply(
        reply_subject=getattr(latest, 'reply_subject', '') or '',
        reply_content=getattr(latest, 'reply_content', '') or 'Thank you, looking forward to it!',
        campaign_name=latest.campaign.name,
    )
    print("  RESULT:", res)
except Exception as e:
    import traceback
    print("  LIVE TEST FAILED:", repr(e))
    traceback.print_exc()
print("=" * 70)
