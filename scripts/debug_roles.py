from core.models import CompanyUser
users = list(CompanyUser.objects.all().values('id', 'email', 'role', 'company_id', 'is_active'))
print(users)
