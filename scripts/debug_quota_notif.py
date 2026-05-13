from core.models import AgentTokenQuota, CompanyUser
from project_manager_agent.models import PMNotification

# Step 1: check quotas
quotas = list(AgentTokenQuota.objects.select_related('company').all())
print(f"Total quotas: {len(quotas)}")
for q in quotas:
    print(f"  {q.company.name} / {q.agent_name}: {q.used_tokens}/{q.included_tokens}")

# Step 2: check company users
company_users = list(CompanyUser.objects.filter(role__in=['owner', 'admin', 'company_admin']))
print(f"\nCompany users (owner/admin): {len(company_users)}")
for cu in company_users:
    print(f"  {cu.email} role={cu.role} company={cu.company_id}")

# Step 3: try creating one notification manually
if quotas and company_users:
    q = quotas[0]
    cu = company_users[0]
    n = PMNotification.objects.create(
        company_user=cu,
        notification_type='custom',
        severity='warning',
        title=f"TEST — quota check {q.agent_name}",
        message="This is a test quota notification.",
    )
    print(f"\nTest notification created: id={n.id} for {cu.email}")
else:
    print("\nCannot create notification — no quotas or no company users found")
