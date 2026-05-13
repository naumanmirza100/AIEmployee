from core.models import AgentTokenQuota

updated = AgentTokenQuota.objects.update(included_tokens=10_000)
print(f"Updated {updated} quota rows → 10K tokens")
