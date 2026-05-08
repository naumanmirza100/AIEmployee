"""One-shot smoke: verify resolve_for_call can now auto-create the quota row.

Run with: python manage.py shell < scripts/smoke_quota_auto_create.py

Pass through; expected output is either a CallContext or NoKeyAvailable
(which is the next layer down, NOT the schema bug).
"""
from core.models import Company, AgentTokenQuota
from core.api_key_service import resolve_for_call, NoKeyAvailable, QuotaExhausted

COMPANY_ID = 44

company = Company.objects.get(pk=COMPANY_ID)

print("Before:")
for agent in ["marketing_agent", "reply_draft_agent"]:
    q = AgentTokenQuota.objects.filter(company=company, agent_name=agent).first()
    print(f"  {agent}: {q and (q.included_tokens, q.used_tokens, q.managed_included_tokens, q.managed_used_tokens)}")

for agent in ["marketing_agent", "reply_draft_agent"]:
    print(f"\nresolve_for_call({agent!r}):")
    try:
        ctx = resolve_for_call(company, agent)
        print(f"  OK  mode={ctx.mode} provider={ctx.provider} key_id={ctx.key_id}")
    except NoKeyAvailable:
        print("  NoKeyAvailable (expected if no BYOK / managed / platform key set)")
    except QuotaExhausted:
        print("  QuotaExhausted")
    except Exception as e:
        print(f"  UNEXPECTED ERROR  {type(e).__name__}: {e}")

print("\nAfter:")
for agent in ["marketing_agent", "reply_draft_agent"]:
    q = AgentTokenQuota.objects.filter(company=company, agent_name=agent).first()
    print(f"  {agent}: {q and (q.included_tokens, q.used_tokens, q.managed_included_tokens, q.managed_used_tokens)}")
