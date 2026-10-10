# The company's own time zone. Leave is recorded in days and half days, and the
# shared calendar has to know when a day starts. It read the zone on each
# employee's HR record, which every record started as UTC: an afternoon off in
# Karachi blocked 6 pm to 5 am. Now a record with no zone of its own follows
# the company's.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0111_use_saved_own_keys'),
    ]

    operations = [
        migrations.AddField(
            model_name='company',
            name='timezone_name',
            field=models.CharField(blank=True, default='', help_text='IANA time zone the company works in, e.g. Asia/Karachi. Blank = not set (UTC).', max_length=64),
        ),
    ]
