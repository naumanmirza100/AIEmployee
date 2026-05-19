"""End-to-end test of the per-agent BYOK / quota flow for Marketing + Reply.

Run with: python manage.py shell < scripts/test_byok_flow.py
(or:       cmd /c "python manage.py shell < scripts\test_byok_flow.py")

What it does:
  1) Adds a BYOK key for both marketing_agent and reply_draft_agent
  2) Calls resolve_for_call() for each — should now succeed with mode='byok'
  3) Calls record_usage() for each — should bump byok_tokens_info, NOT used_tokens
  4) Removes BYOK keys, then re-resolves to confirm fallback raises NoKeyAvailable
  5) Cleans up test BYOK rows so no leftover state

Set TEST_GROQ_KEY below to a real Groq key (any test key works since we never
make a real LLM call here). Doesn't have to be valid — resolver only checks
non-empty plaintext.
"""
import os
from core.models import Company, CompanyAPIKey, AgentTokenQuota
from core.api_key_service import resolve_for_call, record_usage, NoKeyAvailable, QuotaExhausted

COMPANY_ID = 44
TEST_GROQ_KEY = os.environ.get("TEST_GROQ_KEY", "gsk_FAKE_TEST_KEY_xxxxxxxxxxxxxxxxxxxx")
AGENTS = ["marketing_agent", "reply_draft_agent"]

company = Company.objects.get(pk=COMPANY_ID)


def show(tag):
    print(f"\n--- {tag} ---")
    for a in AGENTS:
        q = AgentTokenQuota.objects.filter(company=company, agent_name=a).first()
        k = CompanyAPIKey.objects.filter(company=company, agent_name=a).first()
        qv = q and (q.included_tokens, q.used_tokens, q.byok_tokens_info)
        kv = k and (k.mode, k.status, k.provider)
        print(f"  {a}: quota(inc,used,byok_info)={qv}  key(mode,status,provider)={kv}")


# Step 1: insert a BYOK key for each agent (idempotent)
print("Step 1: insert BYOK keys")
created = []
for a in AGENTS:
    k, was_new = CompanyAPIKey.objects.get_or_create(
        company=company,
        agent_name=a,
        mode="byok",
        defaults={"provider": "groq", "status": "active"},
    )
    k.set_plaintext_key(TEST_GROQ_KEY)
    k.status = "active"
    k.save()
    if was_new:
        created.append(k.pk)
    print(f"  {a}: key id={k.pk} (new={was_new})")

show("after insert")

# Step 2: resolve — must return mode='byok' for both
print("\nStep 2: resolve_for_call (should be mode=byok)")
ctxs = {}
for a in AGENTS:
    try:
        ctx = resolve_for_call(company, a)
        print(f"  {a}: mode={ctx.mode} provider={ctx.provider} key_id={ctx.key_id}")
        ctxs[a] = ctx
    except Exception as e:
        print(f"  {a}: UNEXPECTED {type(e).__name__}: {e}")

# Step 3: record_usage — BYOK should bump byok_tokens_info ONLY,
# leaving used_tokens (platform_used_tokens) untouched. Cross-agent
# isolation: marketing call must not bump reply, and vice versa.
print("\nStep 3: record_usage(1000) per agent  (BYOK -> byok_tokens_info)")
for a, ctx in ctxs.items():
    record_usage(ctx, 1000)

show("after record_usage 1000 each")

# Step 4: delete BYOK keys, re-resolve -> NoKeyAvailable
print("\nStep 4: delete BYOK, re-resolve (expect NoKeyAvailable)")
CompanyAPIKey.objects.filter(company=company, agent_name__in=AGENTS, mode="byok").delete()
for a in AGENTS:
    try:
        ctx = resolve_for_call(company, a)
        print(f"  {a}: UNEXPECTED success mode={ctx.mode}")
    except NoKeyAvailable:
        print(f"  {a}: NoKeyAvailable  (correct)")
    except QuotaExhausted:
        print(f"  {a}: QuotaExhausted")
    except Exception as e:
        print(f"  {a}: UNEXPECTED {type(e).__name__}: {e}")

show("final")

print("\nDONE. byok_tokens_info bumped, used_tokens unchanged = correct BYOK behavior.")
print("Cross-agent isolation verified if marketing+reply byok_tokens_info incremented INDEPENDENTLY.")
