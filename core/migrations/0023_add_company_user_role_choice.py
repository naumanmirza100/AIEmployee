# Generated manually for adding company_user role choice

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_add_company_user_project_manager_role_and_relationships'),
    ]

    operations = [
        migrations.AlterField(
            model_name='companyuser',
            name='role',
            field=models.CharField(choices=[('owner', 'Owner'), ('admin', 'Admin'), ('manager', 'Manager'), ('recruiter', 'Recruiter'), ('company_user', 'Company User'), ('project_manager', 'Project Manager'), ('recruitment_agent', 'Recruitment Agent'), ('frontline_agent', 'Frontline Agent'), ('marketing_agent', 'Marketing Agent')], default='admin', max_length=50),
        ),
    ]

