import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project_manager_ai.settings')
django.setup()
from marketing_agent.models import Campaign, EmailSequence

for camp in Campaign.objects.filter(name__in=['er5t6y7u89', 'new1234']):
    print(f"\n=== Campaign '{camp.name}' (id={camp.id}, status={camp.status}) ===")
    for s in EmailSequence.objects.filter(campaign=camp).order_by('is_sub_sequence', 'name'):
        kind = 'SUB' if s.is_sub_sequence else 'MAIN'
        print(f"  [{kind}] '{s.name}'  is_active={s.is_active}  interest={s.interest_level!r}  steps={s.steps.count()}")
