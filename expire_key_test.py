import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from core.models import AgentTokenQuota, Company

company = Company.objects.get(name__icontains='reply')

# Show current quota state for operations_agent
quota = AgentTokenQuota.objects.filter(company=company, agent_name='operations_agent').first()
if not quota:
    print("No quota found for operations_agent")
else:
    print(f"Before reset:")
    print(f"  managed_used_tokens  = {quota.managed_used_tokens}")
    print(f"  managed_included     = {quota.managed_included_tokens}")
    print(f"  next_reset_at        = {quota.next_reset_at}")

    # Fake some usage
    quota.managed_used_tokens = 500
    # Set next_reset_at to 1 minute ago so task triggers
    quota.next_reset_at = timezone.now() - timedelta(minutes=1)
    quota.save()
    print(f"\nSet managed_used_tokens=500, next_reset_at=1 minute ago")

    # Run the reset task directly
    from core.tasks import reset_weekly_token_quotas
    reset_weekly_token_quotas()

    quota.refresh_from_db()
    print(f"\nAfter reset:")
    print(f"  managed_used_tokens  = {quota.managed_used_tokens}")
    print(f"  next_reset_at        = {quota.next_reset_at}")
    print("Done — reload page to see reset quota.")
