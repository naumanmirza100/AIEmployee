"""Live end-to-end test: platform key -> real LLM call -> used_tokens decrements.

Pre-condition: set a real Groq platform key via the admin UI FIRST
  (SuperAdmin page -> Platform Keys tab -> Groq row -> Save)

Run: cmd /c "python manage.py shell < scripts\test_platform_live.py"

What it proves:
  1. resolver picks up platform key (mode='platform')
  2. actual Groq chat call goes through
  3. used_tokens increments for the called agent
  4. used_tokens for the OTHER agent stays unchanged (cross-agent isolation)
"""
from core.models import Company, AgentTokenQuota, PlatformAPIKey
from core.api_key_service import resolve_for_call, record_usage, NoKeyAvailable

COMPANY_ID = 44
AGENT_UNDER_TEST = "marketing_agent"
OTHER_AGENT = "reply_draft_agent"

company = Company.objects.get(pk=COMPANY_ID)


def read_quota(agent):
    q = AgentTokenQuota.objects.filter(company=company, agent_name=agent).first()
    return q and (q.included_tokens, q.used_tokens)


# Step 1: confirm platform key exists
pk = PlatformAPIKey.objects.filter(provider='groq', status='active').first()
if not pk or not pk.encrypted_key:
    print("STOP: no active Groq platform key found.")
    print("Go to Admin UI -> Platform Keys tab -> add a real Groq key first.")
    import sys; sys.exit(0)

print("Platform key found:", pk.masked_display)

before_test = read_quota(AGENT_UNDER_TEST)
before_other = read_quota(OTHER_AGENT)
print(f"\nBefore:  {AGENT_UNDER_TEST} used_tokens={before_test[1]}   {OTHER_AGENT} used_tokens={before_other[1]}")

# Step 2: resolve for marketing agent -> should be mode=platform
ctx = resolve_for_call(company, AGENT_UNDER_TEST)
print(f"Resolved: mode={ctx.mode} provider={ctx.provider}")
assert ctx.mode == 'platform', f"Expected mode=platform, got {ctx.mode}"

# Step 3: make a real Groq call (tiny prompt to minimise token spend)
from groq import Groq
client = Groq(api_key=ctx.api_key)
resp = client.chat.completions.create(
    model="llama-3.1-8b-instant",
    messages=[{"role": "user", "content": "Reply with just: OK"}],
    max_tokens=5,
)
total_tokens = resp.usage.total_tokens
answer = resp.choices[0].message.content.strip()
print(f"LLM response: {answer!r}   tokens used: {total_tokens}")

# Step 4: record usage
record_usage(ctx, total_tokens)

# Step 5: verify
after_test = read_quota(AGENT_UNDER_TEST)
after_other = read_quota(OTHER_AGENT)
print(f"\nAfter:   {AGENT_UNDER_TEST} used_tokens={after_test[1]}   {OTHER_AGENT} used_tokens={after_other[1]}")

delta_test = after_test[1] - before_test[1]
delta_other = after_other[1] - before_other[1]

print(f"\nResults:")
print(f"  {AGENT_UNDER_TEST} delta: +{delta_test} tokens (should be {total_tokens})")
print(f"  {OTHER_AGENT} delta:       +{delta_other} tokens (should be 0)")

ok = delta_test == total_tokens and delta_other == 0
print(f"\n{'ALL CHECKS PASSED' if ok else 'FAIL - check above'}")
