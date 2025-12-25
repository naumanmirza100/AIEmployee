# Generated migration to add frontline_agent role

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_alter_userprofile_role'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(choices=[('project_manager', 'Project Manager'), ('team_member', 'Team Member'), ('viewer', 'Viewer'), ('recruitment_agent', 'Recruitment Agent'), ('frontline_agent', 'Frontline Agent')], default='team_member', max_length=20),
        ),
    ]

