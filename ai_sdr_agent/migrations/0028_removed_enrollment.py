# An unsubscribe link in a sales email named only the enrolment that sent it.
# Deleting the campaign or clearing its leads deleted the enrolment, and the link
# then had nobody to unsubscribe. Links now carry the company and the address
# themselves; this table keeps those two facts for the links already sent, at the
# moment their enrolment is deleted.

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0113_calendarblock_sales_and_executive_sources'),
        ('ai_sdr_agent', '0027_sdrmeeting_google_event'),
    ]

    operations = [
        migrations.CreateModel(
            name='SDRRemovedEnrollment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('enrollment_id', models.BigIntegerField(unique=True)),
                ('email', models.CharField(max_length=254)),
                ('removed_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='core.company')),
            ],
            options={
                'db_table': 'sdr_removed_enrollment',
            },
        ),
    ]
