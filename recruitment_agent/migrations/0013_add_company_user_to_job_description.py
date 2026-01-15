# Generated manually for adding company_user to JobDescription

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('recruitment_agent', '0012_recruiterinterviewsettings'),
        ('core', '0021_add_company_user_project_manager_role_and_relationships'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobdescription',
            name='company_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_jobs', to='core.companyuser', help_text='Company user who created this job'),
        ),
    ]

