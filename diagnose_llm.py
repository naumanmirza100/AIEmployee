"""Find out WHY the Groq LLM call fails (the empty 'Error analyzing reply:').
Calls the analyzer's LLM path directly with full traceback.
    python diagnose_llm.py
"""
import os, django, traceback
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from marketing_agent.models import Campaign
from marketing_agent.utils.reply_analyzer import ReplyAnalyzer
from marketing_agent.services.reply_processor import _company_id_for_campaign

camp = Campaign.objects.filter(status='active').first()
cid = _company_id_for_campaign(camp) if camp else None
print(f"Campaign: {camp.name if camp else None}  company_id={cid}")

az = ReplyAnalyzer()
az.company_id = cid
az.agent_key_name = 'marketing_agent'

print("\n--- Trying a direct Groq call ---")
try:
    out = az._call_groq_qa("Reply to classify: 'dont send it again'. Return one word.", "You classify email replies.", temperature=0.3, max_tokens=50)
    print("SUCCESS. Response:", repr(out)[:300])
except Exception as e:
    print("FAILED with full traceback:")
    traceback.print_exc()

# Also check what key the service resolves for this company/agent
print("\n--- Key resolution ---")
try:
    from core.api_key_service import resolve_for_call
    from core.models import Company
    if cid:
        ctx = resolve_for_call(Company.objects.get(pk=cid), 'marketing_agent')
        print("Resolved key ctx:", ctx)
    else:
        print("No company_id — cannot resolve a managed key.")
except Exception as e:
    print("Key resolution error:")
    traceback.print_exc()
