"""Root-cause diagnostic for the 'both replies got same interest' bug.
Shows each reply's STORED content + interest, then RE-RUNS the current analyzer
live on that exact content so we can see where the classification goes wrong.
    python diagnose_reply.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Reply
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer, strip_quoted_thread
from marketing_agent.services.reply_processor import _company_id_for_campaign

EMAIL = 'fatimahnooray@gmail.com'
az = ReplyAnalyzer()

replies = list(Reply.objects.filter(lead__email__iexact=EMAIL).order_by('-created_at')[:4])
print(f"=== {len(replies)} recent replies for {EMAIL} ===\n")

for r in replies:
    print("=" * 70)
    print(f"reply#{r.id}  at={r.created_at}")
    print(f"  responded to email: {(r.reply_subject or '')!r}")
    print(f"  STORED interest    : {r.interest_level!r}")
    print(f"  RAW content        : {(r.reply_content or '')[:150]!r}")
    stripped = strip_quoted_thread(r.reply_content or '')
    print(f"  QUOTE-STRIPPED     : {stripped!r}")
    # Re-run analyzer live on the stored content:
    try:
        res = az.analyze_reply(
            reply_subject=r.reply_subject or '',
            reply_content=r.reply_content or '',
            campaign_name=r.campaign.name if r.campaign else '',
            company_id=_company_id_for_campaign(r.campaign) if r.campaign else None,
        )
        print(f"  LIVE re-analysis   : {res.get('interest_level')!r}  ({res.get('analysis','')[:80]})")
    except Exception as e:
        print(f"  LIVE re-analysis   : ERROR {e!r}")
    print()
