"""Re-run the analyzer on any reply stuck at 'not_analyzed' (failed under old code).
RUN THIS *AFTER* restarting the backend, so the fixed code is loaded.
    python reanalyze_failed.py
"""
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Reply
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
from marketing_agent.services.reply_processor import _company_id_for_campaign

VALID = ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']
az = ReplyAnalyzer()

stuck = list(Reply.objects.filter(interest_level='not_analyzed').select_related('campaign', 'lead', 'contact'))
print(f"Found {len(stuck)} reply/replies stuck at 'not_analyzed'.")
for r in stuck:
    try:
        res = az.analyze_reply(
            reply_subject=r.reply_subject or '',
            reply_content=r.reply_content or '',
            campaign_name=r.campaign.name if r.campaign else '',
            company_id=_company_id_for_campaign(r.campaign) if r.campaign else None,
        )
        lvl = (res.get('interest_level') or '').lower()
        if lvl in VALID:
            r.interest_level = lvl
            r.analysis = (res.get('analysis') or '')[:2000]
            r.save(update_fields=['interest_level', 'analysis'])
            if r.contact:
                r.contact.reply_interest_level = lvl
                r.contact.save(update_fields=['reply_interest_level'])
            print(f"  reply#{r.id} {r.lead.email}: not_analyzed -> {lvl}")
        else:
            print(f"  reply#{r.id}: invalid level {lvl!r}, skipped")
    except Exception as e:
        print(f"  reply#{r.id}: FAILED AGAIN -> {e!r}  (did you restart the backend?)")
