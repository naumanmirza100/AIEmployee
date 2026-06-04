import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()

from core.models import Company, CompanyUser
from project_manager_agent.models import Project, TeamMember

company = Company.objects.get(name__icontains='reply')
print(f"Company: {company.name}")

# Show projects
projects = Project.objects.filter(company=company)
print(f"\nProjects:")
for p in projects:
    print(f"  id={p.id} — {p.name}")

# Show company users
users = CompanyUser.objects.filter(company=company, is_active=True)
print(f"\nCompany Users:")
for u in users:
    print(f"  id={u.id} — {u.full_name} ({u.email})")

# Add all company users as team members to all projects
print(f"\nAdding team members...")
for p in projects:
    for u in users:
        tm, created = TeamMember.objects.get_or_create(
            project=p,
            defaults={
                'name': u.full_name or u.email,
                'email': u.email,
                'role': 'member',
            }
        )
        status = "created" if created else "exists"
        print(f"  {p.name} ← {u.full_name} ({status})")

print("\nDone — now Meeting Scheduler will show these members.")
