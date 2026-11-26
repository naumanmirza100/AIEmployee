# A backup can now belong to one company (Company dashboard → Backups): that company's own data, made by one of its
# owners or admins or by the nightly job. Backups with no company are the super admin's whole-system ones, as before.
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0124_merge_calendars_backups'),
    ]

    operations = [
        migrations.AddField(
            model_name='systembackup',
            name='company',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='backups', to='core.company'),
        ),
        migrations.AddField(
            model_name='systembackup',
            name='company_user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                    related_name='backups_made', to='core.companyuser'),
        ),
    ]
