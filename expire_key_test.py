import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from core.models import CompanyAPIKey, KeyRequest, Company, AgentTokenQuota
from core.api_key_service import _ensure_quota

company = Company.objects.get(name__icontains='reply')
now = timezone.now()

# Check if operations_agent managed key exists
key = CompanyAPIKey.objects.filter(company=company, agent_name='operations_agent', mode='managed').first()
if key:
    print(f"Key exists: id={key.id}, status={key.status}")
    key.status = 'expired'
    key.valid_until = now - timedelta(days=1)
    key.save()
    print(f"Set to expired.")
else:
    key = CompanyAPIKey(
        company=company,
        agent_name='operations_agent',
        mode='managed',
        provider='groq',
        status='expired',
        renewal_period='monthly',
        valid_until=now - timedelta(days=1),
        tokens_per_period=100000,
    )
    key.set_plaintext_key('gsk_testfakekey1234567890abcdefghijklmnop')
    key.save()
    print(f"Created fake expired key: id={key.id}")

# Create backdated key_assigned request if none exists
req = KeyRequest.objects.filter(company=company, agent_name='operations_agent', status='key_assigned').first()
if not req:
    one_month_ago = now - timedelta(days=30)
    req = KeyRequest.objects.create(
        company=company,
        agent_name='operations_agent',
        provider='groq',
        status='key_assigned',
        preferred_duration='monthly',
        is_renewal=False,
        linked_key_id=key.id,
        key_cost_snapshot=10.00,
        service_charge_snapshot=9.00,
        amount_paid=19.00,
        paid_at=one_month_ago + timedelta(hours=1),
        resolved_at=one_month_ago + timedelta(hours=2),
    )
    req.created_at = one_month_ago
    req.save()
    print(f"Created request: id={req.id}")
else:
    req.linked_key_id = key.id
    req.save()
    print(f"Request exists: id={req.id}, linked to key {key.id}")

# Ensure quota exists
quota = _ensure_quota(company, 'operations_agent')
print(f"Quota: managed_included={quota.managed_included_tokens}")
print(f"\nDone — hard reload to see Expired badge + Renew Key on Operations Agent.")
