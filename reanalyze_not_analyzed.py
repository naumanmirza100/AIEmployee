"""
Re-run the AI analyzer on replies stuck at 'not_analyzed' (they failed earlier due
to the json-scope bug in reply_analyzer.py, now fixed).
Run:  python manage.py shell < reanalyze_not_analyzed.py
"""
from marketing_agent.models import Reply
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
from marketing_agent.services.reply_processor import _company_id_for_campaign

VALID = ['positive', 'negative', 'neutral', 'requested_info', 'objection', 'unsubscribe']
analyzer = ReplyAnalyzer()

# Re-run ALL replies here (not just not_analyzed) so we can see the AI path work.
stuck = list(Reply.objects.select_related('contact', 'campaign', 'lead').order_by('-created_at')[:10])
lines = [f"Re-analyzing {len(stuck)} recent reply/replies (AI path)."]

for r in stuck:
    try:
        res = analyzer.analyze_reply(
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
            lines.append(f"  Reply #{r.id} {r.lead.email}: not_analyzed -> {lvl}")
        else:
            lines.append(f"  Reply #{r.id} {r.lead.email}: got invalid level {lvl!r}, left as-is")
    except Exception as e:
        lines.append(f"  Reply #{r.id} {r.lead.email}: FAILED AGAIN -> {e!r}")

print("REANALYZE_RESULT || " + " || ".join(lines))
