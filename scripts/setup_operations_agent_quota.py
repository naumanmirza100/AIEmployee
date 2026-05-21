"""
One-shot script: create AdminPricingConfig for operations_agent (1M tokens)
and fix any stale AgentTokenQuota rows that still have the 10K default.

Run with:
  python manage.py shell < scripts/setup_operations_agent_quota.py
"""
import django
django.setup()

from core.models import AdminPricingConfig, AgentTokenQuota

DEFAULT_FREE_TOKENS = 1_000_000
DEFAULT_MANAGED_TOKENS = 1_000_000

# 1. Create/update AdminPricingConfig
cfg, created = AdminPricingConfig.objects.get_or_create(
    agent_name='operations_agent',
    defaults={
        'free_tokens_on_purchase': DEFAULT_FREE_TOKENS,
        'managed_key_tokens': DEFAULT_MANAGED_TOKENS,
    },
)
if not created:
    changed = False
    if cfg.free_tokens_on_purchase != DEFAULT_FREE_TOKENS:
        cfg.free_tokens_on_purchase = DEFAULT_FREE_TOKENS
        changed = True
    if cfg.managed_key_tokens != DEFAULT_MANAGED_TOKENS:
        cfg.managed_key_tokens = DEFAULT_MANAGED_TOKENS
        changed = True
    if changed:
        cfg.save()
        print(f"Updated AdminPricingConfig operations_agent -> free={DEFAULT_FREE_TOKENS:,}, managed={DEFAULT_MANAGED_TOKENS:,}")
    else:
        print(f"Already exists: AdminPricingConfig operations_agent = free={cfg.free_tokens_on_purchase:,}, managed={cfg.managed_key_tokens:,}")
else:
    print(f"Created: AdminPricingConfig operations_agent = free={DEFAULT_FREE_TOKENS:,}, managed={DEFAULT_MANAGED_TOKENS:,}")

# 2. Fix stale quota rows (included_tokens still at 10_000 default)
stale = AgentTokenQuota.objects.filter(agent_name='operations_agent', included_tokens=10_000)
count = stale.count()
if count:
    stale.update(included_tokens=DEFAULT_FREE_TOKENS)
    print(f"Fixed {count} stale AgentTokenQuota row(s): 10,000 -> {DEFAULT_FREE_TOKENS:,}")
else:
    print("No stale quota rows found.")

# 3. Show current state
rows = AgentTokenQuota.objects.filter(agent_name='operations_agent').select_related('company')
print(f"\nAll operations_agent quota rows ({rows.count()} total):")
for r in rows:
    print(f"  {r.company.name}: included={r.included_tokens:,}, used={r.used_tokens:,}, pool={r.preferred_pool}")
