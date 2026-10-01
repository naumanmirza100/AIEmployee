# One settings table for what each dashboard login hears about, in the bell
# and by email (core.notification_settings).

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0107_calendarblock_leave_source'),
    ]

    operations = [
        migrations.CreateModel(
            name='NotificationSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('topic', models.CharField(max_length=40)),
                ('in_app', models.BooleanField(default=True)),
                ('email', models.BooleanField(default=False)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company_user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                                   related_name='notification_settings', to='core.companyuser')),
            ],
            options={
                'unique_together': {('company_user', 'topic')},
            },
        ),
    ]
