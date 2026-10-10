# An HR record's time zone may now be blank, which means "the company's"
# (core 0112). New records start blank. Records made before this keep the
# 'UTC' they were given: a UTC that was chosen cannot be told from one that was
# only the default, so an HR admin moves them across when they choose to
# (hr_agent/zones.py).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('hr_agent', '0020_free_stuck_leave_requests'),
        ('core', '0112_company_timezone_name'),
    ]

    operations = [
        migrations.AlterField(
            model_name='employee',
            name='timezone_name',
            field=models.CharField(blank=True, default='', help_text="This person's own IANA time zone. Blank = the company's.", max_length=64),
        ),
    ]
