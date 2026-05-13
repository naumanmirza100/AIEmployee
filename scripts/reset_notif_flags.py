from core.models import AgentTokenQuota; n = AgentTokenQuota.objects.update(notified_80pct=False, notified_100pct=False); print(f"Reset {n} quota notification flags")
