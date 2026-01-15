# Generated manually for adding created_by_company_user field to Project

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0023_add_company_user_role_choice'),
    ]

    operations = [
        migrations.AddField(
            model_name='project',
            name='created_by_company_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='created_projects', to='core.companyuser', help_text='Company user who created this project'),
        ),
    ]

